#!/usr/bin/env python3
"""分镜统计 + 连贯性 lint（设计稿 §5 SK4，P2 轻量实现）。

读 shotlist.yaml（C5），输出：
- 景别 / control_level / variant 分布
- 总时长 + 每镜 ≤15s 校验
- 连贯性 lint：order 是否连续无缺号、是否有重复 shot_id

CLI：
  python shotlist_stats.py --project <dir> [--shotlist <path>] [--json]
退出码：0 = 无 lint 错误；1 = 有 lint 错误（缺号/重复/超时）。
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

sys.path.insert(0, str((Path(__file__).resolve().parent.parent.parent
                        / "_shared" / "scripts")))
from _common import read_yaml, project_path  # noqa: E402

MAX_SHOT_S = 15


def analyze(shotlist: dict[str, Any]) -> dict[str, Any]:
    shots = shotlist.get("shots", [])
    durations = [float(s.get("duration_s", 0)) for s in shots]
    orders = [s.get("order") for s in shots if s.get("order") is not None]
    ids = [s.get("shot_id") for s in shots]

    lint: list[str] = []
    over = [s["shot_id"] for s in shots if float(s.get("duration_s", 0)) > MAX_SHOT_S]
    if over:
        lint.append(f"超 {MAX_SHOT_S}s 的镜头：{over}")
    dup = [i for i, c in Counter(ids).items() if c > 1]
    if dup:
        lint.append(f"重复 shot_id：{dup}")
    if orders:
        expected = set(range(min(orders), max(orders) + 1))
        missing = sorted(expected - set(orders))
        if missing:
            lint.append(f"order 缺号：{missing}")

    return {
        "shot_count": len(shots),
        "total_duration_s": round(sum(durations), 2),
        "shot_size_dist": dict(Counter(s.get("shot_size", "?") for s in shots)),
        "control_level_dist": dict(Counter(s.get("control_level", "?") for s in shots)),
        "variant_dist": dict(Counter(s.get("variant", "?") for s in shots)),
        "lint": lint,
        "ok": not lint,
    }


def _load(project: str | None, shotlist_path: str | None) -> dict[str, Any]:
    if shotlist_path:
        return read_yaml(shotlist_path)
    return read_yaml(project_path(project, "04_storyboard", "shotlist.yaml"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="分镜统计 + 连贯性 lint（SK4，P2）")
    parser.add_argument("--project")
    parser.add_argument("--shotlist")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    if not args.project and not args.shotlist:
        parser.error("需 --project 或 --shotlist 之一")

    report = analyze(_load(args.project, args.shotlist))
    if args.json:
        print(json.dumps(report, ensure_ascii=False))
    else:
        print(f"镜头 {report['shot_count']} 总时长 {report['total_duration_s']}s")
        print(f"  景别 {report['shot_size_dist']}")
        print(f"  控制级 {report['control_level_dist']}")
        for w in report["lint"]:
            print(f"  lint: {w}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
