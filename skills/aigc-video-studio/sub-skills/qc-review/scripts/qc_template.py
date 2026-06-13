#!/usr/bin/env python3
"""逐镜质检表骨架生成（设计稿 §5 SK7 / §3.2 C10，P2 轻量实现）。

按 shotlist 为每个镜头生成 C10 检查表骨架（issues 预置标准检查项占位），
供人工/VLM 填充。检查项硬编码自白皮书踩坑表。

CLI：
  python qc_template.py --project <dir> [--out 08_edit/qc-report.yaml] [--json]
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

# 白皮书踩坑表标准检查类别
CHECK_CATEGORIES = ["角色漂移", "穿模", "透视异常", "时代错配", "AI逻辑错误", "音画不同步"]


def build_report(project: str | Path, *, check_level: str = "shot") -> dict[str, Any]:
    shotlist = read_yaml(project_path(project, "04_storyboard", "shotlist.yaml"))
    issues: list[dict[str, Any]] = []
    for shot in shotlist.get("shots", []):
        for cat in CHECK_CATEGORIES:
            issues.append({
                "shot_id": shot["shot_id"],
                "severity": "minor",
                "category": cat,
                "description": f"[待检] {cat}",
                "ai_confidence": None,
                "remedy": "",
            })
    report = {
        "shot_id_scope": "sequence",
        "check_level": check_level,
        "issues": issues,
        "verdict": "needs_fix",
    }
    validate_obj(report, "C10")
    return report


def generate(project: str | Path, *, out: str | Path | None = None) -> dict[str, Any]:
    report = build_report(project)
    out_path = Path(out) if out else project_path(project, "08_edit", "qc-report.yaml")
    write_yaml(out_path, report)
    return {"out": str(out_path), "issue_count": len(report["issues"])}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="逐镜质检表骨架（SK7，P2）")
    parser.add_argument("--project", required=True)
    parser.add_argument("--out")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    result = generate(args.project, out=args.out)
    if args.json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        print(f"质检表骨架 {result['issue_count']} 项 -> {result['out']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
