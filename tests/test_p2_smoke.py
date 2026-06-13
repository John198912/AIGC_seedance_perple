"""P2 骨架 smoke 测试：每个 P2 脚本至少跑通核心函数一次。"""
from __future__ import annotations

from _common import read_yaml, project_path


# ---------- backup.py (SK0) ----------
def test_backup_manifest(project_dir, write_yaml):
    import backup
    write_yaml(project_dir / "01_brief" / "brief.md", "x")  # 制造一个被扫文件
    m = backup.build_manifest(project_dir)
    assert m["asset_count"] >= 1
    assert all("sha256" in a and len(a["sha256"]) == 64 for a in m["assets"])
    res = backup.backup(project_dir)
    assert (project_dir / "ledger" / "backup-manifest.yaml").exists()
    assert res["asset_count"] == m["asset_count"]


# ---------- shotlist_stats.py (SK4) ----------
def test_shotlist_stats(shotlist_doc):
    import shotlist_stats
    rep = shotlist_stats.analyze(shotlist_doc)
    assert rep["shot_count"] == 2
    assert rep["total_duration_s"] > 0
    assert "lint" in rep


def test_shotlist_stats_lint_over_duration():
    import shotlist_stats
    sl = {"shots": [{"shot_id": "SHOT-01", "order": 1, "duration_s": 30,
                     "shot_size": "全景", "control_level": "guided"}]}
    rep = shotlist_stats.analyze(sl)
    assert rep["ok"] is False
    assert any("超" in w for w in rep["lint"])


# ---------- emotion_curve.py (SK2) ----------
def test_emotion_curve_flat_detected():
    import emotion_curve
    sp = {"scenes": [{"scene_id": f"SC-{i}", "emotion_value": 5} for i in range(4)]}
    res = emotion_curve.build_curve(sp)
    assert res["ok"] is False           # 连续 4 场平值 → 命中告警
    assert res["flat_segments"]


def test_emotion_curve_varied_ok():
    import emotion_curve
    sp = {"scenes": [{"scene_id": "a", "emotion_value": 2},
                     {"scene_id": "b", "emotion_value": 6},
                     {"scene_id": "c", "emotion_value": 3}]}
    res = emotion_curve.build_curve(sp)
    assert res["ok"] is True


# ---------- register_check.py (SK3) ----------
def _good_card():
    return {
        "id": "robo", "name": "锈牛仔",
        "feature_card": {"appearance": "锈迹斑斑的机械牛仔"},
        "identity_strategy": {
            "prompt_lock_zh": "锈牛仔", "prompt_lock_en": "rusty cowboy",
            "negative_zh": "光滑", "negative_en": "shiny",
        },
    }


def test_register_check_ok():
    import register_check
    res = register_check.check_card(_good_card())
    assert res["ok"] is True
    assert res["errors"] == []


def test_register_check_human_face_warns():
    import register_check
    card = _good_card()
    card["compliance"] = {"human_face": True}
    res = register_check.check_card(card)
    assert res["ok"] is True              # 仅告警不报错
    assert any("human_face" in w for w in res["warnings"])


def test_register_check_missing_identity_field():
    import register_check
    card = _good_card()
    del card["identity_strategy"]["negative_en"]
    res = register_check.check_card(card)
    assert res["ok"] is False


# ---------- qc_template.py (SK7) ----------
def test_qc_template_build(project_dir, write_yaml, shotlist_doc):
    import qc_template
    write_yaml(project_path(project_dir, "04_storyboard", "shotlist.yaml"), shotlist_doc)
    rep = qc_template.build_report(project_dir)
    assert rep["verdict"] == "needs_fix"
    assert len(rep["issues"]) == 2 * 6   # 2 镜 × 6 检查类别
    res = qc_template.generate(project_dir)
    assert (project_dir / "08_edit" / "qc-report.yaml").exists()
    assert res["issue_count"] == len(rep["issues"])


# ---------- audio_manifest.py (SK8) ----------
def test_audio_manifest(project_dir, write_yaml, shotlist_doc):
    import audio_manifest
    write_yaml(project_path(project_dir, "04_storyboard", "shotlist.yaml"), shotlist_doc)
    # 一张带 voice_ref 的角色卡
    write_yaml(project_path(project_dir, "03_characters", "robo", "card.yaml"),
               {"id": "robo", "voice_ref": "voices/robo.wav"})
    m = audio_manifest.build_manifest(project_dir)
    assert len(m["timeline"]) == 2
    assert m["timeline"][0]["start_s"] == 0.0
    assert m["voice_bind"]["robo"] == "voices/robo.wav"
    # ambience_group 相同的相邻镜头标桥接
    assert any(e["bridge_prev"] for e in m["timeline"])


# ---------- edl_render.py (SK9) ----------
def test_edl_render(project_dir, write_yaml, shotlist_doc):
    import edl_render
    write_yaml(project_path(project_dir, "04_storyboard", "shotlist.yaml"), shotlist_doc)
    edl = edl_render.build_edl(project_dir)
    assert edl["clips"][0]["in_tc"] == "00:00"
    assert edl["clips"][0]["take"] == "<未选>"   # 未选片
    md = edl_render.render_md(edl)
    assert "EDL" in md
    res = edl_render.generate(project_dir)
    assert (project_dir / "08_edit" / "edl.md").exists()
    assert res["clip_count"] == 2


# ---------- render_variants.py (SK10) ----------
def test_render_variants_plan():
    import render_variants
    plan = render_variants.plan_variants("16:9", ["9:16", "1:1"])
    assert plan["source_aspect"] == "16:9"
    aspects = {v["aspect"] for v in plan["variants"]}
    assert aspects == {"9:16", "1:1"}
    portrait = next(v for v in plan["variants"] if v["aspect"] == "9:16")
    assert portrait["width"] == 1080 and portrait["height"] == 1920


def test_render_variants_unknown_aspect():
    import render_variants
    plan = render_variants.plan_variants("16:9", ["7:3"])
    assert plan["variants"][0]["error"]


# ---------- cover_extractor.py (SK10) ----------
def test_cover_extractor(project_dir, write_yaml, shotlist_doc):
    import cover_extractor
    write_yaml(project_path(project_dir, "04_storyboard", "shotlist.yaml"), shotlist_doc)
    res = cover_extractor.extract(project_dir, top=2)
    assert res["top"] == 2
    assert len(res["candidates"]) == 2
    # locked 的镜头（SHOT-08）得分应更高，排前
    assert res["candidates"][0]["score"] >= res["candidates"][1]["score"]


# ---------- capability_query.py (SK11) ----------
def test_capability_query_supported():
    import json
    import capability_query
    res = capability_query.query(model="seedance-2.0", images=9, videos=3,
                                 audios=0, resolution="1080p", channel="falai")
    assert res["supported"] is True
    assert res["verified_at"] is not None
    # verified_at 须可 JSON 序列化（来自 YAML 的 date 不可直接 dumps）
    json.dumps(res, ensure_ascii=False)


def test_capability_query_over_total():
    import capability_query
    # 9+3+3 = 15 > total_files 12 → 不支持 + 降级建议
    res = capability_query.query(model="seedance-2.0", images=9, videos=3, audios=3)
    assert res["supported"] is False
    assert res["fallbacks"]


def test_capability_query_bad_resolution():
    import capability_query
    res = capability_query.query(model="seedance-2.0", resolution="4k", channel="falai")
    assert res["supported"] is False
    assert any("分辨率" in i for i in res["issues"])
