"""metrics 单测：按 prompt_pattern_tags 聚合抽卡/命中/成本。"""
from __future__ import annotations

import metrics
import ledger
from _common import project_path


def _seed(project_dir, write_yaml):
    # 两镜，各 2 take；t01 命中(pass_to_human)、fail02 未命中
    tl7 = {
        "shot_id": "SHOT-07",
        "takes": [
            {"take_id": "SHOT-07-t01", "pass": "draft", "channel": "api",
             "file": "takes/a.mp4", "platform_meta": {"seed": 1, "model_version": "seedance-2.0"},
             "scores": {"agent_vlm": {"verdict": "pass_to_human"}},
             "prompt_pattern_tags": ["推轨+逆光"], "rejected_reason": None, "status": "screened"},
            {"take_id": "SHOT-07-f02", "pass": "draft", "channel": "api",
             "file": "takes/b.mp4", "platform_meta": {"seed": 2, "model_version": "seedance-2.0"},
             "scores": {"agent_vlm": {"verdict": "auto_reject"}},
             "prompt_pattern_tags": ["推轨+逆光"], "rejected_reason": "drift", "status": "auto_rejected"},
        ],
        "selected_take": None, "rerun_history": [],
    }
    write_yaml(project_path(project_dir, "06_generations", "SHOT-07", "takes.yaml"), tl7)
    # 记成本 20 元在 SHOT-07（均摊到 2 take 各 10）
    ledger.append_event(project_dir, {"type": "take_cost", "shot_id": "SHOT-07",
                                      "cny": 20.0, "event_id": "c1"})


def test_collect_aggregates_by_tag(project_dir, write_yaml):
    _seed(project_dir, write_yaml)
    rep = metrics.collect(project_dir)
    assert rep["total_takes"] == 2
    assert rep["total_hits"] == 1
    assert rep["overall_hit_rate"] == 0.5
    tag = rep["by_tag"]["推轨+逆光"]
    assert tag["takes"] == 2
    assert tag["hits"] == 1
    assert tag["hit_rate"] == 0.5
    assert tag["cost_cny"] == 20.0


def test_selected_counts_as_hit(project_dir, write_yaml):
    tl = {
        "shot_id": "SHOT-09",
        "takes": [
            {"take_id": "SHOT-09-t01", "pass": "draft", "channel": "api",
             "file": "takes/x.mp4", "platform_meta": {"seed": 9, "model_version": "seedance-2.0"},
             "scores": {}, "prompt_pattern_tags": ["手持+特写"],
             "rejected_reason": None, "status": "selected"},
        ],
        "selected_take": "SHOT-09-t01", "rerun_history": [],
    }
    write_yaml(project_path(project_dir, "06_generations", "SHOT-09", "takes.yaml"), tl)
    rep = metrics.collect(project_dir)
    assert rep["by_tag"]["手持+特写"]["hits"] == 1


def test_empty_project_zero(project_dir):
    rep = metrics.collect(project_dir)
    assert rep["total_takes"] == 0
    assert rep["overall_hit_rate"] == 0.0
