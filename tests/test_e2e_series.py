"""端到端剧集模式冒烟测试（设计稿 §7.3 series 档 / §9 V2）。

用一个 2 集 mini 剧集驱动剧集模式关键路径：
  init_project(format=series) → 全剧共享角色卡（03_characters/）
  → episode_manager 建 ep-01 / ep-02 + 每集独立 shotlist
  → 每集 compile_genspec（行为逻辑分层 + 坐标构图，A.1/A.2）
  → cross_episode_drift 跨集一致性比对（mock）
  → episode_manager dashboard 汇总

确定性、不触网；与单片 e2e 并存。
"""
from __future__ import annotations

from pathlib import Path

import yaml

from _common import read_yaml, project_path

ROBO = {
    "id": "robo", "name": "锈牛仔",
    "feature_card": {"appearance": "锈迹斑斑的机械牛仔",
                     "behavior_traits": "动作迟缓但精准；紧张时反复擦拭枪管"},
    "identity_strategy": {"prompt_lock_zh": "锈牛仔", "prompt_lock_en": "rusty cowboy",
                          "negative_zh": "光滑", "negative_en": "shiny"},
    "variants": [{"variant_id": "v-dusty", "episode": "ep-02",
                  "state": "蒙尘", "appearance_delta": "全身覆沙尘"}],
}


def _write(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
                    encoding="utf-8")


def _ep_shotlist(ep_no: int, take_suffix: str):
    return {"meta": {"shot_count": 1}, "shots": [
        {"shot_id": "SHOT-01", "order": 1, "duration_s": 6, "control_level": "guided",
         "characters": ["robo"], "scene": f"第{ep_no}集 加油站", "shot_size": "中景",
         "composition": "主体右三分纵线，视线导左上对角", "camera_move": "缓慢推轨",
         "action_logic": "停步压帽，手移向转轮", "drama_type": "动作戏",
         "audio_cue": "风声", "ambience_group": "加油站"}]}


def test_series_pipeline_two_episodes(tmp_path):
    import init_project, episode_manager, register_check, compile_genspec, cross_episode_drift

    # 1) 初始化剧集项目
    res = init_project.init_project("rusty-series", "锈牛仔剧集", fmt="series",
                                    projects_root=str(tmp_path), do_git=False)
    pd = Path(res["project_dir"])
    proj = read_yaml(pd / "project.yaml")
    assert proj["format"] == "series" and proj["episodes"] == []

    # 2) 全剧共享角色卡（含 variant）→ register_check 通过
    _write(project_path(pd, "03_characters", "robo", "card.yaml"), ROBO)
    chk = register_check.check_card(ROBO)
    assert chk["ok"] and chk["variant_count"] == 1

    # 3) 建两集 + 每集独立 shotlist
    episode_manager.create_episode(pd, "第一集 沙暴")
    episode_manager.create_episode(pd, "第二集 对峙")
    assert [e["id"] for e in episode_manager.list_episodes(pd)] == ["ep-01", "ep-02"]

    for i, suffix in ((1, "t01"), (2, "t02")):
        ep_id = f"ep-{i:02d}"
        sl = project_path(pd, "02_screenplay", "episodes", ep_id,
                          "04_storyboard", "shotlist.yaml")
        _write(sl, _ep_shotlist(i, suffix))
        # 选定 take（普通 id → mock 判一致）
        td = project_path(pd, "02_screenplay", "episodes", ep_id,
                          "06_generations", "SHOT-01")
        _write(td / "takes.yaml", {"selected_take": f"SHOT-01-{suffix}"})

        # 4) 每集编译 GenSpec：行为逻辑分层 + 坐标构图注入（A.1/A.2）
        cards = {"robo": ROBO}
        g = compile_genspec.compile_from_shotlist(sl, "SHOT-01", project=pd)
        l3 = g["prompt"]["layer3_shot"]
        assert "构图（坐标化）" in l3 and "右三分纵线" in l3
        assert "行为逻辑（动作戏）" in l3 and "擦拭枪管" in l3  # behavior_traits 注入

    # 5) 跨集漂移检查（mock 普通 id → 全 ok，无漂移）
    drift = cross_episode_drift.generate(pd)
    assert drift["ok"] is True
    assert len(read_yaml(drift["out"])["comparisons"]) == 2  # 2 集各 1 条
    assert Path(drift["md_out"]).exists()

    # 6) 剧级 dashboard 汇总（每集镜头数=1）
    dash = episode_manager.generate_dashboard(pd)
    assert dash["episode_count"] == 2
    dash_md = (pd / "dashboard.md").read_text(encoding="utf-8")
    assert "ep-01" in dash_md and "ep-02" in dash_md


def test_series_pipeline_detects_cross_episode_drift(tmp_path):
    """第二集选定 take 含 'fail' → 跨集漂移被检出。"""
    import init_project, episode_manager, cross_episode_drift

    res = init_project.init_project("drift-series", "漂移剧", fmt="series",
                                    projects_root=str(tmp_path), do_git=False)
    pd = Path(res["project_dir"])
    _write(project_path(pd, "03_characters", "robo", "card.yaml"), ROBO)
    episode_manager.create_episode(pd, "第一集")
    episode_manager.create_episode(pd, "第二集")

    for i, suffix in ((1, "t01"), (2, "fail99")):  # 第二集漂移
        ep_id = f"ep-{i:02d}"
        sl = project_path(pd, "02_screenplay", "episodes", ep_id,
                          "04_storyboard", "shotlist.yaml")
        _write(sl, _ep_shotlist(i, suffix))
        td = project_path(pd, "02_screenplay", "episodes", ep_id,
                          "06_generations", "SHOT-01")
        _write(td / "takes.yaml", {"selected_take": f"SHOT-01-{suffix}"})

    drift = cross_episode_drift.check_drift(pd)
    assert drift["ok"] is False
    assert "robo" in drift["drift_characters"]
    # 第一集 ok、第二集 drift
    by_ep = {c["episode"]: c["status"] for c in drift["comparisons"]}
    assert by_ep["ep-01"] == "ok" and by_ep["ep-02"] == "drift"
