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


def compare_ab(project: str | Path, tag_a: str, tag_b: str,
               report: dict[str, Any] | None = None) -> dict[str, Any]:
    """提示词 A/B 对比（S-P1-6 学习回路）：比较两个 prompt_pattern_tag 的命中率与单位成本。

    返回各臂的抽卡/命中/命中率/单位命中成本，以及胜出臂（命中率优先，并列看单位成本）。
    用于「同一镜多提示词变体并行 → 学习哪种模式更高效」。
    """
    report = report or collect(project)
    by_tag = report.get("by_tag", {})
    empty = {"takes": 0, "hits": 0, "hit_rate": 0.0, "cost_cny": 0.0, "cost_per_hit_cny": None}
    a = by_tag.get(tag_a, dict(empty))
    b = by_tag.get(tag_b, dict(empty))

    def _winner() -> str | None:
        if a["takes"] == 0 and b["takes"] == 0:
            return None
        if a["hit_rate"] != b["hit_rate"]:
            return tag_a if a["hit_rate"] > b["hit_rate"] else tag_b
        # 命中率并列 → 单位命中成本更低者胜（None 视为最差）
        ca = a.get("cost_per_hit_cny")
        cb = b.get("cost_per_hit_cny")
        if ca is None and cb is None:
            return None
        if ca is None:
            return tag_b
        if cb is None:
            return tag_a
        if ca == cb:
            return None
        return tag_a if ca < cb else tag_b

    return {
        "arm_a": {"tag": tag_a, **{k: a.get(k) for k in empty}},
        "arm_b": {"tag": tag_b, **{k: b.get(k) for k in empty}},
        "winner": _winner(),
        "hit_rate_delta": round(a["hit_rate"] - b["hit_rate"], 4),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="prompt_pattern_tags 指标统计 + A/B 对比（SK0）")
    parser.add_argument("--project", required=True)
    parser.add_argument("--ab", nargs=2, metavar=("TAG_A", "TAG_B"),
                        help="对比两个 prompt_pattern_tag 的命中率/单位成本")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    report = collect(args.project)

    if args.ab:
        cmp = compare_ab(args.project, args.ab[0], args.ab[1], report=report)
        if args.json:
            print(json.dumps(cmp, ensure_ascii=False))
        else:
            print(f"A/B：{cmp['arm_a']['tag']} 率 {cmp['arm_a']['hit_rate']:.0%} "
                  f"vs {cmp['arm_b']['tag']} 率 {cmp['arm_b']['hit_rate']:.0%} "
                  f"→ 胜出：{cmp['winner'] or '并列/数据不足'}")
        return 0

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
