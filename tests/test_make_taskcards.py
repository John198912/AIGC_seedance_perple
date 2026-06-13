"""任务卡单测：按 (shot×pass) 双 pass 实例化、API/UI 卡、批次清单。"""
from __future__ import annotations

import json

import compile_genspec
import make_taskcards


def test_dual_pass_instantiation(tmp_path, shotlist_shot):
    g = compile_genspec.compile_genspec(shotlist_shot, style_core="末日西部基调")
    res = make_taskcards.make_taskcards([g], tmp_path)
    # guided → draft(api) + final(ui) 两张卡
    assert res["count"] == 2
    passes = sorted(c["pass"] for c in res["cards"])
    assert passes == ["draft", "final"]


def test_api_card_is_valid_json(tmp_path, shotlist_shot):
    g = compile_genspec.compile_genspec(shotlist_shot, style_core="末日西部基调")
    make_taskcards.make_taskcards([g], tmp_path)
    api_cards = list(tmp_path.glob("*.api.json"))
    assert api_cards
    card = json.loads(api_cards[0].read_text(encoding="utf-8"))
    assert card["channel"] == "api"
    assert card["endpoint"]
    assert card["seed_list"]


def test_ui_card_and_batch_manifest(tmp_path, shotlist_shot):
    g = compile_genspec.compile_genspec(shotlist_shot, style_core="末日西部基调")
    make_taskcards.make_taskcards([g], tmp_path)
    assert list(tmp_path.glob("*.md"))  # UI 卡
    assert (tmp_path / "_batch.md").exists()
    manifest = (tmp_path / "_batch.md").read_text(encoding="utf-8")
    assert "批次清单" in manifest


def test_tc_numbering_sequential(tmp_path, shotlist_shot):
    g = compile_genspec.compile_genspec(shotlist_shot, style_core="末日西部基调")
    res = make_taskcards.make_taskcards([g], tmp_path, start_tc=5)
    tcs = sorted(c["tc"] for c in res["cards"])
    assert tcs == ["TC-005", "TC-006"]
