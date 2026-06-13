#!/usr/bin/env python3
"""日落条款 + TTL 领先/滞后衰减（逆向特征工程模块 M4 · 数据闭环）。

日落 / 休眠纪律（硬编码为规则）：
  - 累计 N 项目证据仍停留无信息先验（insufficient）→ **弱负面信号、降优先级**；
  - 判退役/休眠时：**结构层（content）轴只 hibernate（status:hibernate），绝不 retire；
    ①②④顾问轴（audience/scene/behavior）证据长期不足可 retire**。

TTL 领先/滞后衰减（硬编码）：
  - **leading 信号衰减快（短 TTL，默认 30 天半衰）**；
  - **lagging 信号衰减慢（长 TTL，默认 90 天半衰）**。

确定性、不触网、无 LLM。中文 docstring。

CLI：
  python evidence_budget.py --axis hook_type --evidence-count 1 --budget-n 5 \
      --posterior-band insufficient [--json]
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

# 结构层域：只休眠不退役
CONTENT_DOMAIN = "content"
# 顾问域①②④：可退役
ADVISORY_DOMAINS = {"audience", "scene", "behavior"}

# TTL 半衰天数：leading 短（衰减快）、lagging 长（衰减慢）
TTL_HALFLIFE_DAYS = {"leading": 30, "lagging": 90}
# 证据不足的后验档（弱负面信号）
_INSUFFICIENT_BANDS = {"insufficient", "lean_retire", "strong_retire"}

# 进程内累计证据计数（轻量跟踪；持久化属运行时职责）
_ACCRUED: dict[str, int] = {}


def accrue(axis: str, evidence_count: int) -> int:
    """跟踪某轴累计证据项目数（从回测/C15 计）。返回累计后的总数。"""
    _ACCRUED[axis] = _ACCRUED.get(axis, 0) + int(evidence_count)
    return _ACCRUED[axis]


def _axis_domain(axis: str, dictionary: dict[str, Any]) -> str | None:
    entry = (dictionary.get("axes") or {}).get(axis)
    return entry.get("domain") if isinstance(entry, dict) else None


def _axis_signal_kind(axis: str, dictionary: dict[str, Any]) -> str | None:
    entry = (dictionary.get("axes") or {}).get(axis)
    return entry.get("signal_kind") if isinstance(entry, dict) else None


def sunset_check(axis: str, dictionary: dict[str, Any] | None = None, *,
                 evidence_count: int, budget_N: int,
                 posterior_band: str) -> dict[str, Any]:
    """日落判定：结构层只 hibernate，①②④可 retire。

    返回 {axis, domain, action: keep|deprioritize|hibernate|retire, reason}。
    """
    dictionary = dictionary if dictionary is not None else load_lib(DICTIONARY_LIB)
    domain = _axis_domain(axis, dictionary)

    insufficient = posterior_band in _INSUFFICIENT_BANDS
    budget_exhausted = evidence_count >= budget_N and insufficient

    # 证据充足或方向性正面 → 保留
    if not insufficient:
        return {"axis": axis, "domain": domain, "action": "keep",
                "reason": f"后验档 {posterior_band} 非证据不足，保留"}

    if not budget_exhausted:
        # 仍在证据预算内、证据不足 → 弱负面信号、降优先级
        return {"axis": axis, "domain": domain, "action": "deprioritize",
                "reason": f"证据不足（{evidence_count}/{budget_N}），弱负面信号、降优先级"}

    # 预算耗尽且仍证据不足 → 日落
    if domain == CONTENT_DOMAIN:
        # 结构层承重墙：只休眠不退役
        return {"axis": axis, "domain": domain, "action": "hibernate",
                "reason": f"结构层轴累计 {evidence_count}≥{budget_N} 仍证据不足，"
                          f"只 hibernate 不 retire"}
    if domain in ADVISORY_DOMAINS:
        return {"axis": axis, "domain": domain, "action": "retire",
                "reason": f"①②④顾问轴累计 {evidence_count}≥{budget_N} 仍证据不足，可 retire"}
    # 域未知（未登记）→ 保守只 hibernate
    return {"axis": axis, "domain": domain, "action": "hibernate",
            "reason": "域未登记，保守 hibernate"}


def ttl_decay(signal_kind: str, age_days: float) -> dict[str, Any]:
    """leading 短 TTL（衰减快）、lagging 长 TTL（衰减慢）的半衰减权重。

    decay_weight = 0.5 ** (age_days / halflife)，age ≥ 2×半衰记 stale。
    """
    halflife = TTL_HALFLIFE_DAYS.get(signal_kind, 60)
    weight = 0.5 ** (float(age_days) / halflife) if halflife > 0 else 0.0
    stale = float(age_days) >= 2 * halflife
    return {"signal_kind": signal_kind, "age_days": age_days,
            "halflife_days": halflife, "decay_weight": weight, "stale": stale}


def _load_dict(path: str | None) -> dict[str, Any]:
    if not path:
        return load_lib(DICTIONARY_LIB)
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    if p.suffix in (".yaml", ".yml"):
        import yaml
        return yaml.safe_load(text)
    return json.loads(text)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="日落 + TTL 衰减（M4，结构轴只休眠·leading TTL 短·确定性）")
    parser.add_argument("--axis", required=True)
    parser.add_argument("--dictionary", help="字典路径（缺省读 lib）")
    parser.add_argument("--evidence-count", type=int, default=0)
    parser.add_argument("--budget-n", type=int, default=5)
    parser.add_argument("--posterior-band", default="insufficient")
    parser.add_argument("--ttl-signal-kind", help="若给则附带 ttl_decay 结果")
    parser.add_argument("--age-days", type=float, default=0.0)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    dictionary = _load_dict(args.dictionary)
    res: dict[str, Any] = {"sunset": sunset_check(
        args.axis, dictionary, evidence_count=args.evidence_count,
        budget_N=args.budget_n, posterior_band=args.posterior_band)}
    if args.ttl_signal_kind:
        res["ttl"] = ttl_decay(args.ttl_signal_kind, args.age_days)

    if args.json:
        print(json.dumps(res, ensure_ascii=False))
    else:
        s = res["sunset"]
        print(f"日落判定 {s['axis']}（{s['domain']}）→ {s['action']}：{s['reason']}")
        if "ttl" in res:
            t = res["ttl"]
            print(f"TTL {t['signal_kind']} age={t['age_days']}d "
                  f"weight={t['decay_weight']:.3f} stale={t['stale']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
