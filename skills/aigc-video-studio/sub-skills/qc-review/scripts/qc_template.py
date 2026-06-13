#!/usr/bin/env python3
"""逐镜质检表 + QCReport（设计稿 §5 SK7 / §3.2 C10，Phase 4 可用实现）。

按 shotlist 为每镜生成 C10 检查表骨架（issues 预置标准检查项占位，供人工/VLM 填充），
并接入 libs/failure-patterns.yaml 做已知失败模式匹配：
- 每条问题定位到镜头 + 时间码（in_tc-out_tc，由 shotlist 时长累加派生）。
- 分级 blocker/major/minor + AI 置信度 + 命中失败模式 ref + 最低成本处置建议。
- 处置优先级：剪辑规避 > 局部重跑 > 整镜重做（命中模式时直接采用其 remedy）。
- 同时产出 08_edit/qc-report.yaml（C10 结构化）与 08_edit/qc-report.md（人读评审报告）。

确定性：检查项/时间码/失败模式匹配均由输入派生，可复现，不触网。
AI 置信度为占位（None）等待 VLM/人工回填；脚本不臆造数值。

CLI：
  python qc_template.py --project <dir> [--out 08_edit/qc-report.yaml]
                        [--md 08_edit/qc-report.md] [--json]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str((Path(__file__).resolve().parent.parent.parent
                        / "_shared" / "scripts")))
from _common import read_yaml, write_yaml, project_path, ensure_validate_importable  # noqa: E402

ensure_validate_importable()
from validate import validate_obj  # noqa: E402

# 白皮书踩坑表标准检查类别（顺序即 issues 生成顺序，test_p2_smoke 依赖 2 镜 × 6 项）
CHECK_CATEGORIES = ["角色漂移", "穿模", "透视异常", "时代错配", "AI逻辑错误", "音画不同步"]

# 检查类别 → failure-patterns.yaml 模式 id 的语义映射（命中即取其 remedy）
CATEGORY_TO_FP = {
    "角色漂移": "FP-001",
    "穿模": "FP-003",
    "时代错配": "FP-004",
    "AI逻辑错误": "FP-005",  # 塑料感/AI 味归入 AI 逻辑错误范畴
}

# 处置优先级（数值越小成本越低，用于排序展示）
REMEDY_RANK = {"剪辑规避": 0, "局部重跑": 1, "整镜重做": 2}


def _tc(seconds: float) -> str:
    m, s = divmod(int(round(seconds)), 60)
    return f"{m:02d}:{s:02d}"


def load_failure_patterns() -> dict[str, dict[str, Any]]:
    """读 _shared/libs/failure-patterns.yaml，返回 id → 模式 映射。"""
    fp_path = (Path(__file__).resolve().parent.parent.parent
               / "_shared" / "libs" / "failure-patterns.yaml")
    if not fp_path.exists():
        return {}
    data = read_yaml(fp_path)
    return {p["id"]: p for p in data.get("patterns", []) if p.get("id")}


def _shot_time_index(shots: list[dict[str, Any]]) -> dict[str, str]:
    """按 order 累加时长，给每镜派生时间码定位 in_tc-out_tc。"""
    ordered = sorted(shots, key=lambda s: s.get("order", 0))
    idx: dict[str, str] = {}
    cursor = 0.0
    for shot in ordered:
        dur = float(shot.get("duration_s", 0))
        idx[shot["shot_id"]] = f"{_tc(cursor)}-{_tc(cursor + dur)}"
        cursor += dur
    return idx


def _remedy_for(category: str, fps: dict[str, dict[str, Any]]) -> tuple[str, str | None]:
    """按检查类别匹配失败模式，返回（处置建议, 命中的模式 id 或 None）。

    命中模式则采用其 remedy（已按优先级编写）；未命中则留空待人工裁定。
    """
    fp_id = CATEGORY_TO_FP.get(category)
    if fp_id and fp_id in fps:
        return fps[fp_id].get("remedy", ""), fp_id
    return "", None


def build_report(project: str | Path, *, check_level: str = "shot") -> dict[str, Any]:
    shotlist = read_yaml(project_path(project, "04_storyboard", "shotlist.yaml"))
    shots = shotlist.get("shots", [])
    fps = load_failure_patterns()
    tc_index = _shot_time_index(shots)

    issues: list[dict[str, Any]] = []
    for shot in shots:
        sid = shot["shot_id"]
        for cat in CHECK_CATEGORIES:
            remedy, fp_ref = _remedy_for(cat, fps)
            issue = {
                "shot_id": sid,
                "timecode": tc_index.get(sid, ""),
                "severity": "minor",
                "category": cat,
                "description": f"[待检] {cat}",
                "ai_confidence": None,  # 待 VLM/人工回填，不臆造
                "remedy": remedy,
            }
            if fp_ref:
                issue["failure_pattern_ref"] = fp_ref
            issues.append(issue)

    report = {
        "shot_id_scope": "sequence",
        "check_level": check_level,
        "issues": issues,
        "verdict": "needs_fix",
    }
    validate_obj(report, "C10")
    return report


def render_md(report: dict[str, Any], fps: dict[str, dict[str, Any]] | None = None) -> str:
    """渲染 qc-report.md（人读评审报告）。"""
    fps = fps or load_failure_patterns()
    sev_count = {"blocker": 0, "major": 0, "minor": 0}
    for i in report["issues"]:
        sev_count[i["severity"]] = sev_count.get(i["severity"], 0) + 1

    lines = ["# QC 评审报告（QCReport）", "",
             "> SK7 质检评审。问题定位到镜头 + 时间码，分级 blocker/major/minor，",
             "> 处置遵循最低成本优先级：剪辑规避 > 局部重跑 > 整镜重做。", "",
             f"- 检查范围：`{report['shot_id_scope']}`（{report.get('check_level', 'shot')} 级）",
             f"- 裁决：**{report['verdict']}**",
             f"- 问题计数：blocker {sev_count['blocker']} / "
             f"major {sev_count['major']} / minor {sev_count['minor']}",
             "",
             "## 逐条问题",
             "",
             "| 镜头 | 时间码 | 分级 | 类别 | 描述 | AI 置信 | 命中模式 | 处置建议 |",
             "|---|---|---|---|---|---|---|---|"]
    # 处置成本升序展示（先看能否剪辑规避）
    ordered = sorted(report["issues"],
                     key=lambda i: REMEDY_RANK.get((i.get("remedy") or "").split("（")[0], 9))
    for i in ordered:
        conf = "—" if i.get("ai_confidence") is None else f"{i['ai_confidence']:.2f}"
        ref = i.get("failure_pattern_ref", "") or "—"
        remedy = i.get("remedy") or "（待裁定）"
        lines.append(f"| {i.get('shot_id', '?')} | {i.get('timecode', '')} "
                     f"| {i['severity']} | {i.get('category', '')} | {i['description']} "
                     f"| {conf} | {ref} | {remedy} |")
    lines.append("")

    # 命中的失败模式说明
    hit_ids = sorted({i.get("failure_pattern_ref") for i in report["issues"]
                      if i.get("failure_pattern_ref")})
    if hit_ids:
        lines += ["## 命中的已知失败模式（failure-patterns）", "",
                  "| 模式 | 名称 | 适用模型 | 症状 | 修复路径 |",
                  "|---|---|---|---|---|"]
        for fid in hit_ids:
            p = fps.get(fid, {})
            applies = "、".join(p.get("applies_to", []))
            lines.append(f"| {fid} | {p.get('name', '')} | {applies} "
                         f"| {p.get('symptom', '')} | {p.get('remedy', '')} |")
        lines.append("")

    lines += ["## 处置优先级说明", "",
              "1. **剪辑规避**（最低成本）：裁切/遮挡/换镜规避，不重跑生成。",
              "2. **局部重跑**：仅改对应 GenSpec 字段（运镜/negative/身份锁）并 bump version。",
              "3. **整镜重做**（最高成本）：整镜 prompt 重写重生成，仅在前两者无效时采用。",
              ""]
    return "\n".join(lines) + "\n"


def generate(project: str | Path, *, out: str | Path | None = None,
             md: str | Path | None = None) -> dict[str, Any]:
    report = build_report(project)
    out_path = Path(out) if out else project_path(project, "08_edit", "qc-report.yaml")
    write_yaml(out_path, report)

    fps = load_failure_patterns()
    md_path = Path(md) if md else project_path(project, "08_edit", "qc-report.md")
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text(render_md(report, fps), encoding="utf-8")

    matched = sum(1 for i in report["issues"] if i.get("failure_pattern_ref"))
    return {"out": str(out_path), "md_out": str(md_path),
            "issue_count": len(report["issues"]),
            "pattern_matched": matched}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="逐镜质检表 + QCReport（SK7）")
    parser.add_argument("--project", required=True)
    parser.add_argument("--out", help="C10 结构化输出（缺省 08_edit/qc-report.yaml）")
    parser.add_argument("--md", help="人读报告路径（缺省 08_edit/qc-report.md）")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    result = generate(args.project, out=args.out, md=args.md)
    if args.json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        print(f"质检表 {result['issue_count']} 项（命中失败模式 {result['pattern_matched']} 项）"
              f" -> {result['out']}")
        print(f"  评审报告 -> {result['md_out']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
