#!/usr/bin/env python3
"""能力表过期校验 + API 健康心跳（设计稿 §5 SK0/SK11d / §8，S-P0-5/S-P2-2，P1）。

职责：
1. 遍历 capabilities.yaml 各条目的 verified_at，超 reverify_days（默认 30 天）即告警。
   —— 落实“能力数字只进 capabilities.yaml 挂 verified_at、月度重验”纪律。
2. API 健康心跳（mock）：依 project.api_config 检查凭证环境变量是否就绪、
   余额是否低于 balance_alert_cny；无凭证则记“需降级为 ui_only”。
   真实余额查询留待接 api_adapter；本阶段为确定性 mock，便于测试。

凭证安全：只读 env 是否存在（os.environ），绝不读取/打印密钥明文。

CLI：
  python verify_capabilities.py [--project <dir>] [--now 2026-07-15] [--json]
退出码：0 = 全部新鲜且健康；1 = 存在过期项或健康告警。
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import sys
from pathlib import Path
from typing import Any

SHARED_SCRIPTS = (Path(__file__).resolve().parent.parent
                  / "sub-skills" / "_shared" / "scripts")
sys.path.insert(0, str(SHARED_SCRIPTS))
from _common import read_yaml, load_lib, project_path  # noqa: E402

# 能力表中需逐条校验 verified_at 的顶层分组
CAP_GROUPS = ["models", "platforms", "channels"]

# M1 新增的治理 lib（逆向特征工程模块）；陈旧度校验对象
GOVERNANCE_LIBS = [
    "ranking-weights.yaml",
    "feature-dictionary.yaml",
    "source-credibility-rubric.yaml",
    "axis-constraints.yaml",
]


def _parse_date(val: Any) -> _dt.date | None:
    if val is None:
        return None
    if isinstance(val, _dt.date):
        return val
    if isinstance(val, _dt.datetime):
        return val.date()
    try:
        return _dt.date.fromisoformat(str(val)[:10])
    except ValueError:
        return None


def check_expiry(capabilities: dict[str, Any], *, now: _dt.date,
                 reverify_days: int | None = None) -> dict[str, Any]:
    """逐条校验 verified_at 是否过期。返回 {reverify_days, items[], expired[]}。"""
    days = reverify_days if reverify_days is not None else int(
        capabilities.get("reverify_days", 30))
    items: list[dict[str, Any]] = []
    expired: list[str] = []

    for group in CAP_GROUPS:
        for name, entry in (capabilities.get(group, {}) or {}).items():
            if not isinstance(entry, dict):
                continue
            va = _parse_date(entry.get("verified_at"))
            age = (now - va).days if va else None
            is_expired = age is not None and age > days
            missing = va is None
            record = {
                "group": group, "name": name,
                "verified_at": str(entry.get("verified_at")),
                "age_days": age, "expired": is_expired, "missing_verified_at": missing,
            }
            items.append(record)
            if is_expired or missing:
                expired.append(f"{group}.{name}")

    return {"reverify_days": days, "items": items, "expired": expired,
            "ok": not expired}


def check_governance_freshness(*, now: _dt.date,
                               reverify_days: int | None = None) -> dict[str, Any]:
    """校验 M1 治理 lib 的 verified_at / version 陈旧度（M3，独立告警通道）。

    对每个治理 lib（GOVERNANCE_LIBS）：用 load_lib 读取，缺失文件温和跳过并记 missing、
    不抛异常；读顶层 verified_at，超 reverify_days（缺省复用 capabilities 的 30）记 stale；
    缺 verified_at 记 missing_verified_at。feature-dictionary 额外暴露其 version。
    返回 {reverify_days, items[], stale[], ok}。
    """
    days = reverify_days if reverify_days is not None else 30
    items: list[dict[str, Any]] = []
    stale: list[str] = []

    for name in GOVERNANCE_LIBS:
        try:
            lib = load_lib(name) or {}
        except FileNotFoundError:
            items.append({"name": name, "missing": True, "verified_at": None,
                          "age_days": None, "stale": False,
                          "missing_verified_at": False})
            continue
        va = _parse_date(lib.get("verified_at"))
        age = (now - va).days if va else None
        is_stale = age is not None and age > days
        missing_va = va is None
        record: dict[str, Any] = {
            "name": name,
            "verified_at": str(lib.get("verified_at")) if lib.get("verified_at") is not None else None,
            "age_days": age,
            "stale": is_stale,
            "missing_verified_at": missing_va,
        }
        if name == "feature-dictionary.yaml":
            record["version"] = lib.get("version")
        items.append(record)
        if is_stale or missing_va:
            stale.append(name)

    return {"reverify_days": days, "items": items, "stale": stale, "ok": not stale}


def api_heartbeat(project: str | Path | None) -> dict[str, Any]:
    """API 健康心跳（mock）：检查凭证 env 是否就绪 + 余额告警（确定性）。"""
    if project is None:
        return {"checked": False, "note": "未指定 --project，跳过心跳"}
    proj = read_yaml(project_path(project, "project.yaml"))
    api_cfg = proj.get("api_config", {}) or {}
    balance_alert = float(api_cfg.get("balance_alert_cny") or 0)
    fallback = api_cfg.get("fallback_on_quota_exhausted", "ui_only")

    channels = {
        "falai": api_cfg.get("fal_key_env", "FAL_KEY"),
        "volcano": api_cfg.get("volcano_ak_env", "VOLCANO_AK"),
    }
    status: dict[str, Any] = {}
    alerts: list[str] = []
    any_credential = False
    for ch, env_name in channels.items():
        present = bool(env_name and os.environ.get(env_name))
        any_credential = any_credential or present
        # mock 余额：无凭证 → 不可用；有凭证 → 给确定性正余额
        balance = 100.0 if present else None
        if present and balance is not None and balance < balance_alert:
            alerts.append(f"{ch} 余额 {balance} 低于告警线 {balance_alert}")
        status[ch] = {"credential_env": env_name, "credential_present": present,
                      "mock_balance_cny": balance}

    if not any_credential:
        alerts.append(f"无任何 API 凭证就绪，按 fallback_on_quota_exhausted={fallback} 降级为纯 UI 通道")

    return {"checked": True, "channels": status, "alerts": alerts,
            "fallback": fallback, "ok": not alerts}


def verify(project: str | Path | None = None, *, now: _dt.date | None = None,
           reverify_days: int | None = None,
           include_governance: bool = False) -> dict[str, Any]:
    """合并能力过期校验 + 健康心跳。

    M3：include_governance 默认 False —— 保持旧行为与旧 ok 语义完全不变；
    仅当显式传 include_governance=True（或 CLI --governance）时才并入治理陈旧度校验，
    并把 governance.ok 计入总 ok。
    """
    now = now or _dt.date.today()
    capabilities = load_lib("capabilities.yaml")
    expiry = check_expiry(capabilities, now=now, reverify_days=reverify_days)
    heartbeat = api_heartbeat(project)
    result = {
        "now": now.isoformat(),
        "expiry": expiry,
        "heartbeat": heartbeat,
        "ok": expiry["ok"] and heartbeat.get("ok", True),
    }
    if include_governance:
        governance = check_governance_freshness(now=now, reverify_days=reverify_days)
        result["governance"] = governance
        result["ok"] = result["ok"] and governance["ok"]
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="能力表过期校验 + API 健康心跳（SK0）")
    parser.add_argument("--project", help="项目目录（做 API 心跳；缺省只校验能力表）")
    parser.add_argument("--now", help="覆盖当前日期 YYYY-MM-DD（测试用）")
    parser.add_argument("--reverify-days", type=int, help="覆盖过期天数阈值")
    parser.add_argument("--governance", action="store_true",
                        help="并入 M1 治理 lib 陈旧度校验（M3，默认关闭以保旧行为）")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    now = _dt.date.fromisoformat(args.now) if args.now else None
    result = verify(args.project, now=now, reverify_days=args.reverify_days,
                    include_governance=args.governance)

    if args.json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        exp = result["expiry"]
        print(f"能力表（阈值 {exp['reverify_days']} 天，基准 {result['now']}）：")
        if exp["expired"]:
            print(f"  过期/缺 verified_at：{exp['expired']}")
        else:
            print("  全部新鲜")
        hb = result["heartbeat"]
        if hb.get("checked"):
            for a in hb.get("alerts", []):
                print(f"  心跳告警：{a}")
            if not hb.get("alerts"):
                print("  API 心跳正常")
        gov = result.get("governance")
        if gov is not None:
            if gov["stale"]:
                print(f"  治理 lib 陈旧/缺 verified_at：{gov['stale']}")
            else:
                print("  治理 lib 全部新鲜")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
