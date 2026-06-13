"""Phase 6 单测：V2.2+ 扩展层（半自动/轻量优先）。

覆盖 D-2 参考片风格迁移 / D-3 剪辑工程导出 / D-6 资产索引深化 /
Q-8 多平台发布自动化 / Q-9 任务卡 UI 截图位 / Q-10 失败模式库深化 /
Q-12 隐性成本统计 / D-7 观众反馈闭环。
确定性、不触网；与既有测试并存不回归。
"""
from __future__ import annotations

import json
from pathlib import Path
from xml.etree import ElementTree as ET

import yaml

from _common import read_yaml, project_path


# ============================ D-2 参考片风格迁移 ============================
def test_reference_analyzer_normalize_descriptors():
    import reference_analyzer
    clip = {"title": "参考片A", "source": "影片X",
            "annotations": {"palette": "低饱和暖黄,青影调", "lighting": "硬光逆光",
                            "camera": "推,手持"}}
    res = reference_analyzer.analyze([clip])
    assert res["semi_automatic"] and res["needs_human_confirm"]
    d = res["clips"][0]["descriptors"]
    # 关键词归一映射命中
    assert "暖色温倾向" in d["palette"]["values"]
    assert "青影调阴影" in d["palette"]["values"]
    assert "硬光高对比" in d["lighting"]["values"]
    assert "推轨向前" in d["camera"]["values"] and "手持微晃" in d["camera"]["values"]
    # 半自动：一律待确认
    assert all(not d[k]["confirmed"] for k in d)
    # 合并片段去重保序
    assert "暖色温倾向" in res["style_bible_fragment"]["palette"]


def test_reference_analyzer_generate_writes_md(project_dir, write_yaml):
    import reference_analyzer
    write_yaml(project_path(project_dir, "03_style", "reference_clips.yaml"),
               {"reference_clips": [{"title": "T", "annotations": {"pace": "慢"}}]})
    res = reference_analyzer.generate(project_dir)
    out = Path(res["out"])
    assert out.exists() and res["clip_count"] == 1
    md = out.read_text(encoding="utf-8")
    assert "需人工确认" in md and "慢节奏长镜" in md


def test_reference_analyzer_unannotated_placeholder():
    import reference_analyzer
    res = reference_analyzer.analyze([{"title": "空标注"}])
    d = res["clips"][0]["descriptors"]
    assert d["palette"]["values"] == []
    assert "未标注" in d["palette"]["text"]


# ============================ D-3 剪辑工程导出 ============================
def _setup_edl_project(project_dir, write_yaml, shotlist_doc):
    """铺设 shotlist + audio-manifest + 选定 take，供 edl_render 使用。"""
    import audio_manifest
    write_yaml(project_path(project_dir, "04_storyboard", "shotlist.yaml"), shotlist_doc)
    audio_manifest.generate(project_dir)
    for sid in ("SHOT-07", "SHOT-08"):
        write_yaml(project_path(project_dir, "06_generations", sid, "takes.yaml"),
                   {"shot_id": sid, "selected_take": f"{sid}-t01",
                    "takes": [{"take_id": f"{sid}-t01", "pass": "final", "channel": "ui",
                               "file": f"06_generations/{sid}/{sid}-t01.mp4"}]})
    return project_dir


def test_project_export_fcpxml_well_formed(project_dir, write_yaml, shotlist_doc):
    import project_export
    _setup_edl_project(project_dir, write_yaml, shotlist_doc)
    res = project_export.generate(project_dir)
    fx = Path(res["fcpxml_out"])
    assert fx.exists()
    # 良构 XML，根为 fcpxml
    root = ET.fromstring(fx.read_text(encoding="utf-8"))
    assert root.tag == "fcpxml"
    assert root.get("version") == "1.10"
    # 每镜一个 asset-clip
    clips = root.findall(".//spine/asset-clip")
    assert len(clips) == res["clip_count"] == 2
    # 媒体走 file:// 占位 src
    assert root.findall(".//asset/media-rep")[0].get("src").startswith("file://./")


def test_project_export_capcut_manifest_structure(project_dir, write_yaml, shotlist_doc):
    import project_export
    _setup_edl_project(project_dir, write_yaml, shotlist_doc)
    res = project_export.generate(project_dir)
    cc = json.loads(Path(res["capcut_out"]).read_text(encoding="utf-8"))
    assert cc["draft_type"] == "capcut_import_manifest"
    assert cc["semi_automatic"] and cc["needs_relink"]
    track_types = {t["type"] for t in cc["tracks"]}
    assert track_types == {"video", "text", "audio_ambience"}
    video = next(t for t in cc["tracks"] if t["type"] == "video")
    # 微秒时间轴累加 + 每段 needs_relink
    assert all(seg["needs_relink"] for seg in video["segments"])
    assert video["segments"][0]["target_timerange"]["start"] == 0


