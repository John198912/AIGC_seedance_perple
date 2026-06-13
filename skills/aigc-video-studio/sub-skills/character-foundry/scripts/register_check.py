#!/usr/bin/env python3
"""角色注册一致性校验（设计稿 §5 SK3，P2 轻量实现）。

校验 CharacterCard（C4）：
- ref_set ≤9 张
- identity_strategy 四字段齐备（prompt_lock_zh/en + negative_zh/en）
- compliance.human_face 为 True 时告警（设计纪律：定角即规避真实人脸）

CLI：
  python register_check.py --card 03_characters/<id>/card.yaml [--json]
退出码：0 = 通过；1 = 存在错误。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str((Path(__file__).resolve().parent.parent.parent
                        / "_shared" / "scripts")))
from _common import read_yaml, ensure_validate_importable  # noqa: E402

ensure_validate_importable()
from validate import validate_obj  # noqa: E402

REQUIRED_IDENTITY = ["prompt_lock_zh", "prompt_lock_en", "negative_zh", "negative_en"]
MAX_REF = 9


def check_card(card: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []

    # schema 先行
    try:
        validate_obj(card, "C4")
    except Exception as exc:  # noqa: BLE001 —— 汇总为可读错误
        errors.append(f"C4 schema 不通过：{exc}")

    ref_set = card.get("ref_set") or []
    if len(ref_set) > MAX_REF:
        errors.append(f"ref_set {len(ref_set)} 张超上限 {MAX_REF}")

    ident = card.get("identity_strategy", {}) or {}
    missing = [k for k in REQUIRED_IDENTITY if not ident.get(k)]
    if missing:
        errors.append(f"identity_strategy 缺字段：{missing}")

    if (card.get("compliance", {}) or {}).get("human_face"):
        warnings.append("compliance.human_face=true：建议改用非人类/风格化造型规避合规风险")

    return {"id": card.get("id"), "errors": errors, "warnings": warnings,
            "ok": not errors}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="角色注册一致性校验（SK3，P2）")
    parser.add_argument("--card", required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    result = check_card(read_yaml(args.card))
    if args.json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        print(f"角色 {result['id']}：{'通过' if result['ok'] else '有错误'}")
        for e in result["errors"]:
            print(f"  错误：{e}")
        for w in result["warnings"]:
            print(f"  告警：{w}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
