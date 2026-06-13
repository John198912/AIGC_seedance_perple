#!/usr/bin/env python3
"""逆向解构：参考作品 C12 → 特征标签集 C13（M1 · 设计稿 v5.0 第二部分）。

确定性、不触网、无 LLM/subagent。纯查表：
  - 结构层（content）轴：从 C12 annotations.structural 取值，查字典校验取值范围，
    命中即标 provenance=observed、confidence_tier=high、advisory=false（承重墙、可门控）；
  - ①②④（audience/scene/behavior）轴：从 annotations 取值，标 advisory=true、永不门控；
    无外部锚点则 provenance=inferred、confidence_tier=low（决策点4）；
  - 视觉 6 维复用 reference_analyzer 归一（仅作风格描述子片段，不作承重特征）。

CLI：
  python deconstruct.py --refs <C12.yaml/json> --out <C13.json> [--json]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str((Path(__file__).resolve().parent.parent.parent
                        / "_shared" / "scripts")))
sys.path.insert(0, str((Path(__file__).resolve().parent.parent.parent
                        / "prompt-compiler" / "scripts")))
from _common import read_yaml, write_json  # noqa: E402
import feature_dict as fd  # noqa: E402


def _visual_fragment(visual: dict[str, Any]) -> dict[str, list[str]]:
    """复用 reference_analyzer 视觉 6 维归一，产出风格描述子片段（非承重特征）。"""
    try:
        import reference_analyzer as ra
    except ImportError:
        return {}
    clip = {"annotations": visual or {}}
    analyzed = ra.analyze_clip(clip)
    return {k: v["values"] for k, v in analyzed["descriptors"].items() if v["values"]}


def deconstruct_one(ref: dict[str, Any],
                    dictionary: dict[str, Any] | None = None) -> dict[str, Any]:
    """对单条 C12 参考作品产出 C13 FeatureTagSet。"""
    d = dictionary or fd.load_dictionary()
    axes = d.get("axes", {})
    ann = ref.get("annotations", {}) or {}
    structural = ann.get("structural", {}) or {}
    features: list[dict[str, Any]] = []

    for axis_name, value in structural.items():
        if axis_name not in axes:
            continue  # 字典外轴忽略（v0 seed 冻结轴集合）
        meta = axes[axis_name]
        domain = meta["domain"]
        # 取值校验：不在字典 values 范围内则跳过（防臆造取值）
        if not fd.axis_value_valid(axis_name, value, d):
            continue
        if domain == "content":
            # 结构层：承重墙、observed/high、可门控
            features.append({
                "feature_axis": axis_name,
                "value": value,
                "domain": domain,
                "provenance": "observed",
                "confidence_tier": "high",
                "advisory": False,
                "source_refs": [ref["ref_id"]],
                "rationale": "结构层标注直接观测（承重墙）。",
            })
        else:
            # ①②④：顾问、永不门控；无外部锚点 → inferred/low
            features.append({
                "feature_axis": axis_name,
                "value": value,
                "domain": domain,
                "provenance": "inferred",
                "confidence_tier": "low",
                "advisory": True,
                "source_refs": [ref["ref_id"]],
                "rationale": "①②④ 顾问增强，无外部锚点封顶 inferred 地板、永不门控。",
            })

    result: dict[str, Any] = {
        "ref_id": ref["ref_id"],
        "title": ref.get("title", ""),
        "features": features,
    }
    visual = ann.get("visual", {})
    if visual:
        result["visual_fragment"] = _visual_fragment(visual)
    return result


def deconstruct(refs: list[dict[str, Any]],
                dictionary: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """批量解构多条 C12，返回多份 C13。"""
    d = dictionary or fd.load_dictionary()
    return [deconstruct_one(ref, d) for ref in refs]


def _load_refs(path: str | Path) -> list[dict[str, Any]]:
    data = read_yaml(path) or {}
    if isinstance(data, list):
        return data
    return data.get("reference_works") or data.get("refs") or []


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="逆向解构 C12 → C13（M1，确定性·不触网）")
    parser.add_argument("--refs", required=True, help="C12 参考作品文件（yaml/json）")
    parser.add_argument("--out", help="C13 输出路径（多条时写列表）")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    refs = _load_refs(args.refs)
    tagsets = deconstruct(refs)
    payload = tagsets[0] if len(tagsets) == 1 else tagsets
    if args.out:
        write_json(args.out, payload)
    if args.json:
        print(json.dumps(payload, ensure_ascii=False))
    else:
        print(f"解构完成：{len(tagsets)} 份 C13"
              + (f" -> {args.out}" if args.out else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
