"""pipeline_scheduler 单测：等待窗口识别、就绪任务推导、并行分组、只读不改状态。"""
from __future__ import annotations

import pipeline_scheduler
from _common import read_yaml, project_path


def _shotlist(statuses):
    shots = []
    for i, st in enumerate(statuses, 1):
        shots.append({"shot_id": f"SHOT-{i:02d}", "order": i, "duration_s": 8,
                      "status": st})
    return {"meta": {"shot_count": len(shots)}, "shots": shots}


def test_waiting_window_detected(project_dir, write_yaml):
    sl = _shotlist(["generating", "pending"])
    write_yaml(project_path(project_dir, "04_storyboard", "shotlist.yaml"), sl)
    plan = pipeline_scheduler.build_schedule(project_dir)
    assert plan["waiting_window"] is True
    assert "SHOT-01" in plan["in_waiting"]


def test_ready_tasks_exclude_await_select(project_dir, write_yaml):
    # generating(等待) + screened(等人选,await_select 不入就绪) + pending(可编译)
    sl = _shotlist(["generating", "screened", "pending"])
    write_yaml(project_path(project_dir, "04_storyboard", "shotlist.yaml"), sl)
    plan = pipeline_scheduler.build_schedule(project_dir)
    tasks = {t["task"] for t in plan["ready_tasks"]}
    assert "compile_genspec" in tasks       # pending → 可编译
    assert "await_select" not in tasks       # screened 不进就绪队列


def test_parallel_grouping_respects_max(project_dir, write_yaml):
    sl = _shotlist(["pending"] * 5)
    write_yaml(project_path(project_dir, "04_storyboard", "shotlist.yaml"), sl)
    plan = pipeline_scheduler.build_schedule(project_dir, max_parallel=2)
    # 5 个 pending 同任务同 hint → 按 2 切片成 3 组
    compile_groups = [g for g in plan["parallel_groups"] if g["task"] == "compile_genspec"]
    assert len(compile_groups) == 3
    assert all(len(g["shots"]) <= 2 for g in compile_groups)


def test_read_only_no_mutation(project_dir, write_yaml):
    sl = _shotlist(["pending", "generating"])
    sl_path = project_path(project_dir, "04_storyboard", "shotlist.yaml")
    write_yaml(sl_path, sl)
    before = read_yaml(sl_path)
    pipeline_scheduler.build_schedule(project_dir)
    after = read_yaml(sl_path)
    assert before == after
