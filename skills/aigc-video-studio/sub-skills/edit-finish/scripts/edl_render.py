#!/usr/bin/env python3
"""EDL 骨架渲染（设计稿 §5 SK9，P2 轻量实现）。

从 shotlist + 各镜 selected_take 生成 EDL 骨架（剪映术语）：
- 按 order 排片，累加时间码
- 引用每镜选定 take 文件（缺选片则标 <未选>）
- 预留转场/调色占位

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


def _tc(seconds: float) -> str:
    m, s = divmod(int(round(seconds)), 60)
    return f"{m:02d}:{s:02d}"


def _selected_take(project: str | Path, shot_id: str) -> str | None:
    tp = project_path(project, "06_generations", shot_id, "takes.yaml")
    if tp.exists():
        return read_yaml(tp).get("selected_take")
    return None


def build_edl(project: str | Path) -> dict[str, Any]:
    shotlist = read_yaml(project_path(project, "04_storyboard", "shotlist.yaml"))
    shots = sorted(shotlist.get("shots", []), key=lambda s: s.get("order", 0))

    clips: list[dict[str, Any]] = []
    cursor = 0.0
    for shot in shots:
        dur = float(shot.get("duration_s", 0))
        clips.append({
            "shot_id": shot["shot_id"],
            "in_tc": _tc(cursor),
            "out_tc": _tc(cursor + dur),
            "duration_s": dur,
            "take": _selected_take(project, shot["shot_id"]) or "<未选>",
            "transition_out": "硬切",
        })
        cursor += dur
    return {"clips": clips, "total_duration_s": round(cursor, 2)}


def render_md(edl: dict[str, Any]) -> str:
    lines = ["# EDL 骨架（剪映可导入清单）", "",
             "| # | 镜头 | 入点 | 出点 | take | 转场 |",
             "|---|---|---|---|---|---|"]
    for i, c in enumerate(edl["clips"], 1):
        lines.append(f"| {i} | {c['shot_id']} | {c['in_tc']} | {c['out_tc']} "
                     f"| {c['take']} | {c['transition_out']} |")
    lines += ["", f"总时长：{edl['total_duration_s']}s",
              "", "## 统一调色", "> 从 style-bible 导出参数（占位）"]
    return "\n".join(lines) + "\n"


def generate(project: str | Path, *, out: str | Path | None = None) -> dict[str, Any]:
    edl = build_edl(project)
    out_path = Path(out) if out else project_path(project, "08_edit", "edl.md")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(render_md(edl), encoding="utf-8")
    return {"out": str(out_path), "clip_count": len(edl["clips"]),
            "total_duration_s": edl["total_duration_s"]}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="EDL 骨架渲染（SK9，P2）")
    parser.add_argument("--project", required=True)
    parser.add_argument("--out")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    result = generate(args.project, out=args.out)
    if args.json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        print(f"EDL {result['clip_count']} 段 / {result['total_duration_s']}s -> {result['out']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
