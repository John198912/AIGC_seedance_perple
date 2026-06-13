#!/usr/bin/env python3
"""对标驱动顾问路径（逆向特征工程模块 M3 · concept-brief 顾问①②④）。

职责：把逆向产出的 C14 CreativeDNA / reverse-map 特征，转成 concept-brief 的
**对标驱动顾问建议**——仅覆盖受众①(target_audience)、场景②(viewing_scene)、
行为④(engagement hints)三类**顾问增强**轴；**永不进硬约束、永不门控、创作者可覆盖**。

硬规则承接 M2：
  - 每条建议的最终 provenance 过 provenance.final_tier 兜底（只由外部锚点决定）；
  - inferred 项标 advisory:true、gating:false；任何项 gating 恒为 false（顾问路径绝不门控）；
  - 行为域④即便有锚点也维持 advisory（承接 M2 forced inferred 精神）。

确定性、不触网、无 LLM。中文 docstring。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

# 接 M2 provenance（final_tier 兜底）：feature-deconstruct/scripts 与本目录平级。
sys.path.insert(0, str((Path(__file__).resolve().parent.parent.parent
                        / "feature-deconstruct" / "scripts")))
import provenance as prov  # noqa: E402

# 顾问轴 → 域映射（①②④）。轴名或显式 domain 字段均可命中。
_AXIS_DOMAIN = {
    "target_audience": "audience",
    "view_scene": "scene",
    "viewing_scene": "scene",
    "engagement_behavior": "behavior",
}
_ADVISORY_DOMAINS = {"audience", "scene", "behavior"}
_BEHAVIOR_DOMAIN = "behavior"

NOTE = "对标驱动顾问建议，永不门控，创作者可覆盖"


def _feature_domain(feat: dict[str, Any]) -> str | None:
    """判定一条特征属于哪个顾问域：优先显式 domain，否则按 feature_axis 名映射。"""
    dom = feat.get("domain")
    if dom in _ADVISORY_DOMAINS:
        return dom
    axis = feat.get("feature_axis") or feat.get("axis")
    return _AXIS_DOMAIN.get(axis)


def _iter_source_features(dna: dict[str, Any],
                          reverse_map: dict[str, Any] | None) -> list[dict[str, Any]]:
    """从 dna/reverse_map 收集候选特征条目（transferable_patterns / features / 各域列表）。"""
    feats: list[dict[str, Any]] = []
    for src in (dna or {}, reverse_map or {}):
        if not isinstance(src, dict):
            continue
        for key in ("transferable_patterns", "features", "all_features"):
            seq = src.get(key)
            if isinstance(seq, list):
                feats.extend(f for f in seq if isinstance(f, dict))
        # reverse_map 可能按域分桶（audience/scene/behavior）
        for dom in _ADVISORY_DOMAINS:
            seq = src.get(dom)
            if isinstance(seq, list):
                for f in seq:
                    if isinstance(f, dict):
                        feats.append({**f, "domain": dom})
    return feats


def build_advisory(dna: dict[str, Any],
                   reverse_map: dict[str, Any] | None = None) -> dict[str, Any]:
    """把 C14/reverse-map 的①②④域特征转成顾问建议（永不门控、可覆盖）。

    返回 {advisory_suggestions:[{axis,value,domain,provenance,advisory,overridable,
    gating,rationale}], note, count}。
    """
    suggestions: list[dict[str, Any]] = []
    for feat in _iter_source_features(dna, reverse_map):
        domain = _feature_domain(feat)
        if domain not in _ADVISORY_DOMAINS:
            continue  # 结构层③等非顾问轴不进顾问路径

        # 最终档过 final_tier 兜底（只由外部锚点决定）。
        tier = prov.final_tier(feat)
        # 行为域④即便有锚点也强制 advisory（承接 M2 forced inferred 精神）。
        if domain == _BEHAVIOR_DOMAIN:
            tier = prov.final_tier(feat)  # 档位仍诚实标注，但下方 advisory 恒 True

        suggestion = {
            "axis": feat.get("feature_axis") or feat.get("axis"),
            "value": feat.get("value"),
            "domain": domain,
            "provenance": tier,
            "advisory": True,          # 顾问路径恒为顾问增强
            "overridable": True,       # 创作者可覆盖
            "gating": False,           # 任何项 gating 恒为 false（永不门控）
            "rationale": feat.get("rationale") or feat.get("directive") or "",
        }
        suggestions.append(suggestion)

    return {
        "advisory_suggestions": suggestions,
        "count": len(suggestions),
        "note": NOTE,
    }


def merge_into_brief(brief: dict[str, Any], advisory: dict[str, Any]) -> dict[str, Any]:
    """把 advisory 建议挂到 brief 的 advisory_block 字段（新建，不覆盖既有任何字段）。

    返回新 dict；原 brief 的 logline/世界观/风格等一律不动。
    """
    out = dict(brief or {})
    out["advisory_block"] = advisory
    return out


def _load(path: str | None) -> dict[str, Any] | None:
    if not path:
        return None
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    if p.suffix in (".yaml", ".yml"):
        import yaml
        return yaml.safe_load(text)
    return json.loads(text)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="对标驱动顾问路径（M3，永不门控·确定性·不触网）")
    parser.add_argument("--dna", required=True, help="C14 CreativeDNA（json/yaml）")
    parser.add_argument("--reverse-map", help="可选 reverse-map（json/yaml）")
    parser.add_argument("--brief", help="可选 concept-brief，挂载 advisory_block 后输出")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    dna = _load(args.dna) or {}
    reverse_map = _load(args.reverse_map)
    advisory = build_advisory(dna, reverse_map)

    result: dict[str, Any] = advisory
    if args.brief:
        brief = _load(args.brief) or {}
        result = merge_into_brief(brief, advisory)

    if args.json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        print(f"顾问建议 {advisory['count']} 条（{NOTE}）")
        for s in advisory["advisory_suggestions"]:
            print(f"  ①②④ {s['domain']}.{s['axis']}={s['value']} "
                  f"[{s['provenance']}] advisory={s['advisory']} gating={s['gating']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
