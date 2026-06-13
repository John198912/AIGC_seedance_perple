"""契约校验单测：schema 校验通过/失败（C1/C6/C7/C9）。"""
from __future__ import annotations

import pytest

import validate
from validate import ValidationError, validate_obj, resolve_contract


def test_resolve_contract_by_alias_and_code():
    assert resolve_contract("C1") == "C1"
    assert resolve_contract("c6") == "C6"
    # 别名可解析回契约码
    assert resolve_contract(validate.CONTRACT_ALIASES["C1"]) == "C1"


def test_resolve_contract_unknown_raises():
    with pytest.raises(ValueError):
        resolve_contract("C999")


def test_valid_project_passes(project_dir):
    from _common import read_yaml
    proj = read_yaml(project_dir / "project.yaml")
    # 不抛即通过
    validate_obj(proj, "C1")


def test_invalid_project_fails():
    with pytest.raises(ValidationError):
        validate_obj({"not": "a project"}, "C1")


def test_genspec_roundtrip_valid(shotlist_shot):
    import compile_genspec
    genspec = compile_genspec.compile_genspec(shotlist_shot)
    validate_obj(genspec, "C6")  # compile 内部已校验，这里再确认一次


def test_api_card_requires_endpoint_when_channel_api():
    # channel=api 但缺 endpoint/seed_list/recycle_naming → 失败
    bad = {
        "task_id": "TC-001",
        "shot_id": "SHOT-07",
        "pass": "draft",
        "channel": "api",
        "platform": "falai",
    }
    with pytest.raises(ValidationError):
        validate_obj(bad, "C7")
