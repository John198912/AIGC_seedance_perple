#!/usr/bin/env python3
"""剪辑工程导出（设计稿 §9 路线图 D-3，半自动·需人工在 NLE 内重链接）。

从 EDL（edl_render.build_edl）+ 选定 takes 导出两种可导入剪辑工程：
1. 剪映可导入清单（draft-content 风格 JSON）：tracks/segments/入出点/转场/调色占位。
2. FCPXML（标准 XML，供 Premiere/DaVinci Resolve/FCP 导入）：fcpxml>resources>library>
   event>project>sequence>spine>asset-clip。

半自动纪律：媒体路径用 media-manifest 占位（项目相对路径），**导出后需人工在 NLE 内
重新链接（relink）实体媒体**；本脚本只产工程骨架，不打包/搬运媒体实体（遵守 .gitignore）。

确定性：轨道/片段/入出点/时间码均由 EDL 派生（帧率默认 30fps），可复现、不触网。

CLI：
  python project_export.py --project <dir> [--fps 30]
      [--capcut 08_edit/capcut-draft.json] [--fcpxml 08_edit/timeline.fcpxml] [--json]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any
from xml.dom import minidom
from xml.etree import ElementTree as ET

sys.path.insert(0, str((Path(__file__).resolve().parent.parent.parent
                        / "_shared" / "scripts")))
from _common import read_yaml, write_json, project_path  # noqa: E402

# 当前目录可导入同目录 edl_render
sys.path.insert(0, str(Path(__file__).resolve().parent))
import edl_render  # noqa: E402

DEFAULT_FPS = 30


def _tc_to_seconds(tc: str) -> float:
    """'MM:SS' → 秒。"""
    parts = tc.split(":")
    if len(parts) == 2:
        return int(parts[0]) * 60 + int(parts[1])
    return float(tc or 0)


def _selected_take_file(project: str | Path, shot_id: str, take_id: str | None) -> str:
    """从 takes.yaml 找选定 take 的媒体文件路径（占位，需人工重链）。"""
    tp = project_path(project, "06_generations", shot_id, "takes.yaml")
    if take_id and tp.exists():
        for t in read_yaml(tp).get("takes", []) or []:
            if t.get("take_id") == take_id and t.get("file"):
                return t["file"]
    return f"06_generations/{shot_id}/{take_id or 'SELECTED'}.mp4"


def build_capcut_draft(project: str | Path, edl: dict[str, Any], *,
                       fps: int = DEFAULT_FPS) -> dict[str, Any]:
    """剪映 draft-content 风格清单（简化结构，供导入参考；非剪映私有完整格式）。"""
    video_segments: list[dict[str, Any]] = []
    text_segments: list[dict[str, Any]] = []
    cursor_us = 0  # 剪映以微秒计
    for clip in edl["clips"]:
        dur_s = float(clip["duration_s"])
        dur_us = int(round(dur_s * 1_000_000))
        take_id = None if clip["take"] == "<未选>" else clip["take"]
        video_segments.append({
            "shot_id": clip["shot_id"],
            "material_path": _selected_take_file(project, clip["shot_id"], take_id),
            "target_timerange": {"start": cursor_us, "duration": dur_us},
            "source_timerange": {"start": 0, "duration": dur_us},
            "transition": clip["transition_in"],
            "needs_relink": True,  # 半自动：导入后人工重链实体媒体
        })
        cursor_us += dur_us

    sub_cursor = 0
    for s in edl["subtitles"]:
        start_us = int(round(_tc_to_seconds(s["in_tc"]) * 1_000_000))
        end_us = int(round(_tc_to_seconds(s["out_tc"]) * 1_000_000))
        text_segments.append({
            "shot_id": s["shot_id"], "content": s["text"],
            "target_timerange": {"start": start_us, "duration": max(0, end_us - start_us)},
        })

    return {
        "draft_type": "capcut_import_manifest",
        "semi_automatic": True,
        "needs_relink": True,
        "fps": fps,
        "duration_us": cursor_us,
        "color_grade_placeholder": edl["color_grade"],
        "tracks": [
            {"type": "video", "segments": video_segments},
            {"type": "text", "segments": text_segments},
            {"type": "audio_ambience",
             "segments": [{"ambience_group": b["ambience_group"],
                           "shared_asset": b["shared_asset"],
                           "in_tc": b["in_tc"], "out_tc": b["out_tc"]}
                          for b in edl.get("ambience_bridges", [])]},
        ],
    }


def _frame_dur(fps: int) -> str:
    return f"1/{fps}s"


def _rational(seconds: float, fps: int) -> str:
    """秒 → FCPXML 有理时间 'N/Ds'（按帧对齐）。"""
    frames = int(round(seconds * fps))
    return f"{frames * 1}/{fps}s" if frames else "0s"


def build_fcpxml(project: str | Path, edl: dict[str, Any], *,
                 fps: int = DEFAULT_FPS, title: str = "AIGC Timeline") -> str:
    """构造标准 FCPXML（v1.10）字符串，良构可被 Premiere/Resolve 导入。"""
    fcpxml = ET.Element("fcpxml", version="1.10")
    resources = ET.SubElement(fcpxml, "resources")
    fmt_id = "r1"
    ET.SubElement(resources, "format", id=fmt_id, name="FFVideoFormat1080p30",
                  frameDuration=_frame_dur(fps), width="1920", height="1080")

    # 每镜一个 asset 资源（媒体为占位 src，需人工重链）
    asset_ids: dict[str, str] = {}
    for i, clip in enumerate(edl["clips"], 1):
        aid = f"a{i}"
        asset_ids[clip["shot_id"]] = aid
        take_id = None if clip["take"] == "<未选>" else clip["take"]
        src = _selected_take_file(project, clip["shot_id"], take_id)
        dur = _rational(float(clip["duration_s"]), fps)
        asset = ET.SubElement(resources, "asset", id=aid, name=clip["shot_id"],
                              start="0s", duration=dur, hasVideo="1", format=fmt_id)
        ET.SubElement(asset, "media-rep", kind="original-media",
                      src=f"file://./{src}")

    library = ET.SubElement(fcpxml, "library")
    event = ET.SubElement(library, "event", name="AIGC")
    project_el = ET.SubElement(event, "project", name=title)
    total = _rational(float(edl["total_duration_s"]), fps)
    sequence = ET.SubElement(project_el, "sequence", format=fmt_id,
                             duration=total, tcStart="0s", tcFormat="NDF")
    spine = ET.SubElement(sequence, "spine")

    offset = 0.0
    for clip in edl["clips"]:
        dur_s = float(clip["duration_s"])
        ac = ET.SubElement(spine, "asset-clip",
                           ref=asset_ids[clip["shot_id"]],
                           name=clip["shot_id"],
                           offset=_rational(offset, fps),
                           duration=_rational(dur_s, fps),
                           start="0s")
        # 转场以 marker 标注（半自动，导入后人工套用真实转场）
        ET.SubElement(ac, "marker", start=_rational(offset, fps),
                      duration=_frame_dur(fps), value=clip["transition_in"])
        offset += dur_s

    raw = ET.tostring(fcpxml, encoding="unicode")
    return minidom.parseString(raw).toprettyxml(indent="  ")


def generate(project: str | Path, *, fps: int = DEFAULT_FPS,
             capcut_out: str | Path | None = None,
             fcpxml_out: str | Path | None = None) -> dict[str, Any]:
    edl = edl_render.build_edl(project)
    meta_path = project_path(project, "project.yaml")
    title = read_yaml(meta_path).get("title", "AIGC Timeline") if meta_path.exists() else "AIGC Timeline"

    capcut = build_capcut_draft(project, edl, fps=fps)
    fcpxml = build_fcpxml(project, edl, fps=fps, title=title)

    cc_path = Path(capcut_out) if capcut_out else project_path(project, "08_edit", "capcut-draft.json")
    fx_path = Path(fcpxml_out) if fcpxml_out else project_path(project, "08_edit", "timeline.fcpxml")
    write_json(cc_path, capcut)
    fx_path.parent.mkdir(parents=True, exist_ok=True)
    fx_path.write_text(fcpxml, encoding="utf-8")

    return {"capcut_out": str(cc_path), "fcpxml_out": str(fx_path),
            "clip_count": len(edl["clips"]), "fps": fps,
            "needs_relink": True, "total_duration_s": edl["total_duration_s"]}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="剪辑工程导出（D-3，半自动·需人工重链）")
    parser.add_argument("--project", required=True)
    parser.add_argument("--fps", type=int, default=DEFAULT_FPS)
    parser.add_argument("--capcut")
    parser.add_argument("--fcpxml")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    result = generate(args.project, fps=args.fps,
                      capcut_out=args.capcut, fcpxml_out=args.fcpxml)
    if args.json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        print(f"剪辑工程导出（{result['clip_count']} 段 / {result['fps']}fps）：")
        print(f"  剪映清单 -> {result['capcut_out']}")
        print(f"  FCPXML  -> {result['fcpxml_out']}")
        print("  注：媒体为占位路径，导入后需人工在 NLE 内重新链接（relink）。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
