#!/usr/bin/env python3
"""三级来源标记与锚点评估（逆向特征工程模块 M2 · 设计稿 v5.0 第七部分 / 决策点4）。

三级来源标记 observed / sourced / inferred。编造的定义 = 把 inferred 谎报为
observed/sourced；带诚实档位的推断合法。

硬规则（决策点4）：`inferred` 最终 confidence **只由外部锚点决定**——
  - sourced：source_refs 含 ≥2 独立来源（不同 source domain）；
  - observed：视频本体 / 第一方实绩；
  - inferred：无/不足外部源 → **封顶 inferred 地板、禁止升档**。
自产基率 / 标注 origin: llm 的来源**不算锚点**。

确定性、不触网、无 LLM。纯规则判定，可复现。
"""
from __future__ import annotations

from typing import Any

# 不算锚点的来源 origin（自产基率 / 另一 LLM）
_NON_ANCHOR_ORIGINS = {"llm", "self", "self_baseline", "model"}

# 三级档地板序（越往后越弱）
_PROVENANCE_ORDER = ["observed", "sourced", "inferred"]
MIN_INDEPENDENT_SOURCES = 2   # sourced 升档所需独立来源数


def _ref_origin(ref: Any) -> str:
    """取来源条目的 origin（dict 显式 origin 字段；纯字符串视为外部，origin=external）。"""
    if isinstance(ref, dict):
        return str(ref.get("origin", "external")).lower()
    return "external"


def _ref_domain(ref: Any) -> str:
    """取来源条目的 source domain（用于独立性判定）。

    dict 优先 source_domain/domain 字段；字符串取其裸值。
    """
    if isinstance(ref, dict):
        return str(ref.get("source_domain") or ref.get("domain") or ref.get("source") or "")
    return str(ref)


def is_valid_anchor(ref: Any) -> bool:
    """该来源是否构成外部锚点。自产基率 / origin:llm 一律不算锚点。"""
    if not ref:
        return False
    if _ref_origin(ref) in _NON_ANCHOR_ORIGINS:
        return False
    # 第一方实绩（origin: first_party）与外部来源均算锚点
    return bool(_ref_domain(ref))


def independent_anchor_count(source_refs: list[Any]) -> int:
    """统计独立外部锚点数（按不同 source domain 去重，排除非锚点来源）。"""
    domains: set[str] = set()
    for ref in source_refs or []:
        if is_valid_anchor(ref):
            domains.add(_ref_domain(ref))
    return len(domains)


def has_first_party_anchor(source_refs: list[Any]) -> bool:
    """是否含第一方实绩锚点（origin: first_party / C15）。"""
    for ref in source_refs or []:
        if isinstance(ref, dict) and str(ref.get("origin", "")).lower() == "first_party":
            return True
    return False


def final_tier(feature: dict[str, Any]) -> str:
    """最终 provenance 档：只由外部锚点决定（硬规则，禁止凭声明升档）。

    - 第一方实绩 / 视频本体观测 → observed；
    - ≥2 独立外部锚点 → 最多升至 sourced；
    - 否则 → 封顶 inferred 地板（无论声明为何，绝不升档）。
    """
    refs = feature.get("source_refs", []) or []
    claimed = feature.get("provenance", "inferred")

    # observed 仅在第一方实绩 / 显式视频本体观测时成立
    if has_first_party_anchor(refs):
        return "observed"
    if claimed == "observed" and feature.get("observed_from_video"):
        return "observed"

    # sourced 需 ≥2 独立外部锚点
    if independent_anchor_count(refs) >= MIN_INDEPENDENT_SOURCES:
        return "sourced"

    # 无/不足外部锚点 → 封顶 inferred 地板，禁止升档
    return "inferred"


def is_upgrade(from_tier: str, to_tier: str) -> bool:
    """to_tier 是否相对 from_tier 升档（observed > sourced > inferred）。"""
    try:
        return _PROVENANCE_ORDER.index(to_tier) < _PROVENANCE_ORDER.index(from_tier)
    except ValueError:
        return False


def apply_floor(feature: dict[str, Any]) -> dict[str, Any]:
    """把最终档写回特征；inferred 项标 advisory（永不门控）。返回新 dict。"""
    out = dict(feature)
    tier = final_tier(feature)
    out["provenance"] = tier
    if tier == "inferred":
        out["advisory"] = True
        # 无锚点时置信封顶 low
        out.setdefault("confidence_tier", "low")
        out["confidence_tier"] = "low"
    return out
