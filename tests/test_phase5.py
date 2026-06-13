"""Phase 5 单测：V1.5 连续性增强 + V2 剧集量产。

覆盖 A.1 行为逻辑分层 / A.2 坐标构图 / A.3 环境音桥接 / A.4 尾帧延续 /
A.5 渠道成本路由，与 B.1 剧集初始化 / B.2 variants 校验 / B.3 跨集漂移 /
B.4 复用镜头库 / B.5 A/B 变体与 metrics 对比 / B.6 经验回写。
确定性、不触网；与既有 101 测试并存不回归。
"""
from __future__ import annotations

from pathlib import Path

from _common import read_yaml, project_path


# ============================ A.1 行为逻辑分层 ============================
def test_behavior_logic_action_drama_uses_traits():
    import compile_genspec
    shot = {"shot_id": "SHOT-07", "scene": "废弃加油站，黄昏",
            "characters": ["robo"], "drama_type": "动作戏",
            "action_logic": "压低帽檐，手移向腰部转轮", "composition": "右三分纵线"}
    cards = {"robo": {"feature_card": {"behavior_traits": "紧张时反复擦拭枪管"}}}
    bl = compile_genspec.build_behavior_logic(shot, cards)
    assert bl["drama_type"] == "动作戏"
    names = [l["layer"] for l in bl["layers"]]
    assert names == ["处境层", "动作层", "因果层", "留白层"]
    # R5：动机取自 behavior_traits
    assert "擦拭枪管" in bl["layered_text"]
    assert bl["motivation_source"] == "robo.behavior_traits"
    # R4 留白层显式声明
    assert any("自由发挥" in l["text"] for l in bl["layers"])


def test_behavior_logic_emotion_drama_has_emotion_layer():
    import compile_genspec
    shot = {"shot_id": "SHOT-01", "characters": ["x"], "drama_type": "情感戏",
            "action_logic": "落泪", "scene": "废墟"}
    bl = compile_genspec.build_behavior_logic(shot, {})
    assert "情绪层" in [l["layer"] for l in bl["layers"]]


def test_behavior_logic_default_drama_type():
    import compile_genspec
    bl = compile_genspec.build_behavior_logic({"characters": []}, {})
    assert bl["drama_type"] == "动作戏"  # 缺省


def test_compile_layers_inject_behavior_and_composition():
    import compile_genspec
    shot = {"shot_id": "SHOT-07", "scene": "加油站", "characters": ["robo"],
            "shot_size": "中景", "composition": "右三分纵线，视线导左上对角",
            "camera_move": "推轨", "action_logic": "停步压帽", "drama_type": "动作戏"}
    cards = {"robo": {"feature_card": {"behavior_traits": "迟缓但精准"}}}
    g = compile_genspec.compile_genspec(shot, character_cards=cards)
    l3 = g["prompt"]["layer3_shot"]
    assert "构图（坐标化）" in l3 and "右三分纵线" in l3
    assert "行为逻辑" in l3 and "迟缓但精准" in l3


# ============================ A.2 坐标化构图 ============================
def test_composition_block_fallback():
    import compile_genspec
    block = compile_genspec.build_composition_block({"shot_size": "全景"})
    assert "三分线" in block  # 缺 composition 时回退三分占位


# ============================ A.3 环境音桥接 ============================
def test_ambience_shared_bed(project_dir, write_yaml, shotlist_doc):
    import audio_manifest
    write_yaml(project_path(project_dir, "04_storyboard", "shotlist.yaml"), shotlist_doc)
    m = audio_manifest.build_manifest(project_dir)
    # shotlist_doc 两镜同 ambience_group=加油站 → 一条共享床
    groups = m["ambience_groups"]
    assert len(groups) == 1
    g = groups[0]
    assert g["ambience_group"] == "加油站"
    assert set(g["shots"]) == {"SHOT-07", "SHOT-08"}
    assert g["bed_start_s"] == 0.0 and g["bed_end_s"] > 0


def test_edl_ambience_bridge_track(project_dir, write_yaml, shotlist_doc):
    import audio_manifest, edl_render
    write_yaml(project_path(project_dir, "04_storyboard", "shotlist.yaml"), shotlist_doc)
    audio_manifest.generate(project_dir)  # 先产出 audio-manifest（含 ambience_groups）
    edl = edl_render.build_edl(project_dir)
    assert edl["ambience_bridges"]
    md = edl_render.render_md(edl)
    assert "环境音桥接轨" in md


