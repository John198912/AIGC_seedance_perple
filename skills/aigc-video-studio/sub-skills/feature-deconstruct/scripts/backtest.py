#!/usr/bin/env python3
"""分层控混淆回测（逆向特征工程模块 M4 · 数据闭环）。

幸存者偏差硬规则（硬编码，非注释）：C15/池化基准只看得到已发布/已爆作品，数据被截断
→ **只做桶内（同账号×同时段桶×同题材桶）相对比较，禁用任何绝对完播/互动阈值**。
任何绝对阈值入参（abs_threshold）一律 raise ValueError 拒绝。

流程：stratify（按 bucket_key 分组，丢弃 bucket_incomplete）→ relative_compare（仅桶内
treatment vs control 的相对差）→ 贝叶斯判据（bayes_criterion）聚合产出决策。

确定性、不触网、无 LLM。中文 docstring。

CLI：
  python backtest.py --c15 perf_c15.json --axis hook_type --treatment shock_open \
      --metric completion_rate [--min-effect 0.02] [--json]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import channel_perf as cp  # noqa: E402
import bayes_criterion as bayes  # noqa: E402


def stratify(c15_list: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """按 bucket_key 分组；丢弃 bucket_incomplete 行（诚实边界）。"""
    strata: dict[str, list[dict[str, Any]]] = {}
    for c15 in c15_list:
        if c15.get("bucket_incomplete"):
            continue
        key = cp.bucket_key(c15)
        strata.setdefault(key, []).append(c15)
    return strata


def _has_axis_value(row: dict[str, Any], axis: str, treatment_value: str) -> bool:
    """该样本是否带某轴的 treatment 取值。

    兼容两种标注：行内 `axes`/`feature_tags` 字典（axis→value），或顶层同名键。
    """
    tags = row.get("axes") or row.get("feature_tags") or {}
    if isinstance(tags, dict) and tags.get(axis) is not None:
        return str(tags.get(axis)) == str(treatment_value)
    if axis in row:
        return str(row.get(axis)) == str(treatment_value)
    return False


def _metric(row: dict[str, Any], metric: str) -> float | None:
    m = row.get("axis_level_metrics", {}) or {}
    v = m.get(metric)
    return float(v) if isinstance(v, (int, float)) else None


def relative_compare(bucket_rows: list[dict[str, Any]], axis: str,
                     treatment_value: str, metric: str) -> dict[str, Any]:
    """**仅桶内**比较带某轴取值（treatment）vs 不带（control）在该 metric 上的相对差。

    返回 {treatment_n, control_n, treatment_mean, control_mean, abs_diff, rel_lift}。
    绝不与任何绝对阈值比较。
    """
    treat: list[float] = []
    control: list[float] = []
    for row in bucket_rows:
        val = _metric(row, metric)
        if val is None:
            continue
        if _has_axis_value(row, axis, treatment_value):
            treat.append(val)
        else:
            control.append(val)

    t_mean = sum(treat) / len(treat) if treat else None
    c_mean = sum(control) / len(control) if control else None
    abs_diff = None
    rel_lift = None
    if t_mean is not None and c_mean is not None:
        abs_diff = t_mean - c_mean
        rel_lift = (abs_diff / c_mean) if c_mean else None
    return {
        "treatment_n": len(treat),
        "control_n": len(control),
        "treatment_mean": t_mean,
        "control_mean": c_mean,
        "abs_diff": abs_diff,
        "rel_lift": rel_lift,
    }


def run_backtest(c15_list: list[dict[str, Any]], axis: str, treatment_value: str,
                 metric: str, *, abs_threshold: Any = None,
                 min_effect: float = 0.02, prior: dict[str, Any] | None = None) -> dict[str, Any]:
    """回测入口。abs_threshold 一律拒绝（幸存者偏差硬规则）。

    聚合各桶相对差 → 贝叶斯判据产出决策。返回
    {buckets_used, per_bucket[], pooled_effect, bayes:{...}, decision}。
    """
    if abs_threshold is not None:
        raise ValueError("禁用绝对阈值：幸存者偏差下只做桶内相对比较")

    strata = stratify(c15_list)
    per_bucket: list[dict[str, Any]] = []
    effects: list[float] = []
    for key, rows in strata.items():
        cmp = relative_compare(rows, axis, treatment_value, metric)
        cmp["bucket_key"] = key
        per_bucket.append(cmp)
        # 仅当桶内 treatment 与 control 都有样本，相对差才有意义
        if cmp["abs_diff"] is not None:
            effects.append(cmp["abs_diff"])

    pooled_effect = sum(effects) / len(effects) if effects else None
    bayes_res = bayes.evaluate(effects, min_effect=min_effect, prior=prior) if effects else None

    return {
        "axis": axis,
        "treatment_value": treatment_value,
        "metric": metric,
        "buckets_used": len(effects),
        "per_bucket": per_bucket,
        "pooled_effect": pooled_effect,
        "bayes": bayes_res,
        "decision": bayes_res["decision"] if bayes_res else "insufficient_hold",
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
        description="分层控混淆回测（M4，只桶内相对·禁绝对阈值·确定性）")
    parser.add_argument("--c15", required=True, help="C15 列表（json/yaml）")
    parser.add_argument("--axis", required=True)
    parser.add_argument("--treatment", required=True, help="treatment 轴取值")
    parser.add_argument("--metric", required=True, help="比较的 metric 名")
    parser.add_argument("--min-effect", type=float, default=0.02)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    c15_list = _load(args.c15)
    if isinstance(c15_list, dict):
        c15_list = c15_list.get("rows") or c15_list.get("c15") or []
    res = run_backtest(c15_list, args.axis, args.treatment, args.metric,
                       min_effect=args.min_effect)
    if args.json:
        print(json.dumps(res, ensure_ascii=False))
    else:
        print(f"回测 {args.axis}={args.treatment} on {args.metric}："
              f"{res['buckets_used']} 桶，pooled={res['pooled_effect']}，"
              f"决策 {res['decision']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
