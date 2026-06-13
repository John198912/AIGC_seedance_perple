#!/usr/bin/env python3
"""预算护栏（设计稿 §5 SK0 / §8 / §4 单写者矩阵，P1）。

每批次发出前核算成本，三道闸：
1. 单镜上限：按 min(project.per_shot_cost_cap, genspec.per_shot_cost_cap) 拦截
   —— GenSpec 只能下调（更严），上调需 Gate；故取 min。
2. 总预算告警：累计成本 / token_budget 超 alert_threshold 即告警（不阻断）。
3. ai_qc_cost_cap：VLM/Judge 推理累计费超 ai_qc_cost_cap 即拦截。

判定结果（含拦截/告警）追写 events.jsonl（事件源，type=adjust 记录护栏动作；
真实计费由 ingest/本脚本以 take_cost/ai_qc_cost 追写）。本脚本是 events.jsonl
的合法写者之一（与 ingest.py 并列，见 §4）。

CLI：
  python budget_guard.py --project <dir> --shot SHOT-07 --batch-cost 50 \
      [--genspec 05_prompts/genspecs/SHOT-07.yaml] [--qc-cost 3] [--json]
退出码：0 = 放行；1 = 被单镜上限或 ai_qc_cap 拦截。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

SHARED_SCRIPTS = (Path(__file__).resolve().parent.parent
                  / "sub-skills" / "_shared" / "scripts")
sys.path.insert(0, str(SHARED_SCRIPTS))
from _common import read_yaml, project_path, load_lib  # noqa: E402
import ledger as _ledger  # noqa: E402


def estimate_channel_cost(channel: str, *, seconds: float = 0.0,
                          shots: int = 1) -> dict[str, Any]:
    """按 channel-cost-map.yaml 估算渠道成本（A.5 渠道成本路由）。

    api 类渠道按 cost_per_second_cny * 秒数计；ui 类按 credits_per_shot * 镜数（积分）。
    数字仅来自挂 verified_at 的 channel-cost-map，确定性、不触网。
    返回 {channel, unit, cost, verified_at, max_resolution}；未知渠道返回 supported=False。
    """
    cmap = load_lib("channel-cost-map.yaml").get("channels", {})
    ch = cmap.get(channel)
    if ch is None:
        return {"channel": channel, "supported": False,
                "reason": f"channel-cost-map 无 {channel} 条目（需补并挂 verified_at）"}
    out: dict[str, Any] = {
        "channel": channel,
        "supported": True,
        "type": ch.get("type"),
        "max_resolution": ch.get("max_resolution"),
        "verified_at": str(ch.get("verified_at")),
    }
    if ch.get("cost_per_second_cny") is not None:
        out["unit"] = "cny"
        out["cost"] = round(float(ch["cost_per_second_cny"]) * float(seconds), 2)
    elif ch.get("credits_per_shot") is not None:
        out["unit"] = "credits"
        out["cost"] = float(ch["credits_per_shot"]) * int(shots)
    else:
        out["unit"] = "unknown"
        out["cost"] = 0.0
    return out


def cheapest_channel(*, seconds: float = 0.0,
                     min_resolution: str | None = None) -> dict[str, Any] | None:
    """在 cny 计价的 api 渠道中选最便宜者（满足分辨率约束），供路由决策参考。"""
    cmap = load_lib("channel-cost-map.yaml").get("channels", {})
    best: dict[str, Any] | None = None
    for name, ch in cmap.items():
        if ch.get("cost_per_second_cny") is None:
            continue
        if min_resolution and ch.get("max_resolution") != min_resolution \
                and min_resolution == "1080p" and ch.get("max_resolution") not in ("1080p",):
            continue
        est = estimate_channel_cost(name, seconds=seconds)
        if best is None or est["cost"] < best["cost"]:
            best = est
    return best


def effective_per_shot_cap(project_budget: dict[str, Any],
                           genspec: dict[str, Any] | None) -> float | None:
    """单镜有效上限 = min(project, genspec)。任一缺省取另一个；都缺为 None（不拦）。"""
    caps = []
    p = project_budget.get("per_shot_cost_cap_cny")
    if p is not None:
        caps.append(float(p))
    if genspec is not None:
        g = genspec.get("per_shot_cost_cap_cny")
        if g is not None:
            caps.append(float(g))
    return min(caps) if caps else None


def check_batch(project: str | Path, *, shot_id: str | None = None,
                batch_cost_cny: float = 0.0, genspec: dict[str, Any] | None = None,
                qc_cost_cny: float = 0.0) -> dict[str, Any]:
    """发批前核算。返回 {allowed, blocks[], alerts[], ...}。不写账，仅判定。"""
    proj = read_yaml(project_path(project, "project.yaml"))
    budget = proj.get("budget", {})
    summary = _ledger.get_summary(project)

    blocks: list[str] = []
    alerts: list[str] = []

    # 1) 单镜上限：本镜已花 + 本批新增，对比 min(project, genspec)
    cap = effective_per_shot_cap(budget, genspec)
    shot_spent = 0.0
    if shot_id:
        shot_spent = float((summary.get("by_shot", {}).get(shot_id, {}) or {}).get("cny", 0.0))
    shot_projected = shot_spent + float(batch_cost_cny)
    if cap is not None and shot_projected > cap:
        blocks.append(
            f"单镜 {shot_id} 预计 {shot_projected:.2f} 超上限 {cap:.2f}"
            f"（min(project, genspec)）")

    # 2) 总预算告警阈值
    token_budget = float(budget.get("token_budget_cny") or 0)
    threshold = float(budget.get("alert_threshold") or 0)
    total_projected = float(summary.get("total_cny", 0.0)) + float(batch_cost_cny) + float(qc_cost_cny)
    if token_budget > 0 and threshold > 0:
        ratio = total_projected / token_budget
        if ratio >= threshold:
            alerts.append(
                f"累计预计 {total_projected:.2f}/{token_budget:.2f} "
                f"= {ratio:.0%} ≥ 告警阈值 {threshold:.0%}")

    # 3) ai_qc_cost_cap
    qc_cap = budget.get("ai_qc_cost_cap_cny")
    qc_projected = float(summary.get("ai_qc_costs", 0.0)) + float(qc_cost_cny)
    if qc_cap is not None and qc_projected > float(qc_cap):
        blocks.append(
            f"AI QC 预计 {qc_projected:.2f} 超 ai_qc_cost_cap {float(qc_cap):.2f}")

    return {
        "allowed": not blocks,
        "shot_id": shot_id,
        "effective_per_shot_cap": cap,
        "shot_spent": shot_spent,
        "shot_projected": shot_projected,
        "total_projected": total_projected,
        "qc_projected": qc_projected,
        "blocks": blocks,
        "alerts": alerts,
    }


def guard_batch(project: str | Path, *, shot_id: str | None = None,
                batch_cost_cny: float = 0.0, genspec: dict[str, Any] | None = None,
                qc_cost_cny: float = 0.0, record: bool = True) -> dict[str, Any]:
    """核算并（record=True 时）把护栏判定追写 events.jsonl。"""
    result = check_batch(project, shot_id=shot_id, batch_cost_cny=batch_cost_cny,
                         genspec=genspec, qc_cost_cny=qc_cost_cny)
    if record and (result["blocks"] or result["alerts"]):
        note = "; ".join(result["blocks"] + result["alerts"])
        _ledger.append_event(project, {
            "type": "adjust",
            "shot_id": shot_id,
            "cny": 0.0,  # 护栏判定不改账面，仅留痕
            "note": f"budget_guard: {'BLOCK' if result['blocks'] else 'ALERT'} {note}",
        })
    return result


def _load_genspec(path: str | None) -> dict[str, Any] | None:
    if not path:
        return None
    return read_yaml(path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="预算护栏：单镜上限 + 告警 + ai_qc_cap（SK0）")
    parser.add_argument("--project", required=True)
    parser.add_argument("--shot")
    parser.add_argument("--batch-cost", type=float, default=0.0, help="本批新增预计成本 CNY")
    parser.add_argument("--genspec", help="GenSpec 路径（取其 per_shot_cost_cap 参与 min）")
    parser.add_argument("--qc-cost", type=float, default=0.0, help="本批新增 AI QC 预计成本 CNY")
    parser.add_argument("--no-record", action="store_true", help="只判定不写事件")
    parser.add_argument("--channel", help="按 channel-cost-map 估算该渠道成本（路由参考）")
    parser.add_argument("--seconds", type=float, default=0.0, help="估算用时长（秒）")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    if args.channel:
        est = estimate_channel_cost(args.channel, seconds=args.seconds)
        if args.json:
            print(json.dumps(est, ensure_ascii=False))
        else:
            print(f"渠道 {args.channel} 估算：{est}")
        return 0

    genspec = _load_genspec(args.genspec)
    result = guard_batch(args.project, shot_id=args.shot, batch_cost_cny=args.batch_cost,
                        genspec=genspec, qc_cost_cny=args.qc_cost,
                        record=not args.no_record)

    if args.json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        print(f"放行：{result['allowed']}（单镜上限={result['effective_per_shot_cap']}）")
        for b in result["blocks"]:
            print(f"  阻断：{b}")
        for a in result["alerts"]:
            print(f"  告警：{a}")
    return 0 if result["allowed"] else 1


if __name__ == "__main__":
    sys.exit(main())
