#!/usr/bin/env python3
"""事件源账本（设计稿 §3.2 C8 / §4 单写者矩阵，S-P1-4）。

设计：
- ledger/events.jsonl —— append-only 流水（单写者），每行一条事件 JSON。
- ledger/summary.yaml —— 由事件流重放重建的派生快照，可随时从 events 重算。

幂等：每条事件带 event_id；重复追加同一 event_id 不重复记账（去重）。

CLI：
  python ledger.py --project <dir> --append --type take_cost --shot SHOT-07 --cny 12
  python ledger.py --project <dir> --rebuild         # 由 events 重算 summary
  python ledger.py --project <dir> --show [--json]
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import read_yaml, write_yaml, project_path, ensure_validate_importable  # noqa: E402

ensure_validate_importable()
from validate import validate_obj  # noqa: E402

EVENT_TYPES = {"take_cost", "ai_qc_cost", "human_minutes", "hidden_cost", "stage_advance", "adjust"}


def _ledger_dir(project: str | Path) -> Path:
    return project_path(project, "ledger")


def events_path(project: str | Path) -> Path:
    return _ledger_dir(project) / "events.jsonl"


def summary_path(project: str | Path) -> Path:
    return _ledger_dir(project) / "summary.yaml"


def _now_iso() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def make_event_id(event: dict[str, Any]) -> str:
    """由内容派生确定性 event_id（用于幂等去重）。

    若调用方已显式提供 event_id 则沿用；否则按关键字段 hash。
    """
    if event.get("event_id"):
        return event["event_id"]
    basis = json.dumps(
        {k: event.get(k) for k in ("ts", "type", "shot_id", "taskcard", "cny", "credits",
                                   "minutes", "category", "note")},
        ensure_ascii=False,
        sort_keys=True,
    )
    return "ev-" + hashlib.sha256(basis.encode("utf-8")).hexdigest()[:16]


def read_events(project: str | Path) -> list[dict[str, Any]]:
    path = events_path(project)
    if not path.exists():
        return []
    events = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            events.append(json.loads(line))
    return events


def _existing_ids(project: str | Path) -> set[str]:
    return {e["event_id"] for e in read_events(project) if e.get("event_id")}


def append_event(project: str | Path, event: dict[str, Any]) -> dict[str, Any]:
    """追加一条事件（幂等）。返回写入后的事件 dict。

    若 event_id 已存在则跳过追加（幂等），但仍返回该事件。
    """
    event = dict(event)
    event.setdefault("ts", _now_iso())
    if event.get("type") not in EVENT_TYPES:
        raise ValueError(f"未知事件类型：{event.get('type')}（可用：{sorted(EVENT_TYPES)}）")
    event["event_id"] = make_event_id(event)

    path = events_path(project)
    path.parent.mkdir(parents=True, exist_ok=True)

    if event["event_id"] in _existing_ids(project):
        # 幂等：已记录过，不重复追加
        rebuild_summary(project)
        return event

    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(event, ensure_ascii=False) + "\n")
    rebuild_summary(project)
    return event


def rebuild_summary(project: str | Path) -> dict[str, Any]:
    """由 events.jsonl 重放重建 summary，并写回 summary.yaml。"""
    events = read_events(project)
    summary: dict[str, Any] = {
        "total_cny": 0.0,
        "total_credits": 0.0,
        "by_shot": {},
        "ai_qc_costs": 0.0,
        "human_minutes": 0.0,
        "hidden_costs": {},
        "event_count": len(events),
    }
    for e in events:
        cny = float(e.get("cny") or 0)
        credits = float(e.get("credits") or 0)
        etype = e.get("type")

        if etype == "take_cost":
            summary["total_cny"] += cny
            summary["total_credits"] += credits
            shot = e.get("shot_id")
            if shot:
                slot = summary["by_shot"].setdefault(
                    shot, {"cny": 0.0, "credits": 0.0, "take_count": 0})
                slot["cny"] += cny
                slot["credits"] += credits
                slot["take_count"] += 1
        elif etype == "ai_qc_cost":
            summary["ai_qc_costs"] += cny
            summary["total_cny"] += cny
        elif etype == "human_minutes":
            summary["human_minutes"] += float(e.get("minutes") or 0)
        elif etype == "hidden_cost":
            cat = e.get("category", "misc")
            summary["hidden_costs"][cat] = summary["hidden_costs"].get(cat, 0.0) + cny
            summary["total_cny"] += cny
        elif etype == "adjust":
            summary["total_cny"] += cny
            summary["total_credits"] += credits
        # stage_advance 不计费

    # 校验 C8（summary 段）
    validate_obj({"summary": summary}, "C8")
    write_yaml(summary_path(project), {"summary": summary})
    return summary


def get_summary(project: str | Path) -> dict[str, Any]:
    path = summary_path(project)
    if path.exists():
        return read_yaml(path)["summary"]
    return rebuild_summary(project)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="事件源账本")
    parser.add_argument("--project", required=True)
    parser.add_argument("--append", action="store_true")
    parser.add_argument("--rebuild", action="store_true")
    parser.add_argument("--show", action="store_true")
    parser.add_argument("--type", choices=sorted(EVENT_TYPES))
    parser.add_argument("--shot")
    parser.add_argument("--taskcard")
    parser.add_argument("--pass", dest="pass_", choices=["draft", "final"])
    parser.add_argument("--channel", choices=["api", "ui"])
    parser.add_argument("--cny", type=float)
    parser.add_argument("--credits", type=float)
    parser.add_argument("--minutes", type=float)
    parser.add_argument("--category")
    parser.add_argument("--note")
    parser.add_argument("--event-id")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    result: Any
    if args.append:
        if not args.type:
            print("--append 需要 --type", file=sys.stderr)
            return 2
        event = {k: v for k, v in {
            "event_id": args.event_id, "type": args.type, "shot_id": args.shot,
            "taskcard": args.taskcard, "pass": args.pass_, "channel": args.channel,
            "cny": args.cny, "credits": args.credits, "minutes": args.minutes,
            "category": args.category, "note": args.note,
        }.items() if v is not None}
        result = append_event(args.project, event)
    elif args.rebuild:
        result = rebuild_summary(args.project)
    else:  # 默认 show
        result = get_summary(args.project)

    if args.json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
