#!/usr/bin/env python3
"""音频素材清单 + 时间轴对齐 + voice_bind 映射（设计稿 §5 SK8，P2 轻量实现）。

按 shotlist 的选定镜头与 ambience_group 生成音频清单：
- 按 order 累加时间轴（start_s/end_s）
- ambience_group 相同的相邻镜头标“环境音桥接”
- voice_bind：若角色卡填了 voice_ref，输出 角色→声纹资产 映射（跨镜一致）

CLI：
  python audio_manifest.py --project <dir> [--out 07_audio/audio-manifest.yaml] [--json]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str((Path(__file__).resolve().parent.parent.parent
                        / "_shared" / "scripts")))
from _common import read_yaml, write_yaml, project_path  # noqa: E402


def _voice_binds(project: str | Path) -> dict[str, str]:
    """扫角色卡 voice_ref，产出 角色id → 声纹资产 映射。"""
    chars_dir = project_path(project, "03_characters")
    binds: dict[str, str] = {}
    if chars_dir.exists():
        for card in sorted(chars_dir.glob("*/card.yaml")):
            data = read_yaml(card)
            if data.get("voice_ref"):
                binds[data["id"]] = data["voice_ref"]
    return binds


def build_manifest(project: str | Path) -> dict[str, Any]:
    shotlist = read_yaml(project_path(project, "04_storyboard", "shotlist.yaml"))
    shots = sorted(shotlist.get("shots", []), key=lambda s: s.get("order", 0))

    timeline: list[dict[str, Any]] = []
    cursor = 0.0
    prev_group = None
    for shot in shots:
        dur = float(shot.get("duration_s", 0))
        entry = {
            "shot_id": shot["shot_id"],
            "start_s": round(cursor, 2),
            "end_s": round(cursor + dur, 2),
            "audio_cue": shot.get("audio_cue", ""),
            "ambience_group": shot.get("ambience_group"),
            "bridge_prev": shot.get("ambience_group") is not None
                           and shot.get("ambience_group") == prev_group,
        }
        timeline.append(entry)
        cursor += dur
        prev_group = shot.get("ambience_group")

    return {
        "total_duration_s": round(cursor, 2),
        "timeline": timeline,
        "voice_bind": _voice_binds(project),
    }


def generate(project: str | Path, *, out: str | Path | None = None) -> dict[str, Any]:
    manifest = build_manifest(project)
    out_path = Path(out) if out else project_path(project, "07_audio", "audio-manifest.yaml")
    write_yaml(out_path, manifest)
    manifest["out"] = str(out_path)
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="音频清单 + 时间轴 + voice_bind（SK8，P2）")
    parser.add_argument("--project", required=True)
    parser.add_argument("--out")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    manifest = generate(args.project, out=args.out)
    if args.json:
        print(json.dumps(manifest, ensure_ascii=False))
    else:
        print(f"音频清单 {len(manifest['timeline'])} 段，总时长 {manifest['total_duration_s']}s")
        if manifest["voice_bind"]:
            print(f"  声纹绑定：{manifest['voice_bind']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
