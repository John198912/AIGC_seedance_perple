"""Prompt QC 单测：八要素硬阻断 + 占位语义评分。"""
from __future__ import annotations

import compile_genspec
import prompt_qc


def test_complete_genspec_no_blockers(shotlist_shot):
    g = compile_genspec.compile_genspec(shotlist_shot, style_core="末日西部基调")
    qc = prompt_qc.run_qc(g)
    assert qc["structural_blockers"] == []
    assert qc["craft_score"] is not None


def test_missing_element_blocks():
    # 缺失全部要素的空 prompt → 八要素全报缺
    empty = {"prompt": {}}
    blockers = prompt_qc.find_structural_blockers(empty)
    assert set(blockers) == set(prompt_qc.CRAFT_ELEMENTS)


def test_scorer_callback_injectable(shotlist_shot):
    g = compile_genspec.compile_genspec(shotlist_shot, style_core="末日西部基调")

    def fake_scorer(genspec, blockers):
        return {"craft_score": 88, "deai_score": 77, "rubric_anchor_drift": 3}

    qc = prompt_qc.run_qc(g, scorer=fake_scorer)
    assert qc["craft_score"] == 88
    assert qc["deai_score"] == 77


def test_cli_exit_code_on_blockers(tmp_path):
    from _common import write_yaml
    bad = {"shot_id": "SHOT-00", "prompt": {}}
    p = tmp_path / "bad.yaml"
    write_yaml(p, bad)
    rc = prompt_qc.main(["--genspec", str(p), "--json"])
    assert rc == 1
