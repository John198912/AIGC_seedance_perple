#!/usr/bin/env python3
"""对抗校验（确定性 mock · 逆向特征工程模块 M2 · 设计稿第七部分 / 决策点4）。

流程：subagent-A 提 inferred 特征 + rationale → subagent-B 红队（内部一致性 / 基率检验）
→ 收敛。真实由两路 subagent 接线（见 SKILL.md），本脚本为**确定性 mock**。

硬规则（决策点4）：
  - 轮数封 1–2（MAX_ROUNDS）；
  - **无外部锚点时多轮只做内部一致性剪枝、绝不升档**（最终档过 provenance.final_tier 兜底）；
  - 自产基率 / 另一 LLM 不算锚点；
  - 输出保留异议（objections）与 inference_method。

确定性、不触网、无 LLM。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str((Path(__file__).resolve().parent.parent.parent
                        / "_shared" / "scripts")))
from _common import read_yaml  # noqa: E402
import provenance as prov  # noqa: E402

MAX_ROUNDS = 2   # 轮数封顶 1–2


def _red_team(feature: dict[str, Any]) -> list[str]:
    """subagent-B 红队（mock）：内部一致性 / 基率检验，确定性产出异议列表。"""
    objections: list[str] = []
    # 内部一致性：value 缺失 / rationale 缺失
    if not feature.get("value"):
        objections.append("value 缺失，无法核验")
    if not feature.get("rationale"):
        objections.append("缺 rationale，基率检验不通过")
    # 基率检验：零锚点却声明高档 = 过度自信
    if prov.independent_anchor_count(feature.get("source_refs", [])) == 0 \
            and feature.get("provenance") in ("observed", "sourced"):
        objections.append("零外部锚点却声明 observed/sourced，基率检验判过度自信")
    return objections


def check_feature(feature: dict[str, Any], max_rounds: int = MAX_ROUNDS) -> dict[str, Any]:
    """对单条 inferred 特征跑对抗校验，返回收敛结果（保留异议，绝不升档）。"""
    rounds = max(1, min(max_rounds, MAX_ROUNDS))
    anchor_count = prov.independent_anchor_count(feature.get("source_refs", []))
    has_anchor = anchor_count > 0 or prov.has_first_party_anchor(
        feature.get("source_refs", []))

    tier_before = feature.get("provenance", "inferred")
    all_objections: list[str] = []
    current = dict(feature)
    rounds_run = 0
    for _ in range(rounds):
        rounds_run += 1
        objs = _red_team(current)
        all_objections.extend(objs)
        # 内部一致性剪枝：异议存在则降置信，绝不升档
        if objs:
            current["confidence_tier"] = "low"
        # 无外部锚点：多轮只剪枝、不升档；有异议解决也不提前停以演示封顶
        if has_anchor and not objs:
            break

    # 最终档兜底：只由外部锚点决定（封顶 inferred 地板，禁止凭声明升档）。
    # final_tier 是唯一授权升档的依据——无锚点时它已封顶 inferred，故此处无需再额外压制。
    # 硬规则保险：无外部锚点时绝不离开 inferred 地板。
    tier_after = prov.final_tier(current)
    if not has_anchor and prov.is_upgrade(tier_before, tier_after):
        tier_after = tier_before

    current["provenance"] = tier_after
    if tier_after == "inferred":
        current["advisory"] = True
    return {
        "feature": current,
        "rounds": rounds_run,
        "has_external_anchor": has_anchor,
        "anchor_count": anchor_count,
        "tier_before": tier_before,
        "tier_after": tier_after,
        "upgraded": prov.is_upgrade(tier_before, tier_after),
        "objections": sorted(set(all_objections)),
        "inference_method": current.get("inference_method", "adversarial_mock"),
        "pruned_only": not has_anchor,
    }


def check_many(features: list[dict[str, Any]],
               max_rounds: int = MAX_ROUNDS) -> dict[str, Any]:
    results = [check_feature(f, max_rounds) for f in features]
    return {
        "mock": True,
        "results": results,
        "any_upgraded": any(r["upgraded"] for r in results),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="对抗校验（M2，确定性 mock·不触网）")
    parser.add_argument("--refs", required=True, help="待校验特征列表（yaml/json）")
    parser.add_argument("--rounds", type=int, default=MAX_ROUNDS)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    data = read_yaml(args.refs) or {}
    feats = data if isinstance(data, list) else (
        data.get("features") or data.get("all_features") or [])
    result = check_many(feats, args.rounds)

    if args.json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        up = "有升档" if result["any_upgraded"] else "无升档"
        print(f"对抗校验（mock）：{len(result['results'])} 条，{up}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
