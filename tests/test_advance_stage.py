"""advance_stage 单测：Gate 拦截、产物缺失拦截、推进 + 版本快照 + 事件追写。"""
from __future__ import annotations

import advance_stage
import ledger
from _common import read_yaml, project_path


def _set_stage(project_dir, stage, gates=None):
    p = project_dir / "project.yaml"
    proj = read_yaml(p)
    proj["stage"] = stage
    if gates:
        proj.setdefault("gates", {}).update(gates)
    import yaml
    p.write_text(yaml.safe_dump(proj, allow_unicode=True, sort_keys=False), encoding="utf-8")


def test_blocked_when_artifacts_missing(project_dir):
    # 处于 S1_BRIEF 但没有 brief.md → 推进到 S2 被产物校验拦截
    _set_stage(project_dir, "S1_BRIEF")
    res = advance_stage.advance(project_dir, do_git=False)
    assert res["advanced"] is False
    assert "01_brief/brief.md" in res["check"]["missing_artifacts"]


def test_blocked_when_gate_not_passed(project_dir, write_yaml):
    # S3_CHARACTER → S4 需要 G3_character passed
    (project_dir / "03_characters" / "robo").mkdir(parents=True, exist_ok=True)
    write_yaml(project_dir / "03_characters" / "robo" / "card.yaml", {"id": "robo"})
    _set_stage(project_dir, "S3_CHARACTER", gates={"G3_character": {"status": "pending"}})
    res = advance_stage.advance(project_dir, do_git=False)
    assert res["advanced"] is False
    assert res["check"]["required_gate"] == "G3_character"


def test_advance_passes_with_gate_and_artifact(project_dir, write_yaml):
    (project_dir / "03_characters" / "robo").mkdir(parents=True, exist_ok=True)
    write_yaml(project_dir / "03_characters" / "robo" / "card.yaml", {"id": "robo"})
    _set_stage(project_dir, "S3_CHARACTER", gates={"G3_character": {"status": "passed"}})
    res = advance_stage.advance(project_dir, do_git=False)
    assert res["advanced"] is True
    assert res["target"] == "S4_STORYBOARD"
    # 版本快照已落
    proj = read_yaml(project_dir / "project.yaml")
    assert proj["stage"] == "S4_STORYBOARD"
    assert proj["versions"][-1]["stage_to"] == "S4_STORYBOARD"
    # 事件源追写 stage_advance
    events = ledger.read_events(project_dir)
    assert any(e["type"] == "stage_advance" for e in events)


def test_force_skips_checks(project_dir):
    _set_stage(project_dir, "S1_BRIEF")  # 无 brief.md
    res = advance_stage.advance(project_dir, force=True, do_git=False)
    assert res["advanced"] is True
    assert res["check"]["ok"] is False  # 校验本来不通过，但 force 放行


def test_check_only_does_not_mutate(project_dir):
    _set_stage(project_dir, "S0_IDEA")
    chk = advance_stage.check_can_advance(project_dir, "S0_IDEA", "S1_BRIEF")
    assert chk["ok"] is True  # S0_IDEA 无产物要求
    assert read_yaml(project_dir / "project.yaml")["stage"] == "S0_IDEA"
