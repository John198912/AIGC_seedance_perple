#!/usr/bin/env python3
"""G0 版权审查闸（逆向特征工程模块 M2 · 设计稿第六部分 / 第九部分 M2 行）。

产出结构化审查记录（checklist）：迁移的结构 / 不碰的表达 / 法域（中国《著作权法》|日本法）/
单参考贡献模式数 ≤3 校验 / lexical_hit 汇总；并**追写一条事件到项目 events.jsonl**
（复用 _shared/scripts/ledger.py，与 G3/G6/G9 同构）。

决议：gate=G0，decision=pass|block，reviewer=human_required（G0 永不自动放行，
结构/视觉相似性查表做不到，需人工闸）。

state-machine 集成点（在 advance_stage 前插 G0）仅在 SKILL.md 文档化，**不改 advance_stage**。

确定性、不触网、无 LLM。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str((Path(__file__).resolve().parent.parent.parent
                        / "_shared" / "scripts")))
from _common import read_yaml, write_json, project_path  # noqa: E402
import ledger as _ledger  # noqa: E402
import ip_prescreen  # noqa: E402

PER_REF_PATTERN_CAP = 3   # 单参考贡献模式数硬上限（与 reverse_map 一致）
LEGAL_DOMAINS = {
    "douyin": "中国《著作权法》",
    "cn": "中国《著作权法》",
    "tokyo": "日本法",
    "jp": "日本法",
}


def _legal_basis(target_platform: str) -> str:
    """按目标平台映射法域。"""
    return LEGAL_DOMAINS.get((target_platform or "").lower(), "中国《著作权法》")


def _per_ref_violations(dna: dict[str, Any]) -> list[dict[str, Any]]:
    """校验单参考贡献模式数 ≤3；返回超限的 ref 列表。"""
    counts: dict[str, int] = {}
    for pat in dna.get("transferable_patterns", []) or []:
        refs = pat.get("source_refs") or ([pat["source_ref"]] if pat.get("source_ref") else [])
        for ref in refs:
            if ref:
                counts[ref] = counts.get(ref, 0) + 1
    return [{"ref_id": r, "pattern_count": c}
            for r, c in sorted(counts.items()) if c > PER_REF_PATTERN_CAP]


def build_review(dna: dict[str, Any], *, target_platform: str = "douyin",
                 references: list[dict[str, Any]] | None = None,
                 keywords: dict[str, list[str]] | None = None) -> dict[str, Any]:
    """构造 G0 结构化审查记录（不落盘）。"""
    patterns = dna.get("transferable_patterns", []) or []
    migrated = [{"feature_axis": p.get("feature_axis"), "value": p.get("value"),
                 "ip_layer": p.get("ip_layer", "structural")} for p in patterns]
    forbidden = dna.get("forbidden", []) or []

    # 词汇级 IP 预筛汇总（扫 DNA + 参考登记文本）
    scan_payload: Any = {"dna": dna, "references": references or []}
    prescreen = ip_prescreen.prescreen(scan_payload, keywords)
    per_ref_violations = _per_ref_violations(dna)

    # 决议：有词汇命中 / 单参考超限 → block；否则 pass（仍需人工确认）
    blocked = bool(prescreen["lexical_hit"]) or bool(per_ref_violations)
    decision = "block" if blocked else "pass"

    return {
        "gate": "G0",
        "decision": decision,
        "reviewer": "human_required",
        "checklist": {
            "migrated_structure": migrated,               # 迁移的结构
            "untouched_expression": list(forbidden),      # 不碰的表达
            "legal_basis": _legal_basis(target_platform),  # 法域
            "target_platform": target_platform,
            "per_ref_cap": PER_REF_PATTERN_CAP,
            "per_ref_cap_ok": not per_ref_violations,     # 单参考 ≤3 校验
            "per_ref_violations": per_ref_violations,
            "lexical_hit": prescreen["lexical_hit"],      # lexical_hit 汇总
            "structural_check": prescreen["structural_check"],  # defer_to_G0_human
        },
    }


def run_gate(project: str | Path, dna: dict[str, Any], *,
             target_platform: str = "douyin",
             references: list[dict[str, Any]] | None = None,
             keywords: dict[str, list[str]] | None = None,
             out: str | Path | None = None) -> dict[str, Any]:
    """跑 G0 闸：构造记录 → 写记录文件 → 追写 events.jsonl（与 G3/G6/G9 同构）。"""
    review = build_review(dna, target_platform=target_platform,
                          references=references, keywords=keywords)

    out_path = Path(out) if out else project_path(project, "ledger", "g0-review.json")
    write_json(out_path, review)

    event = _ledger.append_event(project, {
        "type": "g0_review",
        "gate": "G0",
        "decision": review["decision"],
        "reviewer": "human_required",
        "lexical_hit_count": len(review["checklist"]["lexical_hit"]),
        "per_ref_cap_ok": review["checklist"]["per_ref_cap_ok"],
        "note": f"G0 版权审查 decision={review['decision']}",
    })

    review["event_id"] = event["event_id"]
    review["record_path"] = str(out_path)
    return review


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="G0 版权审查闸（M2，确定性·不触网）")
    parser.add_argument("--project", required=True)
    parser.add_argument("--dna", required=True, help="C14 CreativeDNA 文件（yaml/json）")
    parser.add_argument("--platform", default="douyin", help="目标平台（douyin/tokyo/...）")
    parser.add_argument("--refs", help="C12 参考登记文件（可选，用于词汇扫描）")
    parser.add_argument("--out", help="审查记录输出路径")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    dna = read_yaml(args.dna)
    references = None
    if args.refs:
        rdata = read_yaml(args.refs) or {}
        references = rdata if isinstance(rdata, list) else (
            rdata.get("reference_works") or rdata.get("refs") or [])
    review = run_gate(args.project, dna, target_platform=args.platform,
                      references=references, out=args.out)

    if args.json:
        print(json.dumps(review, ensure_ascii=False))
    else:
        print(f"G0 审查：decision={review['decision']} reviewer={review['reviewer']} "
              f"法域={review['checklist']['legal_basis']} "
              f"词汇命中 {len(review['checklist']['lexical_hit'])} 条 "
              f"-> {review['record_path']}（事件 {review['event_id']}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
