"""vlm_screen 单测：协议分层、auto_reject 规则、永不 auto_accept、unverifiable、记账。"""
from __future__ import annotations

import vlm_screen
import ledger
from _common import read_yaml, project_path


def _config():
    from _common import load_lib
    return load_lib("vlm-config.yaml")


def test_auto_reject_only_when_fail_and_high_confidence():
    cfg = _config()
    # identity=FAIL 且 conf>0.9 → auto_reject
    assert vlm_screen.decide_verdict("FAIL", 0.95, "static", cfg) == "auto_reject"
    # FAIL 但置信不足 → 不 auto_reject（应为 unverifiable，因 FAIL 不属可信 PASS）
    assert vlm_screen.decide_verdict("FAIL", 0.5, "static", cfg) == "unverifiable"


def test_never_auto_accept():
    cfg = _config()
    # 高置信 PASS 也只到 pass_to_human，绝不 auto_accept
    v = vlm_screen.decide_verdict("PASS", 0.99, "dynamic", cfg)
    assert v == "pass_to_human"
    assert v != "auto_accept"


def test_unverifiable_on_low_confidence():
    cfg = _config()
    assert vlm_screen.decide_verdict("PASS", 0.3, "static", cfg) == "unverifiable"


def test_protocol_selection_default_dynamic():
    cfg = _config()
    assert vlm_screen.choose_protocol({"take_id": "t1"}, cfg) == "dynamic"
    assert vlm_screen.choose_protocol({"take_id": "t1", "vlm_protocol_hint": "static"}, cfg) == "static"


def test_dynamic_samples_three_frames():
    cfg = _config()
    av = vlm_screen.screen_take({"take_id": "SHOT-07-t01", "vlm_protocol_hint": "dynamic"},
                                cfg, mock=True)
    assert av["protocol"] == "dynamic"
    assert av["frames_sampled"] == ["first", "mid", "last"]


def test_screen_shot_writes_and_records(project_dir, make_takelog, write_yaml):
    tl = make_takelog(take_ids=["SHOT-07-t01", "SHOT-07-fail02", "SHOT-07-weak03"])
    shot_dir = project_path(project_dir, "06_generations", "SHOT-07")
    write_yaml(shot_dir / "takes.yaml", tl)

    res = vlm_screen.screen_shot(project_dir, "SHOT-07", mock=True)
    assert res["screened"] == 3
    assert res["verdicts"]["auto_reject"] == 1     # fail02
    assert res["verdicts"]["unverifiable"] == 1    # weak03
    assert res["verdicts"]["pass_to_human"] == 1   # t01

    # 回写 takes.yaml：auto_reject 的被标 status
    saved = read_yaml(shot_dir / "takes.yaml")
    fail = next(t for t in saved["takes"] if t["take_id"] == "SHOT-07-fail02")
    assert fail["status"] == "auto_rejected"
    assert fail["scores"]["agent_vlm"]["verdict"] == "auto_reject"

    # ai_qc 成本计入 ledger
    s = ledger.get_summary(project_dir)
    assert s["ai_qc_costs"] > 0
