#!/usr/bin/env python3
"""结案经验回写（设计稿 §7.3 / §9 V2 可选，SK0，轻量）。

项目结案时把可复用经验回写到跨项目经验库 cross-project-lessons.yaml：
- 命中率最高/最低的 prompt_pattern_tag（取自 metrics）
- 检出的失败模式（取自 qc-report 命中的 failure_pattern_ref）
- 手填要点（--note）

经验库为活文档，供后续项目冷启动参考（仅经验文本，不入可执行契约）。
确定性：统计来自 metrics/qc，不触网。

CLI：
  python lessons_writeback.py --project <dir> [--lessons cross-project-lessons.yaml]
      [--note "..."] [--json]
"""
from __future__ import annotations

import argparse
import datetime
import json
import sys
from pathlib import Path
from typing import Any

SHARED_SCRIPTS = (Path(__file__).resolve().parent.parent
                  / "sub-skills" / "_shared" / "scripts")
sys.path.insert(0, str(SHARED_SCRIPTS))
from _common import read_yaml, write_yaml, project_path  # noqa: E402
import metrics as _metrics  # noqa: E402


def _top_tags(report: dict[str, Any]) -> dict[str, Any]:
    by_tag = report.get("by_tag", {})
    if not by_tag:
        return {"best": None, "worst": None}
    ranked = sorted(by_tag.items(), key=lambda kv: kv[1]["hit_rate"])
    return {"worst": {"tag": ranked[0][0], "hit_rate": ranked[0][1]["hit_rate"]},
            "best": {"tag": ranked[-1][0], "hit_rate": ranked[-1][1]["hit_rate"]}}


def _failure_patterns(project: str | Path) -> list[str]:
    qc = project_path(project, "08_edit", "qc-report.yaml")
    if not qc.exists():
        return []
    refs = set()
    for issue in read_yaml(qc).get("issues", []) or []:
        fp = issue.get("failure_pattern_ref")
        if fp:
            refs.add(fp)
    return sorted(refs)


def build_lesson(project: str | Path, *, note: str = "") -> dict[str, Any]:
    proj = read_yaml(project_path(project, "project.yaml"))
    report = _metrics.collect(project)
    tags = _top_tags(report)
    return {
        "project_id": proj.get("id"),
        "title": proj.get("title"),
        "format": proj.get("format"),
        "closed_at": datetime.date.today().isoformat(),
        "overall_hit_rate": report.get("overall_hit_rate"),
        "best_pattern": tags["best"],
        "worst_pattern": tags["worst"],
        "failure_patterns_seen": _failure_patterns(project),
        "note": note,
    }


def writeback(project: str | Path, *, lessons_path: str | Path | None = None,
              note: str = "") -> dict[str, Any]:
    lesson = build_lesson(project, note=note)
    path = Path(lessons_path) if lessons_path else project_path(project, "..", "cross-project-lessons.yaml")
    path = path.resolve()
    book = read_yaml(path) if path.exists() else {"lessons": []}
    book.setdefault("lessons", [])
    # 同 project_id 覆盖（结案幂等）
    book["lessons"] = [l for l in book["lessons"] if l.get("project_id") != lesson["project_id"]]
    book["lessons"].append(lesson)
    write_yaml(path, book)
    return {"lessons_path": str(path), "lesson": lesson,
            "total_lessons": len(book["lessons"])}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="结案经验回写（SK0，可选）")
    parser.add_argument("--project", required=True)
    parser.add_argument("--lessons", help="经验库路径（缺省项目同级 cross-project-lessons.yaml）")
    parser.add_argument("--note", default="")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    result = writeback(args.project, lessons_path=args.lessons, note=args.note)
    if args.json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        print(f"经验已回写 -> {result['lessons_path']}（共 {result['total_lessons']} 条）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
