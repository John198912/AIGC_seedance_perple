"""账本单测：事件源追加、幂等、summary 重放重建。"""
from __future__ import annotations

import ledger


def test_append_and_replay(project_dir):
    ledger.append_event(project_dir, {
        "type": "take_cost", "shot_id": "SHOT-07", "pass": "draft",
        "channel": "api", "cny": 12.0, "event_id": "ev-1",
    })
    ledger.append_event(project_dir, {
        "type": "take_cost", "shot_id": "SHOT-07", "pass": "draft",
        "channel": "api", "cny": 12.0, "event_id": "ev-2",
    })
    s = ledger.get_summary(project_dir)
    assert s["total_cny"] == 24.0
    assert s["event_count"] == 2
    assert s["by_shot"]["SHOT-07"]["take_count"] == 2


def test_idempotent_event_id(project_dir):
    ev = {"type": "take_cost", "shot_id": "SHOT-09", "cny": 5.0, "event_id": "dup"}
    ledger.append_event(project_dir, dict(ev))
    ledger.append_event(project_dir, dict(ev))  # 同 event_id 不重复计
    s = ledger.get_summary(project_dir)
    assert s["event_count"] == 1
    assert s["total_cny"] == 5.0


def test_mixed_event_types(project_dir):
    ledger.append_event(project_dir, {"type": "take_cost", "shot_id": "SHOT-01",
                                      "cny": 10.0, "event_id": "a"})
    ledger.append_event(project_dir, {"type": "ai_qc_cost", "cny": 2.0, "event_id": "b"})
    ledger.append_event(project_dir, {"type": "human_minutes", "minutes": 30,
                                      "event_id": "c"})
    s = ledger.get_summary(project_dir)
    assert s["ai_qc_costs"] == 2.0
    assert s["human_minutes"] == 30
    assert s["total_cny"] == 12.0  # take 10 + qc 2


def test_summary_rebuilt_from_events_only(project_dir):
    ledger.append_event(project_dir, {"type": "take_cost", "shot_id": "SHOT-02",
                                      "cny": 7.0, "event_id": "x"})
    # 直接调 rebuild 不依赖既有 summary 文件
    s = ledger.rebuild_summary(project_dir)
    assert s["total_cny"] == 7.0
