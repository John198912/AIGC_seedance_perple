#!/usr/bin/env python3
"""C1–C10 schema 校验（设计稿 §8：所有契约文件写后必经校验）。

所有技能脚本复用本模块。提供：
- contract 名 -> schema 文件 的映射
- validate_obj(): 校验内存对象
- validate_file(): 校验磁盘上的 yaml/json 契约文件
- CLI 入口：python validate.py --project <dir> --contract C6 --file <path> [--json]

设计纪律：校验失败不得进入下游；缺文件/坏 schema 给修复指引。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator

# schemas/ 与本脚本同在 _shared/ 下
SCHEMA_DIR = Path(__file__).resolve().parent.parent / "schemas"

# 契约名 -> 业务别名（双向可查）
CONTRACT_ALIASES = {
    "C1": "project",
    "C2": "brief",
    "C3": "screenplay",
    "C4": "character",
    "C5": "shotlist",
    "C6": "genspec",
    "C7": "taskcard",
    "C8": "ledger",
    "C9": "takelog",
    "C10": "qcreport",
    "C11": "feedback",
    "C12": "reference_work",
    "C13": "featuretagset",
    "C14": "creativedna",
}
ALIAS_TO_CONTRACT = {v: k for k, v in CONTRACT_ALIASES.items()}


class ValidationError(Exception):
    """携带结构化错误信息的校验异常。"""

    def __init__(self, contract: str, errors: list[str]):
        self.contract = contract
        self.errors = errors
        super().__init__(f"{contract} 校验失败：\n" + "\n".join(errors))


def resolve_contract(name: str) -> str:
    """把 C6 / genspec 等任意写法归一为 Cx 契约号。"""
    key = name.strip()
    if key in CONTRACT_ALIASES:
        return key
    upper = key.upper()
    if upper in CONTRACT_ALIASES:
        return upper
    if key.lower() in ALIAS_TO_CONTRACT:
        return ALIAS_TO_CONTRACT[key.lower()]
    raise ValueError(f"未知契约名：{name}（可用：{', '.join(CONTRACT_ALIASES)} 或别名）")


def load_schema(contract: str) -> dict[str, Any]:
    contract = resolve_contract(contract)
    schema_path = SCHEMA_DIR / f"{contract}.schema.json"
    if not schema_path.exists():
        raise FileNotFoundError(
            f"找不到 schema：{schema_path}。请确认 _shared/schemas/ 下存在 {contract}.schema.json"
        )
    with schema_path.open(encoding="utf-8") as fh:
        return json.load(fh)


def _format_errors(validator: Draft202012Validator, obj: Any) -> list[str]:
    msgs = []
    for err in sorted(validator.iter_errors(obj), key=lambda e: list(e.path)):
        loc = "/".join(str(p) for p in err.path) or "<root>"
        msgs.append(f"  [{loc}] {err.message}")
    return msgs


def validate_obj(obj: Any, contract: str) -> None:
    """校验内存对象；失败抛 ValidationError。"""
    contract = resolve_contract(contract)
    schema = load_schema(contract)
    validator = Draft202012Validator(schema)
    errors = _format_errors(validator, obj)
    if errors:
        raise ValidationError(contract, errors)


def _load_data_file(path: Path) -> Any:
    if not path.exists():
        raise FileNotFoundError(f"找不到契约文件：{path}")
    text = path.read_text(encoding="utf-8")
    if path.suffix in (".json", ".json5"):
        return json.loads(text)
    # yaml.safe_load 同时能解析 json
    return yaml.safe_load(text)


def validate_file(path: str | Path, contract: str) -> None:
    """校验磁盘上的契约文件（yaml/json）；失败抛 ValidationError。"""
    data = _load_data_file(Path(path))
    validate_obj(data, contract)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="C1–C10 契约 schema 校验")
    parser.add_argument("--project", help="项目目录（可选，仅用于相对路径提示）")
    parser.add_argument("--contract", required=True, help="契约名：C1..C10 或别名（genspec 等）")
    parser.add_argument("--file", required=True, help="待校验的契约文件路径")
    parser.add_argument("--json", action="store_true", help="输出机读 JSON 结果")
    args = parser.parse_args(argv)

    try:
        validate_file(args.file, args.contract)
    except (ValidationError, FileNotFoundError, ValueError) as exc:
        if args.json:
            errors = exc.errors if isinstance(exc, ValidationError) else [str(exc)]
            print(json.dumps({"ok": False, "contract": args.contract, "errors": errors},
                             ensure_ascii=False))
        else:
            print(f"校验失败：{exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps({"ok": True, "contract": resolve_contract(args.contract),
                          "file": args.file}, ensure_ascii=False))
    else:
        print(f"校验通过：{args.file}（{resolve_contract(args.contract)}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
