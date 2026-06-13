#!/usr/bin/env python3
"""提示词模式指标统计（设计稿 §5 SK0 / §7.3，S-P1-6，P1）。

按 takes.yaml 中各 take 的 prompt_pattern_tags 聚合：
- take 数（抽卡数）
- 命中数 / 命中率（命中定义：VLM verdict=pass_to_human 或 status=selected）
- 成本（按 ledger by_shot 的镜头成本，均摊到该镜各 take 再归到 tag）

用途：为提示词 A/B 与经验校准提供数据（“抽卡命中率随项目数提升”）。

CLI：
  python metrics.py --project <dir> [--json]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import read_yaml, project_path  # noqa: E402
import ledger as _ledger  # noqa: E402

# 命中判定：通过 VLM 人审或被选中即视为“有效命中”
HIT_VERDICTS = {"pass_to_human"}
HIT_STATUSES = {"selected"}


def _is_hit(take: dict[str, Any]) -> bool:
    verdict = (take.get("scores", {}).get("agent_vlm", {}) or {}).get("verdict")
    if verdict in HIT_VERDICTS:
        return True
    return take.get("status") in HIT_STATUSES


def _iter_takelogs(project: str | Path):
    gen_dir = project_path(project, "06_generations")
    if not gen_dir.exists():
        return
    for shot_dir in sorted(gen_dir.iterdir()):
        if shot_dir.is_dir() and shot_dir.name.startswith("SHOT-"):
            tp = shot_dir / "takes.yaml"
            if tp.exists():
                yield shot_dir.name, read_yaml(tp)


def collect(project: str | Path) -> dict[str, Any]:
    """聚合各 prompt_pattern_tag 的抽卡/命中/成本。返回报表 dict。"""
    summary = _ledger.get_summary(project)
    by_shot_cost = {s: float(v.get("cny", 0.0))
                    for s, v in (summary.get("by_shot", {}) or {}).items()}

    tags: dict[str, dict[str, Any]] = {}
    total_takes = 0
    total_hits = 0

    for shot_id, takelog in _iter_takelogs(project):
        shot_takes = takelog.get("takes", [])
        n = len(shot_takes)
        # 该镜成本均摊到每 take
        per_take_cost = (by_shot_cost.get(shot_id, 0.0) / n) if n else 0.0
        for take in shot_takes:
            total_takes += 1
            hit = _is_hit(take)
            total_hits += 1 if hit else 0
            tag_list = take.get("prompt_pattern_tags") or ["<untagged>"]
            for tag in tag_list:
                slot = tags.setdefault(tag, {"takes": 0, "hits": 0, "cost_cny": 0.0})
                slot["takes"] += 1
                slot["hits"] += 1 if hit else 0
                slot["cost_cny"] = round(slot["cost_cny"] + per_take_cost, 4)

    # 计算命中率
    for slot in tags.values():
        slot["hit_rate"] = round(slot["hits"] / slot["takes"], 4) if slot["takes"] else 0.0
        slot["cost_per_hit_cny"] = (round(slot["cost_cny"] / slot["hits"], 4)
                                    if slot["hits"] else None)

    return {
        "total_takes": total_takes,
        "total_hits": total_hits,
        "overall_hit_rate": round(total_hits / total_takes, 4) if total_takes else 0.0,
        "by_tag": tags,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="prompt_pattern_tags 指标统计（SK0）")
    parser.add_argument("--project", required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    report = collect(args.project)

    if args.json:
        print(json.dumps(report, ensure_ascii=False))
    else:
        print(f"总抽卡 {report['total_takes']} / 命中 {report['total_hits']} "
              f"/ 命中率 {report['overall_hit_rate']:.0%}")
        print("按模式标签：")
        for tag, s in sorted(report["by_tag"].items(),
                             key=lambda kv: kv[1]["hit_rate"], reverse=True):
            print(f"  {tag}: 抽卡 {s['takes']} 命中 {s['hits']} "
                  f"率 {s['hit_rate']:.0%} 成本 {s['cost_cny']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
