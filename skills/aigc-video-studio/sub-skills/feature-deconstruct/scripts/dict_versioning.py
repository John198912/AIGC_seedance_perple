#!/usr/bin/env python3
"""版本化字典发布（逆向特征工程模块 M4 · 数据闭环 · semver）。

版本化纪律（硬编码为规则）：
  - **增删轴 = major**；**仅权重/元数据调（同一轴集合内）= minor**；无变 = patch/none；
  - **轴集合在一个 major 内冻结**：minor 内不得增删轴 → 若 classify 出 added/removed
    却要 minor bump，raise；
  - 轴发现批量进新 major 时，diff_new_vs_existing **只 diff 新轴 × 既有轴**的稀疏冲突
    候选（配合 axis-constraints 稀疏增量），不重导稠密矩阵；
  - publish **不直接写盘覆盖 lib**（返回拟发布版，人工确认）。

确定性、不触网、无 LLM。中文 docstring。

CLI：
  python dict_versioning.py --old old_dict.yaml --new new_dict.yaml [--json]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

_VERSION_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)(?:-(.+))?$")


def parse_version(v: str) -> tuple[int, int, int, str | None]:
    """解析如 '0.1.0-seed' → (0, 1, 0, 'seed')。"""
    m = _VERSION_RE.match(str(v).strip())
    if not m:
        raise ValueError(f"非法版本号：{v}（期望 major.minor.patch[-tag]）")
    major, minor, patch = int(m.group(1)), int(m.group(2)), int(m.group(3))
    return major, minor, patch, m.group(4)


def _axes(d: dict[str, Any]) -> dict[str, Any]:
    return d.get("axes") or {}


def classify_change(old_dict: dict[str, Any], new_dict: dict[str, Any]) -> dict[str, Any]:
    """对比 axes 键集合与权重/元数据，判定 change_type。

    轴集合变（增删轴）= major；仅权重/元数据调 = minor；无变 = none。
    返回 {change_type, added_axes[], removed_axes[], modified_axes[]}。
    """
    old_axes, new_axes = _axes(old_dict), _axes(new_dict)
    old_keys, new_keys = set(old_axes), set(new_axes)

    added = sorted(new_keys - old_keys)
    removed = sorted(old_keys - new_keys)
    modified = sorted(
        k for k in (old_keys & new_keys) if old_axes.get(k) != new_axes.get(k))

    if added or removed:
        change_type = "major"
    elif modified:
        change_type = "minor"
    else:
        change_type = "none"

    return {"change_type": change_type, "added_axes": added,
            "removed_axes": removed, "modified_axes": modified}


def bump(old_version: str, change_type: str, *, added_or_removed: bool = False) -> str:
    """按 semver 规则升版；轴集合在一个 major 内冻结。

    若 change_type=minor 却伴随增删轴（added_or_removed=True）→ raise（违反冻结）。
    """
    major, minor, patch, tag = parse_version(old_version)
    if change_type == "major":
        return f"{major + 1}.0.0"
    if change_type == "minor":
        if added_or_removed:
            raise ValueError("轴集合在一个 major 内冻结：minor 内不得增删轴")
        return f"{major}.{minor + 1}.0"
    if change_type in ("patch", "none"):
        return f"{major}.{minor}.{patch + 1}"
    raise ValueError(f"未知 change_type：{change_type}")


def diff_new_vs_existing(old_dict: dict[str, Any],
                         new_dict: dict[str, Any]) -> list[dict[str, Any]]:
    """轴发现批量进新 major 时，只 diff 新轴 × 既有轴的稀疏冲突候选。

    返回 [{new_axis, existing_axis}]，不重导稠密矩阵（不含既有轴两两组合）。
    """
    cls = classify_change(old_dict, new_dict)
    new_axes = cls["added_axes"]
    existing = sorted(set(_axes(old_dict)))
    pairs: list[dict[str, Any]] = []
    for na in new_axes:
        for ea in existing:
            pairs.append({"new_axis": na, "existing_axis": ea})
    return pairs


def publish(old_dict: dict[str, Any], new_dict: dict[str, Any]) -> dict[str, Any]:
    """计算 change_type → bump version → 产出发布记录（不写盘覆盖 lib，人工确认）。"""
    cls = classify_change(old_dict, new_dict)
    from_version = str(old_dict.get("version", "0.0.0"))
    added_or_removed = bool(cls["added_axes"] or cls["removed_axes"])

    # 轴集合冻结校验：minor 内禁增删轴
    axis_set_frozen_ok = True
    try:
        to_version = bump(from_version, cls["change_type"],
                          added_or_removed=added_or_removed)
    except ValueError:
        # 理论上仅当 classify=minor 却有增删轴时触发；此处按 major 兜底并标记
        axis_set_frozen_ok = False
        to_version = bump(from_version, "major")

    diffs = diff_new_vs_existing(old_dict, new_dict) if cls["change_type"] == "major" else []

    return {
        "from_version": from_version,
        "to_version": to_version,
        "change_type": cls["change_type"],
        "added_axes": cls["added_axes"],
        "removed_axes": cls["removed_axes"],
        "modified_axes": cls["modified_axes"],
        "axis_set_frozen_ok": axis_set_frozen_ok,
        "diffs": diffs,
        "written_to_disk": False,   # 不直接覆盖 lib，人工确认
    }


def _load(path: str) -> Any:
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    if p.suffix in (".yaml", ".yml"):
        import yaml
        return yaml.safe_load(text)
    return json.loads(text)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="版本化字典发布（M4，semver·轴集合冻结·不自动写盘）")
    parser.add_argument("--old", required=True, help="旧字典（yaml/json）")
    parser.add_argument("--new", required=True, help="新字典（yaml/json）")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    rec = publish(_load(args.old), _load(args.new))
    if args.json:
        print(json.dumps(rec, ensure_ascii=False))
    else:
        print(f"{rec['from_version']} → {rec['to_version']}（{rec['change_type']}），"
              f"增 {rec['added_axes']} 删 {rec['removed_axes']}，"
              f"轴集合冻结 ok={rec['axis_set_frozen_ok']}（未写盘，待人工确认）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
