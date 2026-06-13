#!/usr/bin/env python3
"""EDL 渲染（设计稿 §5 SK9，Phase 4 可用实现）。

从「选定 takes + shotlist + qc-report + style-bible」生成 08_edit/edl.md（剪映术语）：
- 按 order 排片，累加时间码，引用每镜 selected_take（缺选片标 <未选>）
- 转场：按相邻镜 ambience_group 是否同组给“叠化（同场景）/硬切（换场）”
- 统一调色：从 style-bible 导出参数表（解析 `调色:`/`color_grade:` 段，缺省按 brief 风格词派生）
- 字幕：从 shotlist.dialogue / audio_cue 提取占位字幕轨
- 超分/插帧建议：draft 来源 take 建议超分到 1080p；高速运镜镜头建议插帧
- QC 问题逐条映射处置（读 08_edit/qc-report.yaml，blocker/major 标到对应镜）

确定性：时间码/转场/调色由输入派生，可复现，不触网。

CLI：
  python edl_render.py --project <dir> [--out 08_edit/edl.md] [--json]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str((Path(__file__).resolve().parent.parent.parent
                        / "_shared" / "scripts")))
from _common import read_yaml, project_path  # noqa: E402

# 默认调色参数（缺 style-bible 时，按废土/纪实基调派生的安全值）
DEFAULT_GRADE = {
    "色温": "暖偏黄（4800K 倾向）",
    "对比度": "中高",
    "饱和度": "低饱和",
    "颗粒": "胶片颗粒中等",
    "高光": "柔化压低",
}


def _tc(seconds: float) -> str:
    m, s = divmod(int(round(seconds)), 60)
    return f"{m:02d}:{s:02d}"


def _selected_take(project: str | Path, shot_id: str) -> str | None:
    tp = project_path(project, "06_generations", shot_id, "takes.yaml")
    if tp.exists():
        return read_yaml(tp).get("selected_take")
    return None


def _take_meta(project: str | Path, shot_id: str, take_id: str | None) -> dict[str, Any]:
    """取选定 take 的 pass/分辨率信息，供超分建议。"""
    if not take_id:
        return {}
    tp = project_path(project, "06_generations", shot_id, "takes.yaml")
    if not tp.exists():
        return {}
    for t in read_yaml(tp).get("takes", []):
        if t.get("take_id") == take_id:
            return t
    return {}


def load_color_grade(project: str | Path) -> dict[str, str]:
    """从 style-bible.md 解析调色参数；缺省按 brief 风格词派生默认值。"""
    sb = project_path(project, "03_style", "style-bible.md")
    grade: dict[str, str] = {}
    if sb.exists():
        for line in sb.read_text(encoding="utf-8").splitlines():
            line = line.strip().lstrip("-*").strip()
            for sep in ("：", ":"):
                if sep in line:
                    k, v = line.split(sep, 1)
                    k, v = k.strip(), v.strip()
                    if k in ("色温", "对比度", "饱和度", "颗粒", "高光", "色调", "影调"):
                        grade[k] = v
                    break
    if grade:
        return grade
    # 缺 style-bible：从 brief.style_keywords 派生提示，否则用默认
    brief_path = project_path(project, "01_brief", "brief.yaml")
    if brief_path.exists():
        kws = read_yaml(brief_path).get("style_keywords", []) or []
        if kws:
            return dict(DEFAULT_GRADE, 风格关键词="、".join(kws))
    return dict(DEFAULT_GRADE)


def load_qc_issues(project: str | Path) -> dict[str, list[dict[str, Any]]]:
    """读 qc-report.yaml，按 shot_id 聚合 blocker/major 问题，供 EDL 标注处置。"""
    qc = project_path(project, "08_edit", "qc-report.yaml")
    by_shot: dict[str, list[dict[str, Any]]] = {}
    if not qc.exists():
        return by_shot
    for issue in read_yaml(qc).get("issues", []) or []:
        if issue.get("severity") in ("blocker", "major"):
            by_shot.setdefault(issue.get("shot_id", "?"), []).append(issue)
    return by_shot


def load_ambience_bridges(project: str | Path) -> list[dict[str, Any]]:
    """读 07_audio/audio-manifest.yaml 的共享环境音床，转为 EDL「环境音桥接」轨道。

    A.3：同 ambience_group 的镜头共用一条环境音床，剪辑层加桥接轨交叉淡入淡出，
    根治「单段好、连起来散」的跨镜音频割裂。无音频清单时返回空。
    """
    am = project_path(project, "07_audio", "audio-manifest.yaml")
    if not am.exists():
        return []
    groups = read_yaml(am).get("ambience_groups", []) or []
    return [{
        "ambience_group": g["ambience_group"],
        "in_tc": _tc(g["bed_start_s"]),
        "out_tc": _tc(g["bed_end_s"]),
        "shared_asset": g.get("shared_asset", ""),
        "shots": g.get("shots", []),
    } for g in groups]


def build_edl(project: str | Path) -> dict[str, Any]:
    shotlist = read_yaml(project_path(project, "04_storyboard", "shotlist.yaml"))
    shots = sorted(shotlist.get("shots", []), key=lambda s: s.get("order", 0))
    qc_by_shot = load_qc_issues(project)

    clips: list[dict[str, Any]] = []
    subtitles: list[dict[str, Any]] = []
    upscale_hints: list[dict[str, Any]] = []
    cursor = 0.0
    prev_group = None
    for shot in shots:
        dur = float(shot.get("duration_s", 0))
        sid = shot["shot_id"]
        take_id = _selected_take(project, sid)
        same_scene = (shot.get("ambience_group") is not None
                      and shot.get("ambience_group") == prev_group)
        transition = "叠化（同场景过渡）" if same_scene else "硬切（换场）"

        clips.append({
            "shot_id": sid,
            "in_tc": _tc(cursor),
            "out_tc": _tc(cursor + dur),
            "duration_s": dur,
            "take": take_id or "<未选>",
            "transition_in": transition,
            "qc_remedies": [i.get("remedy", "") for i in qc_by_shot.get(sid, [])],
        })

        # 字幕轨：对白优先，否则 audio_cue 作旁注
        text = shot.get("dialogue") or shot.get("audio_cue")
        if text:
            subtitles.append({"shot_id": sid, "in_tc": _tc(cursor),
                              "out_tc": _tc(cursor + dur), "text": text})

        # 超分/插帧建议
        meta = _take_meta(project, sid, take_id)
        if meta.get("pass") == "draft":
            upscale_hints.append({"shot_id": sid, "type": "超分",
                                  "note": "draft 来源建议超分到 1080p 终渲"})
        if "推" in str(shot.get("camera_move", "")) or "快" in str(shot.get("camera_move", "")):
            upscale_hints.append({"shot_id": sid, "type": "插帧",
                                  "note": "运镜较快，建议插帧平滑（60fps）"})

        cursor += dur
        prev_group = shot.get("ambience_group")

    return {
        "clips": clips,
        "subtitles": subtitles,
        "upscale_hints": upscale_hints,
        "ambience_bridges": load_ambience_bridges(project),
        "color_grade": load_color_grade(project),
        "total_duration_s": round(cursor, 2),
        "qc_mapped": sum(len(v) for v in qc_by_shot.values()),
    }


def render_md(edl: dict[str, Any]) -> str:
    lines = ["# EDL（剪映可导入清单）", "",
             "> SK9 剪辑成片。注：粗剪不计入 MVP 验收门槛（设计稿 §9）。", "",
             "## 拼接顺序与转场",
             "",
             "| # | 镜头 | 入点 | 出点 | take | 转场 | QC 处置 |",
             "|---|---|---|---|---|---|---|"]
    for i, c in enumerate(edl["clips"], 1):
        remedy = "；".join(r for r in c["qc_remedies"] if r) or "—"
        lines.append(f"| {i} | {c['shot_id']} | {c['in_tc']} | {c['out_tc']} "
                     f"| {c['take']} | {c['transition_in']} | {remedy} |")
    lines += ["", f"总时长：{edl['total_duration_s']}s", ""]

    # 统一调色
    lines += ["## 统一调色（从 style-bible 导出）", "",
              "| 参数 | 取值 |", "|---|---|"]
    for k, v in edl["color_grade"].items():
        lines.append(f"| {k} | {v} |")
    lines.append("")

    # 字幕轨
    lines += ["## 字幕轨", ""]
    if edl["subtitles"]:
        lines += ["| 镜头 | 入点 | 出点 | 字幕 |", "|---|---|---|---|"]
        for s in edl["subtitles"]:
            lines.append(f"| {s['shot_id']} | {s['in_tc']} | {s['out_tc']} | {s['text']} |")
    else:
        lines.append("无对白/旁注，无字幕轨。")
    lines.append("")

    # 环境音桥接轨（A.3）
    lines += ["## 环境音桥接轨", ""]
    bridges = edl.get("ambience_bridges", [])
    if bridges:
        lines += ["| 场景组 | 入点 | 出点 | 共享环境音 | 成员镜头 |",
                  "|---|---|---|---|---|"]
        for b in bridges:
            lines.append(f"| {b['ambience_group']} | {b['in_tc']} | {b['out_tc']} "
                         f"| `{b['shared_asset']}` | {', '.join(b['shots'])} |")
        lines.append("")
        lines.append("> 组内镜头共用环境音床，转场处交叉淡入淡出，避免跨镜音频割裂。")
    else:
        lines.append("无跨镜共享环境音组。")
    lines.append("")

    # 超分/插帧建议
    lines += ["## 超分 / 插帧建议", ""]
    if edl["upscale_hints"]:
        for h in edl["upscale_hints"]:
            lines.append(f"- `{h['shot_id']}` {h['type']}：{h['note']}")
    else:
        lines.append("无需超分/插帧。")
    lines.append("")
    return "\n".join(lines) + "\n"


def generate(project: str | Path, *, out: str | Path | None = None) -> dict[str, Any]:
    edl = build_edl(project)
    out_path = Path(out) if out else project_path(project, "08_edit", "edl.md")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(render_md(edl), encoding="utf-8")
    return {"out": str(out_path), "clip_count": len(edl["clips"]),
            "subtitle_count": len(edl["subtitles"]),
            "upscale_hint_count": len(edl["upscale_hints"]),
            "qc_mapped": edl["qc_mapped"],
            "total_duration_s": edl["total_duration_s"]}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="EDL 渲染（SK9）")
    parser.add_argument("--project", required=True)
    parser.add_argument("--out")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    result = generate(args.project, out=args.out)
    if args.json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        print(f"EDL {result['clip_count']} 段 / {result['total_duration_s']}s -> {result['out']}")
        print(f"  字幕 {result['subtitle_count']} 条，超分/插帧建议 "
              f"{result['upscale_hint_count']} 条，QC 处置映射 {result['qc_mapped']} 条")
    return 0


if __name__ == "__main__":
    sys.exit(main())