# ============================ A.4 尾帧延续 ============================
def test_continuity_in_genspec_and_cards(tmp_path):
    import compile_genspec, make_taskcards
    shot = {"shot_id": "SHOT-08", "characters": ["robo"], "shot_size": "近景",
            "composition": "中心", "camera_move": "固定", "action_logic": "回头",
            "control_level": "guided",
            "continuity": {"prev_shot": "SHOT-07",
                           "last_frame_file": "06_generations/SHOT-07/tail.png",
                           "micro_motion_lead_s": 0.5}}
    g = compile_genspec.compile_genspec(shot)
    assert g["continuity"]["prev_shot"] == "SHOT-07"
    # API 卡注入尾帧参考槽 + continuity 段
    res = make_taskcards.make_taskcards([g], tmp_path)
    api = next(c for c in res["cards"] if c["channel"] == "api")
    import json
    data = json.loads((tmp_path / api["file"]).read_text(encoding="utf-8"))
    assert data["continuity"]["prev_shot"] == "SHOT-07"
    assert any(r["slot"] == "@PrevTail" for r in data["references"])
    # UI 卡（final）含尾帧延续段
    ui = next((c for c in res["cards"] if c["channel"] == "ui"), None)
    if ui:
        md = (tmp_path / ui["file"]).read_text(encoding="utf-8")
        assert "尾帧延续" in md


# ============================ A.5 渠道成本路由 ============================
def test_channel_cost_estimate_and_cheapest():
    import budget_guard
    est = budget_guard.estimate_channel_cost("falai_reference_to_video", seconds=10)
    assert est["supported"] and est["unit"] == "cny" and est["cost"] == 8.0
    assert est["verified_at"]  # 挂 verified_at
    # ui 渠道按积分
    ui = budget_guard.estimate_channel_cost("higgsfield_cinema_studio", shots=2)
    assert ui["unit"] == "credits" and ui["cost"] == 48.0
    # 未知渠道
    assert budget_guard.estimate_channel_cost("nope")["supported"] is False
    # 最便宜 api 渠道（volcano 0.6 < falai 0.8）
    best = budget_guard.cheapest_channel(seconds=10)
    assert best["channel"] == "volcano_seedance"


# ============================ B.1 剧集初始化 + episode_manager ============================
def test_series_init_and_episode_manager(tmp_path):
    import init_project, episode_manager
    res = init_project.init_project("ser", "测试剧", fmt="series",
                                    projects_root=str(tmp_path), do_git=False)
    pd = Path(res["project_dir"])
    proj = read_yaml(pd / "project.yaml")
    assert proj["format"] == "series" and proj["episodes"] == []
    e1 = episode_manager.create_episode(pd, "第一集")
    e2 = episode_manager.create_episode(pd, "第二集")
    assert e1["episode"]["id"] == "ep-01" and e2["episode"]["id"] == "ep-02"
    assert (pd / "02_screenplay" / "episodes" / "ep-01.md").exists()
    eps = episode_manager.list_episodes(pd)
    assert [e["id"] for e in eps] == ["ep-01", "ep-02"]
    dash = episode_manager.generate_dashboard(pd)
    assert dash["episode_count"] == 2
    assert (pd / "dashboard.md").exists()


def test_episode_manager_rejects_non_series(project_dir):
    import episode_manager
    # project_dir 是 short_film
    try:
        episode_manager.create_episode(project_dir, "X")
        assert False, "应拒绝非 series"
    except ValueError:
        pass


# ============================ B.2 variants 校验 ============================
def _base_card():
    return {"id": "robo", "name": "锈牛仔",
            "feature_card": {"appearance": "锈机械牛仔"},
            "identity_strategy": {"prompt_lock_zh": "锈牛仔", "prompt_lock_en": "rusty cowboy",
                                  "negative_zh": "光滑", "negative_en": "shiny"}}


def test_register_check_variants_ok():
    import register_check
    card = _base_card()
    card["variants"] = [{"variant_id": "v-injured", "episode": "ep-02",
                         "state": "受伤", "appearance_delta": "右臂裂痕"}]
    res = register_check.check_card(card)
    assert res["ok"] and res["variant_count"] == 1


def test_register_check_variants_duplicate_id():
    import register_check
    card = _base_card()
    card["variants"] = [{"variant_id": "v1", "state": "a"},
                        {"variant_id": "v1", "state": "b"}]
    res = register_check.check_card(card)
    assert res["ok"] is False
    assert any("重复" in e for e in res["errors"])


def test_register_check_variant_missing_id():
    import register_check
    card = _base_card()
    card["variants"] = [{"state": "无 id"}]
    res = register_check.check_card(card)
    assert res["ok"] is False