# ============================ D-6 资产索引深化 ============================
def test_asset_index_register_and_query(project_dir):
    import reuse_shots
    a1 = reuse_shots.register_asset(project_dir, kind="empty", tags=["沙暴", "黄昏"],
                                    source="ep-01/SHOT-03", file="a.mp4")
    reuse_shots.register_asset(project_dir, kind="transition", tags=["加油站"],
                               source="ep-01/SHOT-05", file="b.mp4", reuse_scope="series")
    assert a1["asset_id"] == "AST-001" and a1["hash"].startswith("sha-")
    # 标签交集打分
    q = reuse_shots.query_assets(project_dir, tags=["沙暴", "加油站"])
    assert q["total_matched"] == 2
    # kind 过滤
    qe = reuse_shots.query_assets(project_dir, tags=["沙暴"], kind="empty")
    assert qe["total_matched"] == 1 and qe["candidates"][0]["asset_id"] == "AST-001"
    # scope 过滤
    qs = reuse_shots.query_assets(project_dir, tags=["加油站"], scope="series")
    assert qs["total_matched"] == 1


def test_asset_index_hash_dedup(project_dir):
    import reuse_shots
    a1 = reuse_shots.register_asset(project_dir, kind="empty", tags=["x"],
                                    source="s", file="same.mp4")
    a2 = reuse_shots.register_asset(project_dir, kind="empty", tags=["x"],
                                    source="s2", file="same.mp4")
    # 同 file+tags → 同 hash → 去重返回原条目
    assert a1["asset_id"] == a2["asset_id"]
    assert len(reuse_shots.list_assets(project_dir)) == 1


def test_asset_index_rejects_bad_kind(project_dir):
    import reuse_shots
    try:
        reuse_shots.register_asset(project_dir, kind="nope", tags=["x"],
                                   source="s", file="f.mp4")
        assert False, "应拒绝非法 kind"
    except ValueError:
        pass


# ============================ Q-8 多平台发布自动化 ============================
def test_publish_automation_multi_platform(project_dir):
    import publish_automation
    proj = project_path(project_dir, "project.yaml")
    meta = read_yaml(proj)
    meta["target_platform"] = ["douyin", "bilibili"]
    proj.write_text(yaml.safe_dump(meta, allow_unicode=True), encoding="utf-8")

    res = publish_automation.generate(project_dir)
    assert res["platform_count"] == 2
    assert set(res["platforms"]) == {"douyin", "bilibili"}
    assert Path(res["checklist"]).exists() and Path(res["manifest"]).exists()
    auto = read_yaml(res["manifest"])
    # 半自动·不代发纪律
    assert auto["semi_automatic"] is True and auto["calls_platform_api"] is False
    assert all(e["publish_action"] == "manual" for e in auto["platforms"])
    # 主画幅按平台派生
    by_plat = {e["platform"]: e for e in auto["platforms"]}
    assert by_plat["douyin"]["primary_aspect"] == "9:16"
    assert by_plat["bilibili"]["primary_aspect"] == "16:9"
    # 一键清单含 G9 终确认勾选
    assert "G9" in Path(res["checklist"]).read_text(encoding="utf-8")


# ============================ Q-9 任务卡 UI 截图位 ============================
def test_taskcard_ui_screenshot_slots(tmp_path):
    import compile_genspec, make_taskcards
    shot = {"shot_id": "SHOT-07", "scene": "加油站", "characters": ["robo"],
            "shot_size": "中景", "composition": "右三分", "camera_move": "推轨",
            "action_logic": "停步", "control_level": "guided"}
    g = compile_genspec.compile_genspec(shot)
    res = make_taskcards.make_taskcards([g], tmp_path)
    api = next(c for c in res["cards"] if c["channel"] == "api")
    data = json.loads((tmp_path / api["file"]).read_text(encoding="utf-8"))
    slots = data["ui_screenshot_slots"]
    assert [s["slot"] for s in slots] == ["upload_done", "params_set", "result_preview"]
    # file 留空待回贴；annotations 预置空列表
    assert all(s["file"] is None for s in slots)
    assert data["annotations"] == []


def test_taskcard_ui_card_has_screenshot_section(tmp_path):
    import compile_genspec, make_taskcards
    shot = {"shot_id": "SHOT-08", "scene": "加油站", "characters": ["robo"],
            "shot_size": "近景", "composition": "中心", "camera_move": "固定",
            "action_logic": "回头", "control_level": "locked"}
    g = compile_genspec.compile_genspec(shot)
    res = make_taskcards.make_taskcards([g], tmp_path)
    ui = next((c for c in res["cards"] if c["channel"] == "ui"), None)
    if ui:
        md = (tmp_path / ui["file"]).read_text(encoding="utf-8")
        assert "执行截图位" in md and "media-manifest" in md


