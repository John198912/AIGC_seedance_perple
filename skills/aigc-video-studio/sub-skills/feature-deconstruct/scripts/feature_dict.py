#!/usr/bin/env python3
"""特征字典加载/校验/约束查询（逆向特征工程模块 M1 · 设计稿 v5.0 第三部分）。

职责：
  - 加载并校验 feature-dictionary.yaml（轴元数据）与 axis-constraints.yaml（稀疏冲突规则）；
  - get_axis(name)：取某轴元数据（domain/gating/signal_kind/information/maps_to/values）；
  - is_gating(axis)：该轴是否可门控（仅结构层 content 轴 gating:true）；
  - check_coherence(selected)：对一组 (axis, value) 选定组合查 axis-constraints 命中冲突。

确定性、不触网、无 LLM。所有规则纯查表，可复现。

CLI：
  python feature_dict.py --list                 # 列出全部轴与元数据摘要
  python feature_dict.py --axis hook_type --json # 单轴元数据
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

DICT_FILE = "feature-dictionary.yaml"
CONSTRAINTS_FILE = "axis-constraints.yaml"

# 字典每轴必备元数据字段（校验用）
_REQUIRED_AXIS_FIELDS = ("domain", "gating", "signal_kind", "information", "maps_to", "values")
_VALID_SIGNAL_KIND = {"leading", "lagging"}
_VALID_INFORMATION = {"high", "low"}
_VALID_RELATION = {"conflict", "weak_conflict", "requires"}


def load_dictionary() -> dict[str, Any]:
    """加载并校验 feature-dictionary.yaml；缺字段/坏取值即抛 ValueError。"""
    data = load_lib(DICT_FILE) or {}
    axes = data.get("axes") or {}
    if not axes:
        raise ValueError(f"{DICT_FILE} 缺少 axes")
    for name, meta in axes.items():
        for field in _REQUIRED_AXIS_FIELDS:
            if field not in meta:
                raise ValueError(f"轴 {name} 缺少元数据字段：{field}")
        if not isinstance(meta["gating"], bool):
            raise ValueError(f"轴 {name} 的 gating 必须为 bool")
        if meta["signal_kind"] not in _VALID_SIGNAL_KIND:
            raise ValueError(f"轴 {name} signal_kind 非法：{meta['signal_kind']}")
        if meta["information"] not in _VALID_INFORMATION:
            raise ValueError(f"轴 {name} information 非法：{meta['information']}")
        if not isinstance(meta["maps_to"], list) or not meta["maps_to"]:
            raise ValueError(f"轴 {name} maps_to 必须为非空列表")
        if not isinstance(meta["values"], list) or not meta["values"]:
            raise ValueError(f"轴 {name} values 必须为非空列表")
    return data


def load_constraints() -> list[dict[str, Any]]:
    """加载并校验 axis-constraints.yaml，返回 constraints 列表。"""
    data = load_lib(CONSTRAINTS_FILE) or {}
    constraints = data.get("constraints") or []
    for c in constraints:
        axes = c.get("axes")
        if not isinstance(axes, list) or len(axes) != 2:
            raise ValueError(f"约束 axes 必须为长度 2 的列表：{c}")
        if c.get("relation") not in _VALID_RELATION:
            raise ValueError(f"约束 relation 非法：{c.get('relation')}")
    return constraints


def get_axis(name: str, dictionary: dict[str, Any] | None = None) -> dict[str, Any]:
    """取某轴元数据；未知轴抛 KeyError。"""
    d = dictionary or load_dictionary()
    axes = d.get("axes", {})
    if name not in axes:
        raise KeyError(f"未知轴：{name}（可用：{', '.join(axes)}）")
    return axes[name]


def is_gating(name: str, dictionary: dict[str, Any] | None = None) -> bool:
    """该轴是否可门控（仅结构层 content 轴 gating:true）。"""
    return bool(get_axis(name, dictionary).get("gating", False))


def axis_value_valid(name: str, value: str, dictionary: dict[str, Any] | None = None) -> bool:
    """value 是否在该轴 values 取值范围内。"""
    return value in get_axis(name, dictionary).get("values", [])


def _selected_key(axis: str, value: str) -> str:
    return f"{axis}.{value}"


def check_coherence(selected: list[tuple[str, str] | dict[str, str]],
                    constraints: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    """对一组选定 (axis, value) 查 axis-constraints，返回命中的冲突规则列表。

    selected 元素可为 (axis, value) 元组或 {"feature_axis"/"axis", "value"} 字典。
    命中判定：约束的两个 axis.value 锚点都出现在选定集合中。
    """
    rules = constraints if constraints is not None else load_constraints()
    keys: set[str] = set()
    for item in selected:
        if isinstance(item, dict):
            axis = item.get("feature_axis") or item.get("axis")
            value = item.get("value")
        else:
            axis, value = item
        if axis and value:
            keys.add(_selected_key(axis, value))

    hits: list[dict[str, Any]] = []
    for rule in rules:
        a, b = rule["axes"]
        if a in keys and b in keys:
            hits.append({"axes": [a, b], "relation": rule["relation"],
                         "note": rule.get("note", "")})
    return hits


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="特征字典加载/校验/约束查询（M1）")
    parser.add_argument("--list", action="store_true", help="列出全部轴")
    parser.add_argument("--axis", help="查询单轴元数据")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    d = load_dictionary()
    if args.axis:
        meta = get_axis(args.axis, d)
        if args.json:
            print(json.dumps({"axis": args.axis, **meta}, ensure_ascii=False))
        else:
            print(f"{args.axis}（{meta.get('label_zh', '')}）domain={meta['domain']} "
                  f"gating={meta['gating']} signal={meta['signal_kind']} "
                  f"info={meta['information']} maps_to={meta['maps_to']}")
            print(f"  values: {meta['values']}")
        return 0

    axes = d.get("axes", {})
    if args.json:
        print(json.dumps({"version": d.get("version"), "axes": list(axes)},
                         ensure_ascii=False))
    else:
        print(f"feature-dictionary {d.get('version')}（{len(axes)} 轴）")
        for name, meta in axes.items():
            gate = "门控" if meta["gating"] else "顾问"
            print(f"  - {name}（{meta.get('label_zh', '')}）[{meta['domain']}/{gate}]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
