"""select_take 单测：落实人工选片、auto_reject 防误选、回写 shotlist。"""
from __future__ import annotations

import pytest

import select_take
from _common import read_yaml, project_path


def _seed_takes(project_dir, make_takelog, write_yaml, *, reject=None):
    tl = make_takelog(take_ids=["SHOT-07-t01", "SHOT-07-t02"])
    if reject:
        for t in tl["takes"]:
            if t["take_id"] == reject:
                t.setdefault("scores", {})["agent_vlm"] = {"verdict": "auto_reject"}
    shot_dir = project_path(project_dir, "06_generations", "SHOT-07")
    write_yaml(shot_dir / "takes.yaml", tl)
    return shot_dir


def test_select_writes_selected_take(project_dir, make_takelog, write_yaml):
    shot_dir = _seed_takes(project_dir, make_takelog, write_yaml)
    res = select_take.select_take(project_dir, "SHOT-07", "SHOT-07-t01", do_git=False)
    assert res["selected_take"] == "SHOT-07-t01"
    saved = read_yaml(shot_dir / "takes.yaml")
    assert saved["selected_take"] == "SHOT-07-t01"
    chosen = next(t for t in saved["takes"] if t["take_id"] == "SHOT-07-t01")
    assert chosen["status"] == "selected"


def test_select_blocks_auto_rejected(project_dir, make_takelog, write_yaml):
    _seed_takes(project_dir, make_takelog, write_yaml, reject="SHOT-07-t02")
    with pytest.raises(ValueError):
        select_take.select_take(project_dir, "SHOT-07", "SHOT-07-t02", do_git=False)


def test_select_unknown_take_raises(project_dir, make_takelog, write_yaml):
    _seed_takes(project_dir, make_takelog, write_yaml)
    with pytest.raises(ValueError):
        select_take.select_take(project_dir, "SHOT-07", "SHOT-07-tXX", do_git=False)


def test_select_updates_shotlist(project_dir, make_takelog, write_yaml, shotlist_doc):
    _seed_takes(project_dir, make_takelog, write_yaml)
    sl_path = project_path(project_dir, "04_storyboard", "shotlist.yaml")
    write_yaml(sl_path, shotlist_doc)
    res = select_take.select_take(project_dir, "SHOT-07", "SHOT-07-t01",
                                  shot_status="locked", do_git=False)
    assert res["shotlist_updated"] is True
    sl = read_yaml(sl_path)
    shot = next(s for s in sl["shots"] if s["shot_id"] == "SHOT-07")
    assert shot["status"] == "locked"