# ============================ Q-10 失败模式库深化 ============================
def test_failure_patterns_match_and_count():
    import qc_template
    fps = qc_template.load_failure_patterns()
    # 深化后至少 11 条
    assert len(fps) >= 11
    # 新增分类映射命中（透视异常→FP-002 运镜反向，音画不同步→FP-010 多模态打架）
    remedy, ref = qc_template._remedy_for("透视异常", fps)
    assert ref == "FP-002" and remedy
    remedy2, ref2 = qc_template._remedy_for("音画不同步", fps)
    assert ref2 == "FP-010"
    # 每条都带 rejected_reason / root_cause / remedy
    for p in fps.values():
        assert p.get("rejected_reason") and p.get("root_cause") and p.get("remedy")


def test_pattern_by_rejected_reason():
    import qc_template
    p = qc_template.pattern_by_rejected_reason("character_drift")
    assert p and p["id"] == "FP-001"
    assert qc_template.pattern_by_rejected_reason("不存在的reason") is None
    assert qc_template.pattern_by_rejected_reason("") is None


# ============================ Q-12 隐性成本统计 ============================
def test_cost_report_aggregates_hidden(project_dir):
    import ledger, cost_report
    # 直接生成费 + 隐性分项 + AI-QC + 人工工时
    ledger.append_event(project_dir, {"type": "take_cost", "shot_id": "SHOT-07", "cny": 10})
    ledger.append_event(project_dir, {"type": "hidden_cost", "category": "retry", "cny": 3})
    ledger.append_event(project_dir, {"type": "hidden_cost", "category": "upload", "cny": 1})
    ledger.append_event(project_dir, {"type": "ai_qc_cost", "cny": 2})
    ledger.append_event(project_dir, {"type": "human_minutes", "minutes": 30})

    rep = cost_report.build_report(project_dir, hourly_rate_cny=60.0)
    assert rep["direct_gen_cny"] == 10.0
    assert rep["hidden_costs"] == {"retry": 3.0, "upload": 1.0}
    assert rep["ai_qc_cny"] == 2.0
    # 30 分钟 @ 60/h = 30 cny
    assert rep["human_cny"] == 30.0
    # 隐性合计 = 4(分项) + 2(AI-QC) + 30(工时) = 36
    assert rep["hidden_grand_total_cny"] == 36.0
    assert rep["total_with_hidden_cny"] == 46.0


def test_cost_report_generate_writes_files(project_dir):
    import ledger, cost_report
    ledger.append_event(project_dir, {"type": "take_cost", "shot_id": "SHOT-07", "cny": 5})
    ledger.append_event(project_dir, {"type": "hidden_cost", "category": "bandwidth", "cny": 2})
    res = cost_report.generate(project_dir)
    assert Path(res["out"]).exists() and Path(res["md_out"]).exists()
    md = Path(res["md_out"]).read_text(encoding="utf-8")
    assert "隐性成本报告" in md and "带宽流量" in md


# ============================ D-7 观众反馈闭环 ============================
def test_feedback_aggregate():
    import feedback_intake
    fb = {"project_id": "p1", "items": [
        {"platform": "douyin", "sentiment": "positive", "category": "画质"},
        {"platform": "douyin", "sentiment": "negative", "category": "节奏"},
        {"platform": "bilibili", "sentiment": "negative", "category": "节奏"},
        {"platform": "bilibili", "sentiment": "neutral", "category": "剧情"},
    ]}
    agg = feedback_intake.aggregate(fb)
    assert agg["total"] == 4
    assert agg["by_sentiment"] == {"positive": 1, "negative": 2, "neutral": 1}
    assert agg["by_category"]["节奏"] == 2
    # 情感分 = (1-2)/4 = -0.25
    assert agg["sentiment_score"] == -0.25
    # 高频负面类别：节奏(2) 在前
    assert agg["top_negative_categories"][0] == "节奏"


def test_feedback_intake_writeback(project_dir, write_yaml, tmp_path):
    import feedback_intake
    write_yaml(project_path(project_dir, "09_publish", "audience-feedback.yaml"),
               {"project_id": "test-proj", "title": "测试项目",
                "items": [{"platform": "douyin", "sentiment": "positive", "category": "画质"}]})
    lessons = tmp_path / "cross-project-lessons.yaml"
    res = feedback_intake.writeback(project_dir, lessons_path=str(lessons))
    assert lessons.exists()
    book = read_yaml(lessons)
    lesson = next(l for l in book["lessons"]
                  if l.get("kind") == "audience_feedback")
    assert lesson["project_id"] == "test-proj"
    assert lesson["feedback_total"] == 1
    assert lesson["sentiment_score"] == 1.0
    # 反馈回写含 aggregate 段并过 C11 校验
    fb_out = read_yaml(Path(res["feedback_out"]))
    assert "aggregate" in fb_out


def test_feedback_c11_validates():
    from validate import validate_obj
    import feedback_intake
    fb = {"project_id": "p", "items": [
        {"platform": "douyin", "sentiment": "positive"}]}
    fb["aggregate"] = feedback_intake.aggregate(fb)
    validate_obj(fb, "C11")  # 不抛即通过
