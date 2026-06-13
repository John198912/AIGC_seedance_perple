#!/usr/bin/env python3
"""封面候选提取（设计稿 §5 SK10，Q-8，P2 轻量实现）。

从 shotlist“记忆点镜头”提封面候选：优先 control_level=locked 的关键镜，
其次情绪/动作密度高（有 action_logic）的镜头。输出候选镜头 + 其选定 take 文件。

CLI：
  python cover_extractor.py --project <dir> [--top 3] [--json]
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


def _score(shot: dict[str, Any]) -> int:
    """记忆点打分：locked 关键镜 + 有动作描述 + 有首帧 → 高分。"""
    score = 0
    if shot.get("control_level") == "locked":
        score += 3
    if shot.get("action_logic"):
        score += 2
    if shot.get("first_frame"):
        score += 1
    return score


def _selected_take_file(project: str | Path, shot_id: str) -> str | None:
    tp = project_path(project, "06_generations", shot_id, "takes.yaml")
    if not tp.exists():
        return None
    tl = read_yaml(tp)
    sel = tl.get("selected_take")
    if not sel:
        return None
    for t in tl.get("takes", []):
        if t.get("take_id") == sel:
            return t.get("file")
    return None


def extract(project: str | Path, *, top: int = 3) -> dict[str, Any]:
    shotlist = read_yaml(project_path(project, "04_storyboard", "shotlist.yaml"))
    ranked = sorted(shotlist.get("shots", []), key=_score, reverse=True)
    candidates = []
    for shot in ranked[:top]:
        candidates.append({
            "shot_id": shot["shot_id"],
            "score": _score(shot),
            "first_frame": shot.get("first_frame"),
            "selected_take_file": _selected_take_file(project, shot["shot_id"]),
        })
    return {"candidates": candidates, "top": top}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="封面候选提取（SK10，P2）")
    parser.add_argument("--project", required=True)
    parser.add_argument("--top", type=int, default=3)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    result = extract(args.project, top=args.top)
    if args.json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        print(f"封面候选 Top {result['top']}：")
        for c in result["candidates"]:
            print(f"  {c['shot_id']} (score={c['score']}) "
                  f"frame={c['first_frame']} take={c['selected_take_file']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
