#!/usr/bin/env python3
"""轴发现机制（逆向特征工程模块 M4 · 数据闭环）。

背景：M1 已知"字典外轴取值被静默丢弃"。本机制把这些丢弃项当作**发现素材**：
扫一批 C13 特征，凡 feature_axis 不在字典 axes 内的，按 axis 名聚合计数与样例取值；
计数 ≥ min_support 的候选轴产出提案。

硬规则：**只提案不自动写字典**（人工闸）；提案 status 恒为 candidate；批量进新 major
（轴集合在一个 major 内冻结，见 dict_versioning）。

确定性、不触网、无 LLM。中文 docstring。

CLI：
  python axis_discovery.py --c13 batch.json [--min-support 3] [--json]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str((Path(__file__).resolve().parent.parent.parent
                        / "_shared" / "scripts")))
from _common import load_lib  # noqa: E402

DICTIONARY_LIB = "feature-dictionary.yaml"


def _dictionary_axes(dictionary: dict[str, Any]) -> set[str]:
    return set((dictionary.get("axes") or {}).keys())


def _iter_features(c13_batch: Any) -> list[dict[str, Any]]:
    """从一批 C13（list 或单个 dict，含 features[]）里展开所有特征条目。"""
    feats: list[dict[str, Any]] = []
    batch = c13_batch if isinstance(c13_batch, list) else [c13_batch]
    for c13 in batch:
        if not isinstance(c13, dict):
            continue
        for f in (c13.get("features") or []):
            if isinstance(f, dict):
                feats.append(f)
    return feats


def collect_unknown(c13_batch: Any,
                    dictionary: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """扫一批 C13，聚合字典外轴的计数与样例取值。

    返回 {candidate_axis -> {count, sample_values[]}}。
    """
    known = _dictionary_axes(dictionary)
    unknown: dict[str, dict[str, Any]] = {}
    for feat in _iter_features(c13_batch):
        axis = feat.get("feature_axis")
        if not axis or axis in known:
            continue
        slot = unknown.setdefault(axis, {"count": 0, "sample_values": []})
        slot["count"] += 1
        val = feat.get("value")
        if val is not None and val not in slot["sample_values"]:
            slot["sample_values"].append(val)
    return unknown


def propose_axes(unknown: dict[str, dict[str, Any]], *,
                 min_support: int = 3) -> list[dict[str, Any]]:
    """计数 ≥ min_support 的候选轴产出提案（只提案不写字典，人工闸）。"""
    proposals: list[dict[str, Any]] = []
    for axis, info in sorted(unknown.items()):
        if info["count"] < min_support:
            continue
        proposals.append({
            "candidate_axis": axis,
            "support": info["count"],
            "sample_values": list(info["sample_values"]),
            "suggested_domain": "content",   # 默认提案为结构层，待人工确认
            "status": "candidate",            # 恒 candidate，不自动写字典
            "note": "批量进新 major，需人工确认",
        })
    return proposals


def discover(c13_batch: Any, dictionary: dict[str, Any] | None = None, *,
             min_support: int = 3) -> dict[str, Any]:
    """便捷入口：collect_unknown + propose_axes。"""
    dictionary = dictionary if dictionary is not None else load_lib(DICTIONARY_LIB)
    unknown = collect_unknown(c13_batch, dictionary)
    proposals = propose_axes(unknown, min_support=min_support)
    return {"min_support": min_support, "unknown_axes": unknown, "proposals": proposals,
            "auto_write_dictionary": False}


def _load(path: str) -> Any:
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    if p.suffix in (".yaml", ".yml"):
        import yaml
        return yaml.safe_load(text)
    return json.loads(text)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="轴发现（M4，只提案不写字典·确定性）")
    parser.add_argument("--c13", required=True, help="一批 C13（json/yaml）")
    parser.add_argument("--min-support", type=int, default=3)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    res = discover(_load(args.c13), min_support=args.min_support)
    if args.json:
        print(json.dumps(res, ensure_ascii=False))
    else:
        print(f"字典外轴 {len(res['unknown_axes'])} 个，"
              f"达 min_support={args.min_support} 提案 {len(res['proposals'])} 个"
              f"（只提案不写字典）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
