#!/usr/bin/env python3
"""合规过滤（设计稿 §5 SK5 编译管线④ / §6.3，P1）。

跑 libs/compliance-map.yaml：
1. 语义替换：把敏感词替换为合规的语义化描述，记 compliance_applied[]。
2. 残留扫描：替换后再扫一遍敏感词 + forbidden 硬禁止词；命中即返回 residual[]
   （供 SK5 阻断出卡 / 人工复核）。

确定性逻辑、无副作用（替换在内存的 GenSpec 上进行，写回由 SK5 编译器负责）。

CLI：
  python compliance_check.py --genspec 05_prompts/genspecs/SHOT-07.yaml [--write] [--json]
退出码：0 = 无残留；1 = 存在残留敏感词 / 硬禁止词。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str((Path(__file__).resolve().parent.parent.parent
                        / "_shared" / "scripts")))
from _common import read_yaml, write_yaml, load_lib  # noqa: E402

# GenSpec.prompt 中参与合规扫描/替换的文本层
PROMPT_TEXT_FIELDS = ["layer0_deai", "layer1_setting", "layer2_style", "layer3_shot",
                      "compiled_zh", "compiled_en"]


def _compliance_map() -> dict[str, Any]:
    return load_lib("compliance-map.yaml")


def apply_replacements(text: str, replacements: list[dict[str, str]]) -> tuple[str, list[str]]:
    """对单段文本做语义替换。返回 (新文本, 命中敏感词列表)。"""
    applied = []
    for rule in replacements:
        sensitive = rule.get("sensitive", "")
        repl = rule.get("replace_with", "")
        if sensitive and sensitive in text:
            text = text.replace(sensitive, repl)
            applied.append(sensitive)
    return text, applied


def scan_residual(text: str, replacements: list[dict[str, str]],
                  forbidden: list[str]) -> list[str]:
    """替换后残留扫描：仍含敏感词或硬禁止关键词即记入残留。"""
    hits = []
    for rule in replacements:
        s = rule.get("sensitive", "")
        if s and s in text:
            hits.append(s)
    for fb in forbidden:
        # forbidden 项形如 "真人明星 / 公众人物（...）"，取分隔前的核心词做包含匹配
        for token in _forbidden_tokens(fb):
            if token and token in text:
                hits.append(token)
    return hits


def _forbidden_tokens(entry: str) -> list[str]:
    """从 forbidden 描述里抽取可匹配的核心关键词（去括号说明 + 斜杠拆分）。"""
    head = entry.split("（")[0].split("(")[0]
    return [t.strip() for t in head.replace("/", " ").split() if t.strip()]


def check_genspec(genspec: dict[str, Any]) -> dict[str, Any]:
    """对 GenSpec 跑合规替换 + 残留扫描。返回 {genspec(已替换), compliance_applied, residual}。"""
    cmap = _compliance_map()
    replacements = cmap.get("replacements", []) or []
    forbidden = cmap.get("forbidden", []) or []

    prompt = genspec.get("prompt", {})
    all_applied: list[str] = []
    all_residual: list[str] = []

    for field in PROMPT_TEXT_FIELDS:
        val = prompt.get(field)
        if not isinstance(val, str) or not val:
            continue
        new_val, applied = apply_replacements(val, replacements)
        prompt[field] = new_val
        all_applied.extend(applied)
        all_residual.extend(scan_residual(new_val, replacements, forbidden))

    # 去重并写回 compliance_applied（设计稿要求记录）
    uniq_applied = sorted(set(all_applied))
    uniq_residual = sorted(set(all_residual))
    genspec["compliance_applied"] = uniq_applied

    return {
        "genspec": genspec,
        "compliance_applied": uniq_applied,
        "residual": uniq_residual,
        "ok": not uniq_residual,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="合规替换 + 残留扫描（SK5）")
    parser.add_argument("--genspec", required=True)
    parser.add_argument("--write", action="store_true", help="把替换结果写回 GenSpec 文件")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    genspec = read_yaml(args.genspec)
    result = check_genspec(genspec)

    if args.write:
        write_yaml(args.genspec, result["genspec"])

    out = {k: result[k] for k in ("compliance_applied", "residual", "ok")}
    if args.json:
        print(json.dumps(out, ensure_ascii=False))
    else:
        print(f"合规替换：{out['compliance_applied'] or '无'}")
        if out["residual"]:
            print(f"残留敏感/禁止词（需处理）：{out['residual']}")
        else:
            print("残留扫描通过")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
