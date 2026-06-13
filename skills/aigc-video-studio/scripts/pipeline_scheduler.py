#!/usr/bin/env python3
"""流水线并行调度（设计稿 §5 SK0 / 7.3，Q-6，P1）。

核心理念：在人工/选片等待窗口，并行推进可独立的下游任务，压缩单人吞吐瓶颈。

确定性逻辑：读 shotlist 各镜 status，按依赖规则推导“当前可并行推进的任务”。
镜头级状态流水（简化）：
  pending → generating →(回收+VLM)→ screened → selected → locked

调度规则：
- 处于 generating 的镜头 = “等待窗口”（人/adapter 在产片）；
- 在该窗口可并行：① 编译下一批未编译镜头（pending 且已有 shotlist 定义）
  ② 对已 selected 的镜头排音频/终渲下游任务。
- 同平台/同通道的任务建议排同批（parallel_group）。

输出调度计划（机读），供 SK0 编排决策。本脚本不改任何状态文件（只读）。

CLI：
  python pipeline_scheduler.py --project <dir> [--max-parallel 4] [--json]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

SHARED_SCRIPTS = (Path(__file__).resolve().parent.parent
                  / "sub-skills" / "_shared" / "scripts")
sys.path.insert(0, str(SHARED_SCRIPTS))
from _common import read_yaml, project_path  # noqa: E402

# 镜头状态 → 下一可并行推进的下游任务类型
STATUS_NEXT_TASK = {
    "pending": "compile_genspec",     # 未编译 → 可编译
    "compiled": "dispatch_draft",     # 已编译 → 可发抽卡批
    "generating": None,               # 等待窗口（人/adapter 在产片）
    "ingested": "vlm_screen",         # 已回收 → 可初筛
    "screened": "await_select",       # 已初筛 → 等人选片（人工 Gate）
    "selected": "audio_and_final",    # 已选片 → 可排音频 + 终渲
    "locked": None,                   # 完成
}

# 等待窗口状态：处于这些状态说明有“空档”可并行推进别的镜头
WAITING_STATUSES = {"generating", "screened"}


def _load_shotlist(project: str | Path) -> dict[str, Any]:
    path = project_path(project, "04_storyboard", "shotlist.yaml")
    if not path.exists():
        return {"shots": []}
    return read_yaml(path)


def build_schedule(project: str | Path, *, max_parallel: int = 4) -> dict[str, Any]:
    """推导调度计划。返回 {waiting_window, ready_tasks[], parallel_groups[]}。"""
    shotlist = _load_shotlist(project)
    shots = shotlist.get("shots", [])

    in_waiting = [s["shot_id"] for s in shots
                  if s.get("status") in WAITING_STATUSES]
    waiting_window = bool(in_waiting)

    ready_tasks: list[dict[str, Any]] = []
    for s in shots:
        status = s.get("status", "pending")
        task = STATUS_NEXT_TASK.get(status)
        if task and task != "await_select":
            ready_tasks.append({
                "shot_id": s["shot_id"],
                "task": task,
                "from_status": status,
                "platform_hint": s.get("variant") or s.get("lens_type") or "default",
            })

    # 同 task+platform_hint 归并为并行组，受 max_parallel 限制
    groups: dict[str, list[str]] = {}
    for t in ready_tasks:
        key = f"{t['task']}::{t['platform_hint']}"
        groups.setdefault(key, []).append(t["shot_id"])

    parallel_groups = []
    for key, shot_ids in groups.items():
        task, hint = key.split("::", 1)
        # 按 max_parallel 切片成多个可并行批
        for i in range(0, len(shot_ids), max_parallel):
            parallel_groups.append({
                "task": task, "platform_hint": hint,
                "shots": shot_ids[i:i + max_parallel],
            })

    return {
        "waiting_window": waiting_window,
        "in_waiting": in_waiting,
        "ready_tasks": ready_tasks,
        "parallel_groups": parallel_groups,
        "max_parallel": max_parallel,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="流水线并行调度表（SK0）")
    parser.add_argument("--project", required=True)
    parser.add_argument("--max-parallel", type=int, default=4)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    plan = build_schedule(args.project, max_parallel=args.max_parallel)

    if args.json:
        print(json.dumps(plan, ensure_ascii=False))
    else:
        print(f"等待窗口：{'是' if plan['waiting_window'] else '否'}"
              f"（{plan['in_waiting'] or '无'}）")
        print(f"可并行任务 {len(plan['ready_tasks'])} 项，分 {len(plan['parallel_groups'])} 组：")
        for g in plan["parallel_groups"]:
            print(f"  [{g['task']} / {g['platform_hint']}] {g['shots']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
