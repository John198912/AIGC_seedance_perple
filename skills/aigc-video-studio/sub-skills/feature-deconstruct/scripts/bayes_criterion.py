#!/usr/bin/env python3
"""贝叶斯判据（逆向特征工程模块 M4 · 数据闭环 · 非频率派）。

对桶内相对效应样本做确定性的贝叶斯近似（Normal 共轭，纯算术、无随机），产出：
  - 后验均值 + 后验可信区间（默认 90%）；
  - **双门槛**决策：后验区间下界 > min_effect 且后验均值 > min_effect → 候选采纳；
    后验区间上界 < 0 → 候选淘汰；否则证据不足维持；
  - **显式损失函数**：比较采纳损失期望 vs 淘汰损失期望，输出 recommended_action；
  - 定性"贝叶斯置信档" confidence_band（基于后验区间宽度与位置）。

先验：有 C15/基准方向性先验则用之；否则无信息（弱）先验。
说明：此处贝叶斯是真实数值计算（基于 C15 真实计数），不属"伪精度浮点"禁令；
但 confidence_band 必须是定性档。

确定性、不触网、无 LLM。中文 docstring。

CLI：
  python bayes_criterion.py --effects 0.1 0.2 0.05 --min-effect 0.02 [--json]
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from typing import Any

# 90% 可信区间对应的正态分位（双侧 → z≈1.645）
_Z_90 = 1.6448536269514722

CONFIDENCE_BANDS = [
    "strong_adopt", "lean_adopt", "insufficient", "lean_retire", "strong_retire",
]


def _mean(xs: list[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def posterior(effects: list[float], *, prior: dict[str, Any] | None = None,
              credible: float = 0.90) -> dict[str, Any]:
    """对相对效应样本做 Normal 共轭后验近似（确定性）。

    prior（可选）：{"mean": m0, "var": v0, "strength": k0}。无 prior → 无信息弱先验
    （k0=0，后验由数据主导）。返回后验均值 / 方差 / 可信区间。
    """
    n = len(effects)
    data_mean = _mean(effects)
    # 样本方差（无偏；n<2 时退化为一个保守的单位方差，避免零方差假象）
    if n >= 2:
        data_var = sum((x - data_mean) ** 2 for x in effects) / (n - 1)
    else:
        data_var = 1.0
    data_var = max(data_var, 1e-9)

    if prior:
        m0 = float(prior.get("mean", 0.0))
        v0 = float(prior.get("var", 1.0))
        k0 = float(prior.get("strength", 1.0))
    else:
        # 无信息弱先验：强度 0 → 数据主导
        m0, v0, k0 = 0.0, 1.0, 0.0

    # 后验均值：先验伪计数 k0 与 n 个数据点的精度加权平均
    post_mean = (k0 * m0 + n * data_mean) / (k0 + n) if (k0 + n) > 0 else data_mean
    # 后验对均值的方差 ≈ 数据方差 / 有效样本量
    eff_n = k0 + n
    post_var = data_var / eff_n if eff_n > 0 else data_var
    sd = math.sqrt(post_var)

    # 可信区间（默认 90%，z≈1.645）
    z = _Z_90 if abs(credible - 0.90) < 1e-9 else _z_for(credible)
    lo = post_mean - z * sd
    hi = post_mean + z * sd
    return {
        "n": n,
        "post_mean": post_mean,
        "post_var": post_var,
        "post_sd": sd,
        "credible": credible,
        "ci_low": lo,
        "ci_high": hi,
        "prior_used": bool(prior),
    }


def _z_for(credible: float) -> float:
    """少量常用置信度的 z 值查表（确定性，避免引入 scipy）。"""
    table = {0.80: 1.2815515594, 0.90: 1.6448536270,
             0.95: 1.9599639845, 0.99: 2.5758293035}
    # 取最接近的档
    key = min(table, key=lambda k: abs(k - credible))
    return table[key]


def _band(post: dict[str, Any], min_effect: float) -> str:
    """由后验区间位置/宽度定出定性置信档。"""
    lo, hi, mean = post["ci_low"], post["ci_high"], post["post_mean"]
    if lo > min_effect:
        # 整个区间在正向门槛之上
        return "strong_adopt" if lo > min_effect and mean > 2 * min_effect else "lean_adopt"
    if hi < 0:
        return "strong_retire" if hi < -min_effect else "lean_retire"
    return "insufficient"


def decide(post: dict[str, Any], *, min_effect: float,
           loss_adopt: float = 1.0, loss_retire: float = 1.0) -> dict[str, Any]:
    """双门槛 + 显式损失函数决策。

    - 采纳：后验区间下界 > min_effect 且后验均值 > min_effect；
    - 淘汰：后验区间上界 < 0；
    - 否则：证据不足维持。
    损失函数：采纳损失期望（效应低于门槛的负贡献）vs 淘汰损失期望（错失正效应），
    取期望损失更小者为 recommended_action。
    """
    lo, hi, mean = post["ci_low"], post["ci_high"], post["post_mean"]

    adopt = lo > min_effect and mean > min_effect
    retire = hi < 0

    # 显式损失：采纳的期望损失 ∝ 低于门槛的程度；淘汰的期望损失 ∝ 错失的正效应。
    expected_loss_adopt = loss_adopt * max(0.0, min_effect - mean)
    expected_loss_retire = loss_retire * max(0.0, mean)
    if expected_loss_adopt < expected_loss_retire:
        recommended_action = "adopt"
    elif expected_loss_retire < expected_loss_adopt:
        recommended_action = "retire"
    else:
        recommended_action = "hold"

    if adopt:
        decision = "candidate_adopt"
    elif retire:
        decision = "candidate_retire"
    else:
        decision = "insufficient_hold"

    return {
        "decision": decision,
        "min_effect": min_effect,
        "adopt_gate_passed": adopt,
        "retire_gate_passed": retire,
        "expected_loss_adopt": expected_loss_adopt,
        "expected_loss_retire": expected_loss_retire,
        "recommended_action": recommended_action,
        "confidence_band": _band(post, min_effect),
    }


def evaluate(effects: list[float], *, min_effect: float, prior: dict[str, Any] | None = None,
             loss_adopt: float = 1.0, loss_retire: float = 1.0,
             credible: float = 0.90) -> dict[str, Any]:
    """便捷入口：posterior + decide 合并返回。"""
    post = posterior(effects, prior=prior, credible=credible)
    dec = decide(post, min_effect=min_effect, loss_adopt=loss_adopt, loss_retire=loss_retire)
    return {"posterior": post, **dec}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="贝叶斯判据（M4，确定性·非频率派）")
    parser.add_argument("--effects", nargs="+", type=float, required=True,
                        help="桶内相对效应样本")
    parser.add_argument("--min-effect", type=float, default=0.02, help="最小效应量门槛")
    parser.add_argument("--loss-adopt", type=float, default=1.0)
    parser.add_argument("--loss-retire", type=float, default=1.0)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    res = evaluate(args.effects, min_effect=args.min_effect,
                   loss_adopt=args.loss_adopt, loss_retire=args.loss_retire)
    if args.json:
        print(json.dumps(res, ensure_ascii=False))
    else:
        p = res["posterior"]
        print(f"后验均值 {p['post_mean']:.4f}，{int(p['credible']*100)}% 区间 "
              f"[{p['ci_low']:.4f}, {p['ci_high']:.4f}]")
        print(f"决策 {res['decision']}，置信档 {res['confidence_band']}，"
              f"建议 {res['recommended_action']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
