"""budget_guard 单测：min(cap) 拦截、告警阈值、ai_qc_cap 拦截。"""
from __future__ import annotations

import budget_guard
import ledger


def test_effective_cap_is_min():
    budget = {"per_shot_cost_cap_cny": 80}
    assert budget_guard.effective_per_shot_cap(budget, {"per_shot_cost_cap_cny": 50}) == 50
    # genspec 不可上调，但 min 总取更严者
    assert budget_guard.effective_per_shot_cap(budget, {"per_shot_cost_cap_cny": 120}) == 80
    assert budget_guard.effective_per_shot_cap(budget, None) == 80


def test_per_shot_cap_blocks(project_dir):
    # 本镜已花 0，本批预计 100 > min(project 80, genspec 50)=50 → 拦截
    res = budget_guard.check_batch(project_dir, shot_id="SHOT-07",
                                   batch_cost_cny=100,
                                   genspec={"per_shot_cost_cap_cny": 50})
    assert res["allowed"] is False
    assert res["effective_per_shot_cap"] == 50
    assert any("超上限" in b for b in res["blocks"])


def test_per_shot_cap_accumulates_prior_spend(project_dir):
    # 先记 60 元在 SHOT-07，再来一批 30 → 共 90 > 80 上限
    ledger.append_event(project_dir, {"type": "take_cost", "shot_id": "SHOT-07",
                                      "cny": 60.0, "event_id": "pre"})
    res = budget_guard.check_batch(project_dir, shot_id="SHOT-07", batch_cost_cny=30)
    assert res["allowed"] is False


def test_alert_threshold(project_dir):
    # 默认 token_budget 3000, threshold 0.8, per_shot_cap 80。
    # 先把历史总花累计到 2450，再来一小批 50（< 单镜 80 不触发单镜阻断），
    # 总预计 2500/3000=83% ≥ 80% → 触发告警；告警不阻断。
    ledger.append_event(project_dir, {"type": "take_cost", "shot_id": "SHOT-99",
                                      "cny": 2450.0, "event_id": "warmup"})
    res = budget_guard.check_batch(project_dir, batch_cost_cny=50)
    assert any("告警阈值" in a for a in res["alerts"])
    assert res["allowed"] is True  # 告警不阻断


def test_ai_qc_cap_blocks(project_dir):
    # ai_qc_cost_cap 默认 200；预计 qc 250 → 拦截
    res = budget_guard.check_batch(project_dir, qc_cost_cny=250)
    assert res["allowed"] is False
    assert any("ai_qc_cost_cap" in b for b in res["blocks"])


def test_guard_records_event(project_dir):
    budget_guard.guard_batch(project_dir, shot_id="SHOT-07", batch_cost_cny=100,
                             genspec={"per_shot_cost_cap_cny": 50})
    events = ledger.read_events(project_dir)
    assert any(e["type"] == "adjust" and "budget_guard" in e.get("note", "")
               for e in events)
