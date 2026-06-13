"""verify_capabilities 单测：verified_at 过期校验、心跳凭证只读 env。"""
from __future__ import annotations

import datetime as _dt

import verify_capabilities
from _common import load_lib


def test_fresh_when_within_window():
    caps = load_lib("capabilities.yaml")
    # 能力表 verified_at 多为 2026-06-01，基准取 6-13（<30 天）→ 不过期
    res = verify_capabilities.check_expiry(caps, now=_dt.date(2026, 6, 13))
    assert res["ok"] is True
    assert res["expired"] == []


def test_expired_when_beyond_window():
    caps = load_lib("capabilities.yaml")
    # 基准 8-01 距 6-01 超 30 天 → 全部过期
    res = verify_capabilities.check_expiry(caps, now=_dt.date(2026, 8, 1))
    assert res["ok"] is False
    assert len(res["expired"]) >= 1
    assert any("seedance-2.0" in e for e in res["expired"])


def test_reverify_days_override():
    caps = load_lib("capabilities.yaml")
    # 阈值放宽到 365 天 → 8-01 也不过期
    res = verify_capabilities.check_expiry(caps, now=_dt.date(2026, 8, 1),
                                           reverify_days=365)
    assert res["ok"] is True


def test_missing_verified_at_flagged():
    caps = {"models": {"ghost": {"provider": "x"}}}  # 无 verified_at
    res = verify_capabilities.check_expiry(caps, now=_dt.date(2026, 6, 13))
    assert res["ok"] is False
    assert "models.ghost" in res["expired"]


def test_heartbeat_no_credentials_falls_back(project_dir, monkeypatch):
    # 清掉可能存在的凭证 env → 应告警降级为纯 UI
    monkeypatch.delenv("FAL_KEY", raising=False)
    monkeypatch.delenv("VOLCANO_AK", raising=False)
    hb = verify_capabilities.api_heartbeat(project_dir)
    assert hb["checked"] is True
    assert hb["ok"] is False
    assert any("无任何 API 凭证" in a for a in hb["alerts"])
    # 凭证只读存在性，绝不读取明文
    for ch in hb["channels"].values():
        assert ch["credential_present"] is False
        assert "credential_value" not in ch


def test_heartbeat_credential_present(project_dir, monkeypatch):
    monkeypatch.setenv("FAL_KEY", "dummy-not-read")
    hb = verify_capabilities.api_heartbeat(project_dir)
    assert hb["channels"]["falai"]["credential_present"] is True
    # 只暴露 env 名，不回显值
    assert hb["channels"]["falai"]["credential_env"] == "FAL_KEY"
    assert "dummy-not-read" not in str(hb)
