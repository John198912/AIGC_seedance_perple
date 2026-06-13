#!/usr/bin/env python3
"""词汇级 IP 预筛（逆向特征工程模块 M2 · 设计稿第六部分）。

借 compliance_check 查表思路。诚实边界（硬规则）：
  - 只拦【词汇级】信号——照搬角色名 / 台词 / slogan / 专有名词；
  - 命中报 lexical_hit[]（含类别）；
  - **结构 / 视觉相似性（分镜构图、情节节拍、角色形象）查表做不到** →
    固定输出 structural_check: "defer_to_G0_human"，不宣称能自动覆盖。

读 lib `_shared/libs/ip-keywords.yaml`（或参数传入词条）。确定性、不触网、无 LLM。

CLI：
  python ip_prescreen.py --text "..." [--refs <C12/C14 yaml/json>] [--json]
退出码：0 = 无词汇级命中；1 = 有命中（供阻断/转 G0）。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str((Path(__file__).resolve().parent.parent.parent
                        / "_shared" / "scripts")))
from _common import read_yaml, load_lib  # noqa: E402

IP_KEYWORDS_LIB = "ip-keywords.yaml"
# 词条类别 → 中文标签
_CATEGORIES = {
    "character_names": "角色名",
    "catchphrases": "台词/slogan",
    "proper_nouns": "专有名词",
}
DEFER_MARKER = "defer_to_G0_human"


def _load_keywords(keywords: dict[str, list[str]] | None = None) -> dict[str, list[str]]:
    """加载禁用词条：参数传入优先，否则读 lib。"""
    if keywords is not None:
        return keywords
    data = load_lib(IP_KEYWORDS_LIB) or {}
    return {cat: list(data.get(cat, []) or []) for cat in _CATEGORIES}


def scan_text(text: str, keywords: dict[str, list[str]] | None = None) -> list[dict[str, str]]:
    """对单段文本做词汇级扫描，返回命中列表 [{term, category, category_zh}]。"""
    kw = _load_keywords(keywords)
    hits: list[dict[str, str]] = []
    text = text or ""
    for cat, terms in kw.items():
        for term in terms:
            if term and term in text:
                hits.append({"term": term, "category": cat,
                             "category_zh": _CATEGORIES.get(cat, cat)})
    return hits


def _collect_texts(payload: Any) -> list[str]:
    """从任意 C12/C13/C14 结构里收集可扫描文本字段（不深扫结构，只词汇级）。"""
    texts: list[str] = []

    def _walk(obj: Any) -> None:
        if isinstance(obj, str):
            texts.append(obj)
        elif isinstance(obj, dict):
            for v in obj.values():
                _walk(v)
        elif isinstance(obj, list):
            for v in obj:
                _walk(v)

    _walk(payload)
    return texts


def prescreen(payload: Any, keywords: dict[str, list[str]] | None = None) -> dict[str, Any]:
    """词汇级预筛 + 诚实边界声明。返回 {lexical_hit, structural_check, ok}。"""
    texts = _collect_texts(payload)
    seen: set[tuple[str, str]] = set()
    lexical_hit: list[dict[str, str]] = []
    for t in texts:
        for hit in scan_text(t, keywords):
            key = (hit["term"], hit["category"])
            if key not in seen:
                seen.add(key)
                lexical_hit.append(hit)
    return {
        "lexical_hit": lexical_hit,
        # 诚实边界：结构/视觉相似性查表做不到，固定 defer 到 G0 人工闸
        "structural_check": DEFER_MARKER,
        "ok": not lexical_hit,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="词汇级 IP 预筛（M2，确定性·不触网）")
    parser.add_argument("--text", help="直接扫描的文本")
    parser.add_argument("--refs", help="C12/C13/C14 文件（yaml/json）")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    if args.refs:
        payload = read_yaml(args.refs)
    else:
        payload = args.text or ""
    result = prescreen(payload)

    if args.json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        if result["lexical_hit"]:
            terms = "、".join(f"{h['term']}（{h['category_zh']}）" for h in result["lexical_hit"])
            print(f"词汇级命中（需阻断/转 G0）：{terms}")
        else:
            print("词汇级预筛通过")
        print(f"结构/视觉相似性：{result['structural_check']}（查表做不到，依赖 G0 人工闸）")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
