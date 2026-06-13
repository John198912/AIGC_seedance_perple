#!/usr/bin/env python3
"""情绪曲线生成 + 平值校验（设计稿 §5 SK2，P2 轻量实现）。

读剧本（C3），从 scenes[].emotion_value 派生情绪曲线，并校验
“无连续 3 场平值”（设计稿编剧约束）。输出 ASCII 走势 + 曲线数据。

CLI：
  python emotion_curve.py --project <dir> [--screenplay <path>] [--json]
退出码：0 = 无连续平值；1 = 命中连续 3 场平值告警。
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

FLAT_RUN = 3  # 连续平值阈值


def build_curve(screenplay: dict[str, Any]) -> dict[str, Any]:
    scenes = screenplay.get("scenes", [])
    curve = [{"scene_id": s.get("scene_id"), "value": float(s.get("emotion_value", 0))}
             for s in scenes]

    # 连续平值检测
    flat_segments: list[list[str]] = []
    run: list[str] = []
    prev = None
    for pt in curve:
        if prev is not None and pt["value"] == prev:
            run.append(pt["scene_id"])
        else:
            if len(run) >= FLAT_RUN:
                flat_segments.append(run)
            run = [pt["scene_id"]]
        prev = pt["value"]
    if len(run) >= FLAT_RUN:
        flat_segments.append(run)

    return {
        "points": curve,
        "max": max((p["value"] for p in curve), default=0),
        "min": min((p["value"] for p in curve), default=0),
        "flat_segments": flat_segments,
        "ok": not flat_segments,
    }


def render_ascii(curve: list[dict[str, Any]]) -> str:
    lines = []
    for p in curve:
        bar = "█" * int(round(p["value"]))
        lines.append(f"{str(p['scene_id'])[:10]:>10} |{bar} {p['value']}")
    return "\n".join(lines)


def _load(project: str | None, path: str | None) -> dict[str, Any]:
    if path:
        return read_yaml(path)
    return read_yaml(project_path(project, "02_screenplay", "screenplay.yaml"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="情绪曲线 + 平值校验（SK2，P2）")
    parser.add_argument("--project")
    parser.add_argument("--screenplay")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    if not args.project and not args.screenplay:
        parser.error("需 --project 或 --screenplay 之一")

    result = build_curve(_load(args.project, args.screenplay))
    if args.json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        print(render_ascii(result["points"]))
        if result["flat_segments"]:
            print(f"告警 连续平值段：{result['flat_segments']}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
