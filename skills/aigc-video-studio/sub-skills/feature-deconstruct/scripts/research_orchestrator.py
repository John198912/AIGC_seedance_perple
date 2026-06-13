#!/usr/bin/env python3
"""4 路研究编排（受众/场景/内容/行为）确定性 mock（逆向特征工程模块 M2 · 设计稿第七部分）。

真实运行时由 4 路 subagent 联网研究（接线见 SKILL.md，属运行时）；本脚本是
**确定性 mock**，不真正调用 subagent/LLM/网络，便于测试与离线编排骨架。

防幻觉契约（硬规则）：
  - 每条产出特征必须带 source_refs；
  - 零来源 → 标 provenance: inferred + unverifiable: true，**绝不伪造 observed/sourced**；
  - 行为域④即便有 mock 来源也强制走 inferred（行为信号不可由解构直接观测）；
  - 最终档一律过 provenance.final_tier 兜底（只由外部锚点决定）。

CLI：
  python research_orchestrator.py --refs <C12/C13 yaml/json> --json
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

# 4 路研究域 → 字典 domain
ROUTES = {
    "audience": "audience",     # ① 受众
    "scene": "scene",           # ② 场景
    "content": "content",       # 结构层（承重）
    "behavior": "behavior",     # ④ 行为（强制 inferred）
}

# 行为域④：即便 mock 有来源也强制 inferred（不可由解构直接观测）
_FORCE_INFERRED_DOMAINS = {"behavior"}


def _normalize_feature(raw: dict[str, Any], domain: str) -> dict[str, Any]:
    """把一条 mock 研究产出归一为带防幻觉标记的特征。"""
    source_refs = list(raw.get("source_refs", []) or [])
    feat: dict[str, Any] = {
        "feature_axis": raw.get("feature_axis", ""),
        "value": raw.get("value", ""),
        "domain": domain,
        "source_refs": source_refs,
        "rationale": raw.get("rationale", ""),
        "inference_method": raw.get("inference_method", "mock_research"),
    }

    if not source_refs:
        # 零来源：绝不伪造 observed/sourced
        feat["provenance"] = "inferred"
        feat["unverifiable"] = True
        feat["confidence_tier"] = "low"
        feat["advisory"] = True
        return feat

    # 有来源：先按声明，再过 final_tier 兜底（只由外部锚点决定）
    feat["provenance"] = raw.get("provenance", "inferred")
    feat["confidence_tier"] = raw.get("confidence_tier", "med")
    feat = prov.apply_floor(feat)

    # 行为域④：强制 inferred（即便有锚点）
    if domain in _FORCE_INFERRED_DOMAINS:
        feat["provenance"] = "inferred"
        feat["advisory"] = True
        feat["confidence_tier"] = "low"
        feat["forced_inferred"] = True
    return feat


def orchestrate(research_inputs: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    """对 4 路输入做编排，返回 {routes:{域:[特征]}, all_features:[...]}。

    research_inputs：{route: [raw_feature, ...]}；缺省路视为零产出。
    """
    routes_out: dict[str, list[dict[str, Any]]] = {}
    all_features: list[dict[str, Any]] = []
    for route, domain in ROUTES.items():
        raws = research_inputs.get(route, []) or []
        feats = [_normalize_feature(r, domain) for r in raws]
        routes_out[route] = feats
        all_features.extend(feats)
    return {
        "mock": True,
        "routes": routes_out,
        "all_features": all_features,
        "unverifiable_count": sum(1 for f in all_features if f.get("unverifiable")),
    }


def _mock_inputs_from_refs(refs: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """从参考记录派生确定性 mock 研究输入（骨架；真实由 subagent 取代）。

    内容域取 refs 的 structural 标注（带 ref_id 锚点）；①②④给零来源 mock 条目
    以演示防幻觉路径（unverifiable）。
    """
    content: list[dict[str, Any]] = []
    for ref in refs:
        ref_id = ref.get("ref_id", "")
        structural = (ref.get("annotations", {}) or {}).get("structural", {}) or {}
        for axis, value in structural.items():
            content.append({
                "feature_axis": axis, "value": value,
                "source_refs": [{"source_domain": ref_id, "origin": "external"}],
                "provenance": "observed", "observed_from_video": True,
                "rationale": "结构层解构观测",
            })
    # ①②④：零来源 mock（演示 unverifiable，绝不伪造）
    advisory = {
        "audience": [{"feature_axis": "target_audience", "value": "young_male_18_24",
                      "source_refs": []}],
        "scene": [{"feature_axis": "view_scene", "value": "bedtime_fragment",
                   "source_refs": []}],
        "behavior": [{"feature_axis": "engagement_behavior", "value": "rewatch_loop",
                      "source_refs": [{"source_domain": "mock_a", "origin": "external"}]}],
    }
    return {"content": content, **advisory}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="4 路研究编排（M2，确定性 mock·不触网）")
    parser.add_argument("--refs", required=True, help="C12/C13 参考文件（yaml/json）")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    data = read_yaml(args.refs) or {}
    refs = data if isinstance(data, list) else (
        data.get("reference_works") or data.get("refs") or [])
    result = orchestrate(_mock_inputs_from_refs(refs))

    if args.json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        print(f"4 路研究编排（mock）：{len(result['all_features'])} 条特征，"
              f"unverifiable {result['unverifiable_count']} 条")
    return 0


if __name__ == "__main__":
    sys.exit(main())
