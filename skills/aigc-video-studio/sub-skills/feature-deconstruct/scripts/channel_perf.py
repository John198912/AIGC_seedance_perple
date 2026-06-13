#!/usr/bin/env python3
"""C15 ChannelPerformance 第一方实绩采集（逆向特征工程模块 M4 · 数据闭环）。

C15 = 第一方实绩锚点：
  - source **恒** first_party（无论 CSV 是否含该列），经 M2 provenance.has_first_party_anchor
    → observed（复用，勿改 provenance）；
  - **可选、永不门控**。

幸存者偏差硬规则（贯穿数据闭环）：只看得到已发布/已爆作品 → 只做桶内（同账号×同时段桶×
同题材桶）相对比较，禁用任何绝对完播/互动阈值；不强求逐场 retention。
诚实边界：缺 bucket 维度的行记 bucket_incomplete=true 并**排除出回测**。

确定性、不触网、无 LLM。手工/半自动 CSV 摄入（真实联网导出属运行时）。中文 docstring。

CLI：
  python channel_perf.py --csv perf.csv [--json]
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any

# 第一方实绩来源恒定
FIRST_PARTY = "first_party"
# bucket 必需的三维度
_BUCKET_KEYS = ("account", "time_bucket", "topic_bucket")
# CSV 中识别为 metric 的列（其余非 bucket/非元字段也并入 axis_level_metrics）
_META_COLS = {"project_id", "channel", "account", "time_bucket", "topic_bucket",
              "collected_at", "source"}


def _to_number(val: Any) -> Any:
    """尽量把 CSV 字符串转成数值；不可转则原样返回。"""
    if val is None or val == "":
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return val


def _row_to_c15(row: dict[str, Any]) -> dict[str, Any]:
    """单行 CSV → C15 对象。source 强制 first_party；缺 bucket 维度标 bucket_incomplete。"""
    bucket: dict[str, Any] = {}
    incomplete = False
    for k in _BUCKET_KEYS:
        v = row.get(k)
        if v is None or str(v).strip() == "":
            incomplete = True
        else:
            bucket[k] = str(v).strip()

    metrics: dict[str, Any] = {}
    for col, raw in row.items():
        if col in _META_COLS or col in _BUCKET_KEYS:
            continue
        num = _to_number(raw)
        if num is not None:
            metrics[col] = num

    c15: dict[str, Any] = {
        "project_id": str(row.get("project_id", "")).strip(),
        "channel": str(row.get("channel", "")).strip(),
        "axis_level_metrics": metrics,
        "bucket": bucket,
        "source": FIRST_PARTY,   # 硬编码：恒 first_party
    }
    if row.get("collected_at"):
        c15["collected_at"] = str(row["collected_at"]).strip()
    if incomplete:
        c15["bucket_incomplete"] = True
    return c15


def ingest_csv(path: str | Path) -> list[dict[str, Any]]:
    """读手工导出 CSV，逐行归一为 C15 对象列表（source 恒 first_party）。"""
    rows: list[dict[str, Any]] = []
    with Path(path).open(encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            rows.append(_row_to_c15(row))
    return rows


def bucket_key(c15: dict[str, Any]) -> str:
    """同账号×同时段桶×同题材桶的复合键。"""
    b = c15.get("bucket", {}) or {}
    return "|".join(str(b.get(k, "")) for k in _BUCKET_KEYS)


def as_anchor(c15: dict[str, Any]) -> dict[str, Any]:
    """产出可喂给 provenance 的 source_ref（origin:first_party → final_tier → observed）。"""
    return {"origin": FIRST_PARTY, "source_domain": f"c15:{c15.get('channel', '')}"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="C15 第一方实绩采集（M4，确定性·不触网，source 恒 first_party）")
    parser.add_argument("--csv", required=True, help="手工导出 CSV 路径")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    rows = ingest_csv(args.csv)
    incomplete = sum(1 for r in rows if r.get("bucket_incomplete"))
    if args.json:
        print(json.dumps(rows, ensure_ascii=False))
    else:
        print(f"C15 摄入 {len(rows)} 行（source 恒 first_party），"
              f"bucket 不全被排除回测 {incomplete} 行")
    return 0


if __name__ == "__main__":
    sys.exit(main())