# ============================ B.3 跨集漂移 ============================
def _setup_series_with_char(tmp_path, take_suffix):
    import init_project, episode_manager
    res = init_project.init_project("drift", "漂移剧", fmt="series",
                                    projects_root=str(tmp_path), do_git=False)
    pd = Path(res["project_dir"])
    # 全剧共享角色卡
    import yaml
    cd = pd / "03_characters" / "robo"
    cd.mkdir(parents=True, exist_ok=True)
    (cd / "card.yaml").write_text(yaml.safe_dump(_base_card(), allow_unicode=True),
                                  encoding="utf-8")
    episode_manager.create_episode(pd, "第一集")
    # 该集 shotlist 含该角色
    sl = pd / "02_screenplay" / "episodes" / "ep-01" / "04_storyboard" / "shotlist.yaml"
    sl.parent.mkdir(parents=True, exist_ok=True)
    sl.write_text(yaml.safe_dump(
        {"shots": [{"shot_id": "SHOT-01", "order": 1, "duration_s": 5,
                    "control_level": "guided", "characters": ["robo"]}]},
        allow_unicode=True), encoding="utf-8")
    # 选定 take（id 决定 mock 裁决）
    td = pd / "02_screenplay" / "episodes" / "ep-01" / "06_generations" / "SHOT-01"
    td.mkdir(parents=True, exist_ok=True)
    (td / "takes.yaml").write_text(yaml.safe_dump(
        {"selected_take": f"SHOT-01-{take_suffix}"}, allow_unicode=True), encoding="utf-8")
    return pd


def test_cross_episode_drift_ok(tmp_path):
    import cross_episode_drift
    pd = _setup_series_with_char(tmp_path, "t01")  # 普通 id → PASS
    rep = cross_episode_drift.check_drift(pd)
    assert rep["comparisons"]
    assert rep["ok"] is True
    assert rep["comparisons"][0]["status"] == "ok"


def test_cross_episode_drift_detected(tmp_path):
    import cross_episode_drift
    pd = _setup_series_with_char(tmp_path, "fail01")  # 含 fail → 漂移
    rep = cross_episode_drift.check_drift(pd)
    assert rep["ok"] is False
    assert "robo" in rep["drift_characters"]
    res = cross_episode_drift.generate(pd)
    assert Path(res["out"]).exists() and Path(res["md_out"]).exists()


# ============================ B.4 复用镜头库 ============================
def test_reuse_shots_register_and_query(project_dir):
    import reuse_shots
    r1 = reuse_shots.register(project_dir, kind="empty", tags=["沙暴", "黄昏"],
                              episode="ep-01", shot="SHOT-03", file="a.mp4", duration_s=4)
    reuse_shots.register(project_dir, kind="transition", tags=["加油站"],
                         episode="ep-01", shot="SHOT-05", file="b.mp4")
    assert r1["reuse_id"] == "RS-001"
    q = reuse_shots.query(project_dir, tags=["沙暴", "加油站"])
    # 两条各命中 1 个标签
    assert q["total_matched"] == 2
    # kind 过滤
    qe = reuse_shots.query(project_dir, tags=["沙暴"], kind="empty")
    assert qe["total_matched"] == 1 and qe["candidates"][0]["reuse_id"] == "RS-001"


# ============================ B.5 A/B 变体 + metrics 对比 ============================
def test_compile_variants_ab(shotlist_shot):
    import compile_genspec
    variants = compile_genspec.compile_variants(shotlist_shot)
    assert len(variants) == 2
    tags = {v["prompt_pattern_tag"] for v in variants}
    assert tags == {"variant-A", "variant-B"}
    assert variants[0]["version"] == 1 and variants[1]["version"] == 2


def test_metrics_compare_ab():
    import metrics
    report = {"by_tag": {
        "variant-A": {"takes": 10, "hits": 7, "hit_rate": 0.7, "cost_cny": 14.0, "cost_per_hit_cny": 2.0},
        "variant-B": {"takes": 10, "hits": 4, "hit_rate": 0.4, "cost_cny": 12.0, "cost_per_hit_cny": 3.0},
    }}
    cmp = metrics.compare_ab(".", "variant-A", "variant-B", report=report)
    assert cmp["winner"] == "variant-A"
    assert cmp["hit_rate_delta"] == 0.3


def test_metrics_compare_ab_tie_uses_cost():
    import metrics
    report = {"by_tag": {
        "a": {"takes": 5, "hits": 3, "hit_rate": 0.6, "cost_cny": 6.0, "cost_per_hit_cny": 2.0},
        "b": {"takes": 5, "hits": 3, "hit_rate": 0.6, "cost_cny": 9.0, "cost_per_hit_cny": 3.0},
    }}
    cmp = metrics.compare_ab(".", "a", "b", report=report)
    assert cmp["winner"] == "a"  # 命中率并列 → 单位成本低者胜


# ============================ B.6 经验回写 ============================
def test_lessons_writeback(project_dir, tmp_path):
    import lessons_writeback
    lessons = tmp_path / "cross-project-lessons.yaml"
    res = lessons_writeback.writeback(project_dir, lessons_path=str(lessons),
                                      note="结案测试")
    assert lessons.exists()
    book = read_yaml(lessons)
    assert len(book["lessons"]) == 1
    assert book["lessons"][0]["note"] == "结案测试"
    # 幂等：同项目再写覆盖不新增
    lessons_writeback.writeback(project_dir, lessons_path=str(lessons), note="再次")
    book2 = read_yaml(lessons)
    assert len(book2["lessons"]) == 1 and book2["lessons"][0]["note"] == "再次"
