#!/usr/bin/env python3
"""观众反馈闭环（设计稿 §9 路线图 D-7，SK0，轻量）。

发布后把观众反馈结构化收集 → 聚合 → 回写跨项目经验库，形成学习回路：
- 读 09_publish/audience-feedback.yaml（C11 原始反馈，逐条 platform/sentiment/category）。
- 聚合：总数 / 情感分布 / 类别分布 / 情感分（正向占比-负向占比）/ 高频负面类别。
- 回写：把聚合洞察以一条 lesson 追加进 cross-project-lessons.yaml（同 project_id 覆盖，幂等）。

观众/社区启发仅入经验文本（活文档），不进可执行契约的能力数字。
确定性：聚合纯由输入派生，可复现、不触网。

CLI：
  python feedback_intake.py --project <dir> [--feedback <path>]
      [--lessons cross-project-lessons.yaml] [--json]
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
from _common import read_yaml, write_yaml, project_path, ensure_validate_importable  # noqa: E402

ensure_validate_importable()
from validate import validate_obj  # noqa: E402

FEEDBACK_REL = ("09_publish", "audience-feedback.yaml")


def _feedback_path(project: str | Path, override: str | Path | None) -> Path:
    if override:
        return Path(override)
    return project_path(project, *FEEDBACK_REL)


def aggregate(feedback: dict[str, Any]) -> dict[str, Any]:
    """由 items 聚合派生情感/类别分布与情感分（确定性）。"""
    items = feedback.get("items", []) or []
    by_sentiment: dict[str, int] = {}
    by_category: dict[str, int] = {}
    neg_by_category: dict[str, int] = {}

    for it in items:
        sent = it.get("sentiment", "neutral")
        by_sentiment[sent] = by_sentiment.get(sent, 0) + 1
        cat = it.get("category")
        if cat:
            by_category[cat] = by_category.get(cat, 0) + 1
            if sent == "negative":
                neg_by_category[cat] = neg_by_category.get(cat, 0) + 1

    total = len(items)
    pos = by_sentiment.get("positive", 0)
    neg = by_sentiment.get("negative", 0)
    sentiment_score = round((pos - neg) / total, 4) if total else 0.0

    # 高频负面类别（计数降序，并列按类别名稳定排序）
    top_negative = [c for c, _ in sorted(neg_by_category.items(),
                                         key=lambda kv: (-kv[1], kv[0]))]

    return {
        "total": total,
        "by_sentiment": by_sentiment,
        "by_category": by_category,
        "sentiment_score": sentiment_score,
        "top_negative_categories": top_negative,
    }


def load_feedback(project: str | Path, *,
                  feedback_path: str | Path | None = None) -> dict[str, Any]:
    path = _feedback_path(project, feedback_path)
    if not path.exists():
        proj = read_yaml(project_path(project, "project.yaml"))
        return {"project_id": proj.get("id", "unknown"),
                "title": proj.get("title", ""), "items": []}
    return read_yaml(path)


def build_feedback(project: str | Path, *,
                   feedback_path: str | Path | None = None) -> dict[str, Any]:
    """读原始反馈 → 计算 aggregate → 校验 C11 → 返回完整结构。"""
    feedback = load_feedback(project, feedback_path=feedback_path)
    feedback.setdefault("collected_at", datetime.date.today().isoformat())
    feedback["aggregate"] = aggregate(feedback)
    validate_obj(feedback, "C11")
    return feedback


def _lessons_path(project: str | Path, override: str | Path | None) -> Path:
    if override:
        return Path(override).resolve()
    return project_path(project, "..", "cross-project-lessons.yaml").resolve()


def writeback(project: str | Path, *,
              feedback_path: str | Path | None = None,
              lessons_path: str | Path | None = None) -> dict[str, Any]:
    """聚合反馈 → 以一条 audience_feedback lesson 回写经验库（幂等）。"""
    feedback = build_feedback(project, feedback_path=feedback_path)
    agg = feedback["aggregate"]
    pid = feedback.get("project_id", "unknown")

    lesson = {
        "project_id": pid,
        "title": feedback.get("title"),
        "kind": "audience_feedback",
        "collected_at": feedback.get("collected_at"),
        "feedback_total": agg["total"],
        "sentiment_score": agg["sentiment_score"],
        "top_negative_categories": agg["top_negative_categories"],
    }

    # 同 project_id 同 kind 覆盖（幂等），与 lessons_writeback 的结案经验并存
    path = _lessons_path(project, lessons_path)
    book = read_yaml(path) if path.exists() else {"lessons": []}
    book.setdefault("lessons", [])
    book["lessons"] = [l for l in book["lessons"]
                       if not (l.get("project_id") == pid
                               and l.get("kind") == "audience_feedback")]
    book["lessons"].append(lesson)
    write_yaml(path, book)

    # 同时把聚合后的反馈写回项目（保留 aggregate 段）
    out_path = _feedback_path(project, feedback_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    write_yaml(out_path, feedback)

    return {"feedback_out": str(out_path), "lessons_path": str(path),
            "aggregate": agg, "total_lessons": len(book["lessons"])}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="观众反馈闭环（D-7，SK0，轻量）")
    parser.add_argument("--project", required=True)
    parser.add_argument("--feedback", help="原始反馈路径（缺省 09_publish/audience-feedback.yaml）")
    parser.add_argument("--lessons", help="经验库路径（缺省项目同级 cross-project-lessons.yaml）")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    result = writeback(args.project, feedback_path=args.feedback,
                       lessons_path=args.lessons)
    agg = result["aggregate"]
    if args.json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        print(f"反馈聚合：共 {agg['total']} 条，情感分 {agg['sentiment_score']:+.2f}")
        if agg["top_negative_categories"]:
            print(f"  高频负面类别：{'、'.join(agg['top_negative_categories'])}")
        print(f"  已回写经验库 -> {result['lessons_path']}（共 {result['total_lessons']} 条）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
