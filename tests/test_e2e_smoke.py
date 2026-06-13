"""端到端冒烟测试（设计稿 §9 MVP 验收门槛，最重要的交付物）。

用例《锈牛仔》（废土西部，6 镜头），用 mock API 通道（无需真实 key）依次驱动
「剧本 → 定角 → 编译 → 生成 → 选片」硬闭环：

  init_project → brief(C2) / screenplay(C3) / character(C4)
  → shotlist(C5, 含 control_level/render_passes 派生)
  → compile_genspec(C6, 四层 + 槽位预算 + reference_label_map + 两级 prompt_qc)
  → make_taskcards(按 shot×pass 出 UI 卡 + API 卡)
  → budget_guard(min(cap))
  → api_adapter(mock 产出 draft takes 占位文件)
  → ingest(写 TakeLog C9，记 pass/seed)
  → vlm_screen(协议分层初筛)
  → select_take(落实人工选片)
  → advance_stage(逐阶段推进 + G3/G6 强制 Gate)

Phase 4 起延伸到发布全链路（V1 完整单片）：
  选片(S6) → 音画 audio_manifest(S7) → 质检 qc_template(C10) + 剪辑 edl_render(S8)
  → 发布包 render_variants(S9) → DONE，验证 G7(默认自动)/G8/G9 Gate。
设计稿明确：音画合成/粗剪不计入 MVP 验收门槛，但 V1 链路打通仍需端到端验证。
测试可复现：每次用 pytest tmp_path 全新项目目录，mock 产物确定性派生，不触网。
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

# 复用 conftest 已注入 sys.path 的脚本目录
import init_project
import compile_genspec
import make_taskcards
import budget_guard
import api_adapter
import ingest
import vlm_screen
import select_take
import advance_stage
import ledger
from _common import read_yaml, write_yaml, project_path
from validate import validate_obj, validate_file


# --------------------------------------------------------------------------
# 用例素材：《锈牛仔》废土西部短片（6 镜头，覆盖 locked/guided/free 三档）
# --------------------------------------------------------------------------

ROBO_ID = "robo-cowboy"


def _brief() -> dict:
    """C2 ProjectBrief。"""
    return {
        "logline": "末世废土上，一具锈蚀的机械牛仔守着最后一口活水井。",
        "format": "short_film",
        "worldview": "核战后两百年的美国西部，机械生命接管废墟",
        "tone": "苍凉、克制、史诗",
        "style_keywords": ["废土", "黄昏逆光", "胶片颗粒", "锈蚀金属"],
        "aspect_ratio": "16:9",
        "duration_target_s": 60,
        "target_platform": ["douyin", "bilibili"],
        "compliance_flags": {"human_face": False, "note": "非人类主角，规避真人脸合规"},
    }


def _screenplay() -> dict:
    """C3 Screenplay：含情绪曲线，无连续 3 场平值。"""
    scenes = [
        {"scene_id": "SC-01", "location": "废弃加油站", "time": "黄昏",
         "characters_present": [ROBO_ID], "core_action": "锈牛仔巡视水井",
         "emotion_value": 3, "est_shot_count": 2},
        {"scene_id": "SC-02", "location": "沙丘高地", "time": "黄昏",
         "characters_present": [ROBO_ID], "core_action": "察觉远处沙尘异动",
         "emotion_value": 6, "est_shot_count": 2},
        {"scene_id": "SC-03", "location": "水井旁", "time": "入夜",
         "characters_present": [ROBO_ID], "core_action": "握紧转轮，守护水源",
         "emotion_value": 9, "est_shot_count": 2},
    ]
    return {
        "synopsis": "无台词音画叙事：锈牛仔从巡视到警觉再到死守的情绪三段式。",
        "scenes": scenes,
        "emotion_curve": [{"scene_id": s["scene_id"], "value": s["emotion_value"]}
                          for s in scenes],
        "character_briefs": [{"id": ROBO_ID, "name": "锈牛仔", "role": "protagonist"}],
    }


def _character_card() -> dict:
    """C4 CharacterCard：双语 identity_strategy，无伪参数 weight。"""
    return {
        "id": ROBO_ID,
        "name": "锈牛仔",
        "role": "protagonist",
        "compliance": {"human_face": False},
        "feature_card": {
            "appearance": "锈迹斑斑的机械牛仔，黄铜骨架外露，破旧牛仔帽",
            "materials": "氧化黄铜、磨损皮革、风化钢",
            "accessories": "左轮转轮、褪色红围巾",
            "silhouette": "高瘦、单肩微垂",
            "behavior_traits": "听到声响先压低帽檐、右手本能移向转轮",
        },
        "identity_strategy": {
            "ref_order": ["front", "side"],
            "prompt_lock_zh": "锈蚀机械牛仔，黄铜骨架，破旧牛仔帽",
            "prompt_lock_en": "rusty robotic cowboy, brass skeleton, worn cowboy hat",
            "negative_zh": "光滑塑料感，崭新，磨皮",
            "negative_en": "smooth plastic, brand new, airbrushed skin",
        },
        "voice_ref": None,
        "locked": False,
    }


def _shotlist() -> dict:
    """C5 Shotlist：6 镜头，覆盖 locked / guided / free 三档 control_level。"""
    base = {
        "characters": [ROBO_ID],
        "shot_size": "中景",
        "camera_move": "缓慢推轨",
        "composition": "主体居右三分纵线，视线导向左上对角",
        "action_logic": "锈牛仔停步，压低帽檐，右手移向腰部转轮",
        "audio_cue": "风声渐弱，金属吱呀声渐近，无对白",
        "ambience_group": "加油站",
    }
    shots = [
        dict(base, shot_id="SHOT-01", order=1, duration_s=4, control_level="guided",
             first_frame="04_storyboard/boards/SHOT-01-frame.png", status="generating"),
        dict(base, shot_id="SHOT-02", order=2, duration_s=3, control_level="free",
             first_frame=None, status="generating"),
        dict(base, shot_id="SHOT-03", order=3, duration_s=5, control_level="locked",
             first_frame="04_storyboard/boards/SHOT-03-frame.png", status="generating"),
        dict(base, shot_id="SHOT-04", order=4, duration_s=4, control_level="guided",
             first_frame="04_storyboard/boards/SHOT-04-frame.png", status="generating"),
        dict(base, shot_id="SHOT-05", order=5, duration_s=6, control_level="guided",
             first_frame="04_storyboard/boards/SHOT-05-frame.png", status="generating"),
        dict(base, shot_id="SHOT-06", order=6, duration_s=5, control_level="locked",
             first_frame="04_storyboard/boards/SHOT-06-frame.png", status="generating"),
    ]
    return {"meta": {"scene_count": 3, "shot_count": len(shots),
                     "est_duration_s": sum(s["duration_s"] for s in shots)},
            "shots": shots}


# --------------------------------------------------------------------------
# 夹具：构造已落盘到 S5 之前各阶段产物的《锈牛仔》项目
# --------------------------------------------------------------------------

@pytest.fixture
def rusty_project(tmp_path):
    """初始化《锈牛仔》项目，落 brief/screenplay/character/shotlist（均过契约校验）。"""
    res = init_project.init_project("rusty-cowboy", "锈牛仔",
                                    projects_root=str(tmp_path), do_git=False)
    proj = Path(res["project_dir"])

    # S1 brief（C2）
    brief = _brief()
    validate_obj(brief, "C2")
    write_yaml(proj / "01_brief" / "brief.yaml", brief)
    (proj / "01_brief" / "brief.md").write_text("# 锈牛仔 · 项目蓝图\n见 brief.yaml\n",
                                                 encoding="utf-8")

    # S2 screenplay（C3）
    sp = _screenplay()
    validate_obj(sp, "C3")
    write_yaml(proj / "02_screenplay" / "screenplay.yaml", sp)
    (proj / "02_screenplay" / "screenplay.md").write_text("# 锈牛仔 · 剧本\n见 screenplay.yaml\n",
                                                           encoding="utf-8")

    # S3 character（C4）
    card = _character_card()
    validate_obj(card, "C4")
    write_yaml(project_path(proj, "03_characters", ROBO_ID, "card.yaml"), card)

    # S4 shotlist（C5）
    sl = _shotlist()
    validate_obj(sl, "C5")
    write_yaml(project_path(proj, "04_storyboard", "shotlist.yaml"), sl)

    return proj


# --------------------------------------------------------------------------
# 测试 1：阶段产物逐契约校验 + 状态机推进 + G3/G6 强制 Gate
# --------------------------------------------------------------------------

def test_stage_artifacts_validate_and_advance_with_mandatory_gates(rusty_project):
    """每个 stage 产物按契约生成并通过 validate；G3/G6 强制 Gate 存在且拦截推进。"""
    proj = rusty_project

    # 产物文件按契约校验（C2/C3/C4/C5）
    validate_file(proj / "01_brief" / "brief.yaml", "C2")
    validate_file(proj / "02_screenplay" / "screenplay.yaml", "C3")
    validate_file(project_path(proj, "03_characters", ROBO_ID, "card.yaml"), "C4")
    validate_file(project_path(proj, "04_storyboard", "shotlist.yaml"), "C5")

    # S0 → S1 → S2 → S3：无 Gate 拦截，逐级推进
    for target in ("S1_BRIEF", "S2_SCRIPT", "S3_CHARACTER"):
        r = advance_stage.advance(proj, to=target, do_git=False)
        assert r["advanced"] is True, f"应能推进到 {target}：{r.get('hints')}"

    # 关键断言①：G3 角色定稿是强制人工 Gate —— 未 passed 时不可进 S4
    blocked = advance_stage.advance(proj, to="S4_STORYBOARD", do_git=False)
    assert blocked["advanced"] is False
    assert blocked["check"]["required_gate"] == "G3_character"

    # 人工过 G3 后方可推进（project.yaml.gates 由 SK0 维护）
    pj = read_yaml(project_path(proj, "project.yaml"))
    pj["gates"]["G3_character"]["status"] = "passed"
    validate_obj(pj, "C1")
    write_yaml(project_path(proj, "project.yaml"), pj)

    r = advance_stage.advance(proj, to="S4_STORYBOARD", do_git=False)
    assert r["advanced"] is True
    r = advance_stage.advance(proj, to="S5_PROMPTS", do_git=False)
    assert r["advanced"] is True


# --------------------------------------------------------------------------
# 测试 2：编译 GenSpec —— 四层 + 槽位预算 + reference_label_map + render_passes + 两级 QC
# --------------------------------------------------------------------------

def test_compile_genspec_layers_slots_labelmap_renderpasses_and_qc(rusty_project):
    proj = rusty_project
    shotlist_path = project_path(proj, "04_storyboard", "shotlist.yaml")
    genspec_dir = project_path(proj, "05_prompts", "genspecs")
    genspec_dir.mkdir(parents=True, exist_ok=True)

    import prompt_qc

    passes_by_control = {}
    for shot in _shotlist()["shots"]:
        gs = compile_genspec.compile_from_shotlist(
            shotlist_path, shot["shot_id"], style_core="废土黄昏胶片质感")
        validate_obj(gs, "C6")  # C6 写前校验

        # 四层结构齐备
        for layer in ("layer0_deai", "layer1_setting", "layer2_style", "layer3_shot"):
            assert gs["prompt"][layer]

        # 槽位预算：身份槽位映射进 reference_label_map（@语义名 -> @ImageN）
        assert any(v.startswith("@Image") for v in gs["reference_label_map"].values())

        # 两级 prompt_qc：结构八要素无硬阻断（用例提示词齐备）
        qc = prompt_qc.run_qc(gs)
        assert qc["structural_blockers"] == [], f"{shot['shot_id']} 八要素缺项：{qc}"
        gs["prompt_qc"] = qc
        validate_obj(gs, "C6")

        passes_by_control[shot["control_level"]] = [p["pass"] for p in gs["render_passes"]]
        write_yaml(genspec_dir / f"{shot['shot_id']}.yaml", gs)

    # 关键断言②：render_passes 按 control_level 正确派生
    assert passes_by_control["guided"] == ["draft", "final"]   # 双 pass
    assert passes_by_control["locked"] == ["final"]            # 仅终渲
    assert passes_by_control["free"] == ["draft"]              # 仅抽卡

    assert len(list(genspec_dir.glob("*.yaml"))) == 6


# --------------------------------------------------------------------------
# 测试 3（核心）：完整闭环 编译→出卡→护栏→生成→回收→初筛→选片
# --------------------------------------------------------------------------

def test_full_closed_loop_compile_to_select(rusty_project):
    """硬闭环验收：mock API 跑通一镜的 draft 双卡实例化、生成、登记、初筛、选片。"""
    proj = rusty_project
    shotlist_path = project_path(proj, "04_storyboard", "shotlist.yaml")
    genspec_dir = project_path(proj, "05_prompts", "genspecs")
    genspec_dir.mkdir(parents=True, exist_ok=True)

    # --- 编译一个 guided 镜（产出 draft+final 双 pass） ---
    shot_id = "SHOT-01"
    gs = compile_genspec.compile_from_shotlist(shotlist_path, shot_id,
                                               style_core="废土黄昏胶片质感")
    gs_path = genspec_dir / f"{shot_id}.yaml"
    write_yaml(gs_path, gs)

    # --- 出卡：按 (shot×pass) 实例化 UI + API 两张卡 ---
    batch_dir = project_path(proj, "05_prompts", "taskcards", "batch-01")
    tc_res = make_taskcards.make_taskcards([gs], batch_dir, start_tc=1)
    by_channel = {c["channel"]: c for c in tc_res["cards"]}

    # 关键断言③：render_passes 双 pass → UI 卡 + API 卡各一张
    assert by_channel["api"]["pass"] == "draft"
    assert by_channel["ui"]["pass"] == "final"
    api_card_path = batch_dir / by_channel["api"]["file"]
    assert api_card_path.suffix == ".json"          # API 卡机读
    assert (batch_dir / by_channel["ui"]["file"]).suffix == ".md"  # UI 卡人读
    validate_file(api_card_path, "C7")

    # --- 预算护栏：按 min(project=80, genspec=50) 工作 ---
    guard = budget_guard.check_batch(proj, shot_id=shot_id, batch_cost_cny=40,
                                     genspec={"per_shot_cost_cap_cny": 50})
    assert guard["allowed"] is True
    assert guard["effective_per_shot_cap"] == 50    # 取更严者

    blocked = budget_guard.check_batch(proj, shot_id=shot_id, batch_cost_cny=70,
                                       genspec={"per_shot_cost_cap_cny": 50})
    assert blocked["allowed"] is False              # 70 > min(cap)=50 拦截

    # --- api_adapter：mock 产出 draft takes（无真实 key，确定性占位文件） ---
    api_card = read_yaml(api_card_path)
    inbox = project_path(proj, "06_generations", shot_id, "inbox")
    run = api_adapter.execute_card(api_card, inbox, mock=True)
    assert run["mock"] is True
    assert len(run["products"]) == api_card["rolling"]["takes_planned"]
    assert run["seeds"], "API 产物必须带 seed 追溯"
    # 产物落地 inbox
    assert all((inbox / p).exists() for p in run["products"])

    # --- ingest：回收入 takes/，写 TakeLog（C9，记 pass/seed），追写 events.jsonl ---
    ing = ingest.ingest_shot(proj, shot_id, pass_="draft", channel="api",
                             cost_cny=10.0)
    assert len(ing["ingested"]) == len(run["products"])
    takelog_path = project_path(proj, "06_generations", shot_id, "takes.yaml")
    validate_file(takelog_path, "C9")
    takelog = read_yaml(takelog_path)
    # 关键断言④：TakeLog 记 pass + seed
    assert all(t["pass"] == "draft" for t in takelog["takes"])
    assert all(t["platform_meta"]["seed"] is not None for t in takelog["takes"])

    # --- vlm_screen：协议分层初筛，回写 scores.agent_vlm，记 ai_qc_cost ---
    screen = vlm_screen.screen_shot(proj, shot_id, mock=True)
    assert screen["screened"] == len(takelog["takes"])
    takelog = read_yaml(takelog_path)
    for t in takelog["takes"]:
        av = t["scores"]["agent_vlm"]
        assert av["protocol"] in ("static", "dynamic")
        assert av["verdict"] in ("pass_to_human", "auto_reject", "unverifiable")
        assert av["verdict"] != "auto_accept"      # 永不 auto_accept

    # --- select_take：落实人工选片（不可选 auto_reject 废片） ---
    pickable = next(t["take_id"] for t in takelog["takes"]
                    if t["scores"]["agent_vlm"]["verdict"] != "auto_reject")
    sel = select_take.select_take(proj, shot_id, pickable, do_git=False)
    assert sel["selected_take"] == pickable
    takelog = read_yaml(takelog_path)
    assert takelog["selected_take"] == pickable
    # shotlist 该镜 status 被回写
    assert sel["shotlist_updated"] is True

    # 关键断言⑤：ledger events.jsonl 可重放出 summary（成本闭环）
    summary = ledger.rebuild_summary(proj)
    assert summary["event_count"] >= 2              # take_cost + ai_qc_cost
    assert summary["by_shot"][shot_id]["take_count"] == len(run["products"])
    assert summary["ai_qc_costs"] > 0


# --------------------------------------------------------------------------
# 测试 4：auto_reject 废片不可被选为定版（防误选护栏）
# --------------------------------------------------------------------------

def test_auto_reject_take_cannot_be_selected(rusty_project):
    proj = rusty_project
    shot_id = "SHOT-01"

    # 构造一条会被 VLM auto_reject 的 take（take_id 含 "fail" → identity=FAIL+高置信）
    takelog = {
        "shot_id": shot_id,
        "takes": [{
            "take_id": f"{shot_id}-fail", "pass": "draft", "channel": "api",
            "file": "takes/SHOT-01-fail.mp4",
            "platform_meta": {"seed": 1, "model_version": "seedance-2.0"},
            "scores": {}, "rejected_reason": None, "status": "ingested",
        }],
        "selected_take": None, "rerun_history": [],
    }
    write_yaml(project_path(proj, "06_generations", shot_id, "takes.yaml"), takelog)

    vlm_screen.screen_shot(proj, shot_id, mock=True)
    tl = read_yaml(project_path(proj, "06_generations", shot_id, "takes.yaml"))
    assert tl["takes"][0]["scores"]["agent_vlm"]["verdict"] == "auto_reject"

    with pytest.raises(ValueError, match="auto_reject"):
        select_take.select_take(proj, shot_id, f"{shot_id}-fail", do_git=False)


# --------------------------------------------------------------------------
# 测试 5：发布全链路 S6选片 → S7_AUDIO_POST → S8_EDIT → S9_PUBLISH → DONE
# --------------------------------------------------------------------------

def _seed_all_takes_and_select(proj):
    """为 6 镜各写一条可选 take 并选片（直接落 TakeLog，跳过生成细节）。"""
    for shot in _shotlist()["shots"]:
        sid = shot["shot_id"]
        tid = f"{sid}-t01"
        takelog = {
            "shot_id": sid,
            "takes": [{
                "take_id": tid, "pass": "draft", "channel": "api",
                "file": f"takes/{tid}.mp4",
                "platform_meta": {"seed": 7, "model_version": "seedance-2.0"},
                "scores": {}, "rejected_reason": None, "status": "ingested",
            }],
            "selected_take": tid, "rerun_history": [],
        }
        write_yaml(project_path(proj, "06_generations", sid, "takes.yaml"), takelog)


def test_publish_pipeline_audio_edit_publish_to_done(rusty_project):
    """全链路验收：选片后 S7 音画 → S8 剪辑 → S9 发布 → DONE，含 G7/G8/G9 Gate。"""
    import audio_manifest
    import qc_template
    import edl_render
    import render_variants

    proj = rusty_project

    # 前置：把项目状态推进到 S6（过 G3），并为 6 镜落选定 take
    pj = read_yaml(project_path(proj, "project.yaml"))
    pj["gates"]["G3_character"]["status"] = "passed"
    pj["stage"] = "S6_GENERATION"
    validate_obj(pj, "C1")
    write_yaml(project_path(proj, "project.yaml"), pj)
    _seed_all_takes_and_select(proj)

    # 风格圣经（供 EDL 调色参数导出）
    style_dir = project_path(proj, "03_style")
    style_dir.mkdir(parents=True, exist_ok=True)
    (style_dir / "style-bible.md").write_text(
        "# 风格圣经\n- 色温：暖黄\n- 对比度：中高\n- 颗粒：胶片中等\n", encoding="utf-8")

    # 关键断言①：G6 选片是强制人工 Gate —— 未 passed 不可进 S7
    blocked = advance_stage.advance(proj, to="S7_AUDIO_POST", do_git=False)
    assert blocked["advanced"] is False
    assert blocked["check"]["required_gate"] == "G6_select"

    # 人工过 G6
    pj = read_yaml(project_path(proj, "project.yaml"))
    pj["gates"]["G6_select"]["status"] = "passed"
    write_yaml(project_path(proj, "project.yaml"), pj)

    # --- SK8 音频：audio_manifest 产出 audio-plan.md + manifest（含版权登记/桥接） ---
    a_res = audio_manifest.generate(proj)
    assert Path(a_res["plan_out"]).exists()
    assert (project_path(proj, "07_audio", "audio-plan.md")).exists()
    manifest = read_yaml(project_path(proj, "07_audio", "audio-manifest.yaml"))
    assert manifest["timeline"], "时间轴应非空"
    # 相邻同 ambience_group 镜头标桥接（用例 6 镜同组）
    assert any(e["bridge_prev"] for e in manifest["timeline"])

    # 推进 S6 → S7（G6 已过）
    r = advance_stage.advance(proj, to="S7_AUDIO_POST", do_git=False)
    assert r["advanced"] is True, r.get("hints")

    # --- SK7 质检：qc_template 产出 C10 报告（yaml + md），命中失败模式 ---
    qc_res = qc_template.generate(proj)
    qc_yaml = project_path(proj, "08_edit", "qc-report.yaml")
    validate_file(qc_yaml, "C10")                 # 关键断言②：C10 校验通过
    assert Path(qc_res["md_out"]).exists()
    assert qc_res["pattern_matched"] > 0          # 接入 failure-patterns 命中

    # --- SK9 剪辑：edl_render 产出 edl.md（拼接/转场/调色/QC 处置映射） ---
    edl_res = edl_render.generate(proj)
    edl_md = project_path(proj, "08_edit", "edl.md")
    assert edl_md.exists()
    assert edl_res["clip_count"] == 6
    edl_text = edl_md.read_text(encoding="utf-8")
    assert "统一调色" in edl_text and "硬切" in edl_text or "叠化" in edl_text

    # 关键断言③：G7 音画合成确认默认自动 —— 不显式过也能 S7 → S8
    r = advance_stage.advance(proj, to="S8_EDIT", do_git=False)
    assert r["advanced"] is True, r.get("hints")
    assert r["check"]["auto_gate"] == "G7_audio"

    # --- SK10 发布：render_variants.build_package 产出各平台发布包 ---
    pkg = render_variants.build_package(proj)
    assert len(pkg["packages"]) == 2              # douyin + bilibili
    for p in pkg["packages"]:
        pdir = Path(p["dir"])
        assert (pdir / "aigc-declaration.md").exists()   # AIGC 声明强制
        assert (pdir / "variants.yaml").exists()
        assert (pdir / "cover.yaml").exists()
        assert (pdir / "metadata.yaml").exists()

    # 关键断言④：G8 完整性终审为强制 Gate —— 未过不可进 S9
    blocked = advance_stage.advance(proj, to="S9_PUBLISH", do_git=False)
    assert blocked["advanced"] is False
    assert blocked["check"]["required_gate"] == "G8_integrity"

    pj = read_yaml(project_path(proj, "project.yaml"))
    pj["gates"]["G8_integrity"]["status"] = "passed"
    write_yaml(project_path(proj, "project.yaml"), pj)
    r = advance_stage.advance(proj, to="S9_PUBLISH", do_git=False)
    assert r["advanced"] is True, r.get("hints")

    # 关键断言⑤：G9 发布确认（不可逆）为强制 Gate —— 未过不可达 DONE
    blocked = advance_stage.advance(proj, to="DONE", do_git=False)
    assert blocked["advanced"] is False
    assert blocked["check"]["required_gate"] == "G9_publish"

    pj = read_yaml(project_path(proj, "project.yaml"))
    pj["gates"]["G9_publish"]["status"] = "passed"
    write_yaml(project_path(proj, "project.yaml"), pj)
    r = advance_stage.advance(proj, to="DONE", do_git=False)
    assert r["advanced"] is True, r.get("hints")

    # 终态断言：项目抵达 DONE
    pj = read_yaml(project_path(proj, "project.yaml"))
    assert pj["stage"] == "DONE"


# --------------------------------------------------------------------------
# 测试 6：G7 音画合成 Gate 被显式否决（rejected）时拦截 S7 → S8
# --------------------------------------------------------------------------

def test_g7_audio_gate_rejected_blocks_s8(rusty_project):
    proj = rusty_project
    # 直接把项目置于 S7，产物齐备
    (project_path(proj, "07_audio", "audio-plan.md")).parent.mkdir(parents=True, exist_ok=True)
    (project_path(proj, "07_audio", "audio-plan.md")).write_text("# plan\n", encoding="utf-8")
    pj = read_yaml(project_path(proj, "project.yaml"))
    pj["stage"] = "S7_AUDIO_POST"
    pj["gates"]["G7_audio"]["status"] = "rejected"   # 人工/premium 否决音画
    write_yaml(project_path(proj, "project.yaml"), pj)

    blocked = advance_stage.advance(proj, to="S8_EDIT", do_git=False)
    assert blocked["advanced"] is False
    assert blocked["check"]["auto_gate"] == "G7_audio"
    assert blocked["check"]["auto_gate_ok"] is False
