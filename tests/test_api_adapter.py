"""API 适配器单测：mock 模式确定性、凭证仅读环境变量、retry 封装。"""
from __future__ import annotations

import api_adapter


def _api_card():
    return {
        "task_id": "TC-021",
        "shot_id": "SHOT-07",
        "pass": "draft",
        "channel": "api",
        "platform": "falai",
        "model": "seedance-2.0",
        "endpoint": "fal-ai/bytedance/seedance-2.0/fast/reference-to-video",
        "reference_label_map": {},
        "references": [],
        "prompt_compiled_en": "x",
        "prompt_compiled_zh": "x",
        "seed_list": [100, 101, 102, 103],
        "rolling": {"takes_planned": 4, "max_takes": 8, "bayesian": True},
        "retry": {"max_retries": 3, "backoff": "exp", "on_429": "queue_repoll"},
        "fallback": ["volcano:seedance-2.0"],
        "recycle_naming": "SHOT-07-tNN_seed<seed>.mp4",
    }


def test_mock_mode_deterministic(tmp_path):
    card = _api_card()
    r1 = api_adapter.execute_card(card, tmp_path / "a", mock=True)
    r2 = api_adapter.execute_card(card, tmp_path / "b", mock=True)
    assert r1["mock"] is True
    assert r1["seeds"] == r2["seeds"] == [100, 101, 102, 103]
    assert r1["products"] == r2["products"]
    assert len(r1["products"]) == 4


def test_mock_products_are_written(tmp_path):
    card = _api_card()
    r = api_adapter.execute_card(card, tmp_path, mock=True)
    for name in r["products"]:
        assert (tmp_path / name).exists()


def test_credential_only_from_env(monkeypatch):
    monkeypatch.delenv("FAL_KEY", raising=False)
    assert api_adapter.has_credential("falai") is False
    monkeypatch.setenv("FAL_KEY", "secret")
    assert api_adapter.has_credential("falai") is True


def test_auto_mock_when_no_credential(tmp_path, monkeypatch):
    monkeypatch.delenv("FAL_KEY", raising=False)
    card = _api_card()
    r = api_adapter.execute_card(card, tmp_path, mock=None)  # 自动判定
    assert r["mock"] is True


def test_rejects_non_api_card(tmp_path):
    card = _api_card()
    card["channel"] = "ui"
    import pytest
    with pytest.raises(ValueError):
        api_adapter.execute_card(card, tmp_path, mock=True)
