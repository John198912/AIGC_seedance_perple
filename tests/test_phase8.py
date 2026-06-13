"""Phase 8 单测：逆向特征工程模块 M2（三级来源 + 对抗校验锚点硬规则 + G0 闸 + 词汇级 IP 预筛）。

覆盖：无锚点→封顶 inferred 且多轮不升档；sourced 需 ≥2 独立来源否则降级；origin:llm
不算锚点；research_orchestrator 零来源→unverifiable 且不伪造、行为域强制 inferred；
adversarial 内部一致性剪枝但不升档；ip_prescreen 命中词汇级、structural_check=defer_to_G0_human；
g0_gate 写出结构化记录且 events.jsonl 新增 G0 事件、单参考>3 被标记。
确定性、不触网；与既有测试并存不回归。
"""
from __future__ import annotations

import json
from pathlib import Path

import provenance as prov
import research_orchestrator as ro
import adversarial_check as adv
import ip_prescreen
import g0_gate
import ledger as _ledger


# ============================ provenance 三级来源 + 锚点硬规则 ============================
def test_no_anchor_floors_to_inferred():
    feat = {"provenance": "sourced", "source_refs": [
        {"source_domain": "blogA", "origin": "external"}]}  # 仅 1 独立来源
    assert prov.final_tier(feat) == "inferred"


def test_sourced_needs_two_independent():
    two = {"provenance": "inferred", "source_refs": [
        {"source_domain": "blogA"}, {"source_domain": "blogB"}]}
    assert prov.final_tier(two) == "sourced"
    # 两条但同 domain → 不算独立 → 降级 inferred
    same = {"provenance": "sourced", "source_refs": [
        {"source_domain": "blogA"}, {"source_domain": "blogA"}]}
    assert prov.final_tier(same) == "inferred"


def test_origin_llm_not_anchor():
    assert prov.is_valid_anchor({"source_domain": "x", "origin": "llm"}) is False
    assert prov.is_valid_anchor({"source_domain": "x", "origin": "self_baseline"}) is False
    assert prov.is_valid_anchor({"source_domain": "x", "origin": "external"}) is True
    # 两条 llm 来源不能凑成 sourced
    feat = {"provenance": "sourced", "source_refs": [
        {"source_domain": "a", "origin": "llm"}, {"source_domain": "b", "origin": "llm"}]}
    assert prov.final_tier(feat) == "inferred"


def test_first_party_is_observed():
    feat = {"source_refs": [{"origin": "first_party", "source_domain": "channel"}]}
    assert prov.final_tier(feat) == "observed"


def test_no_upgrade_helper():
    assert prov.is_upgrade("inferred", "sourced") is True
    assert prov.is_upgrade("sourced", "inferred") is False
    assert prov.is_upgrade("inferred", "inferred") is False


# ============================ research_orchestrator 防幻觉 ============================
def test_orchestrator_zero_source_unverifiable():
    inputs = {"content": [{"feature_axis": "hook_type", "value": "suspense_question",
                           "source_refs": []}]}
    res = ro.orchestrate(inputs)
    feat = res["routes"]["content"][0]
    assert feat["provenance"] == "inferred"
    assert feat["unverifiable"] is True
    # 绝不伪造 observed/sourced
    assert feat["provenance"] not in ("observed", "sourced")


def test_orchestrator_behavior_forced_inferred():
    # 行为域④即便有外部锚点也强制 inferred
    inputs = {"behavior": [{"feature_axis": "engagement_behavior", "value": "rewatch_loop",
                            "source_refs": [{"source_domain": "a"}, {"source_domain": "b"}],
                            "provenance": "sourced"}]}
    res = ro.orchestrate(inputs)
    feat = res["routes"]["behavior"][0]
    assert feat["provenance"] == "inferred"
    assert feat["forced_inferred"] is True
    assert feat["advisory"] is True


def test_orchestrator_each_feature_has_source_refs_field():
    res = ro.orchestrate({"content": [{"feature_axis": "pacing", "value": "fast_cut",
                                       "source_refs": []}]})
    for f in res["all_features"]:
        assert "source_refs" in f


def test_orchestrator_from_refs_mock():
    refs = [{"ref_id": "REF-1", "annotations": {"structural": {"hook_type": "shock_open"}}}]
    inputs = ro._mock_inputs_from_refs(refs)
    res = ro.orchestrate(inputs)
    assert res["mock"] is True
    # ①②④ 零来源条目产生 unverifiable
    assert res["unverifiable_count"] >= 1


# ============================ adversarial_check ============================
def test_adversarial_prunes_but_no_upgrade():
    # 无外部锚点、声明 sourced：多轮只剪枝、绝不升档
    feat = {"feature_axis": "view_scene", "value": "bedtime_fragment",
            "provenance": "sourced", "rationale": "猜测",
            "source_refs": []}
    r = adv.check_feature(feat, max_rounds=2)
    assert r["has_external_anchor"] is False
    assert r["pruned_only"] is True
    assert r["upgraded"] is False
    assert r["tier_after"] == "inferred"
    assert r["rounds"] <= 2


def test_adversarial_round_cap():
    feat = {"value": "x", "rationale": "r", "source_refs": []}
    r = adv.check_feature(feat, max_rounds=99)  # 请求超限仍封 2
    assert r["rounds"] <= adv.MAX_ROUNDS


def test_adversarial_keeps_objections():
    feat = {"value": "", "provenance": "observed", "source_refs": []}  # 缺 value+rationale
    r = adv.check_feature(feat)
    assert r["objections"]
    assert any("value" in o for o in r["objections"])
    assert r["upgraded"] is False


def test_adversarial_with_anchor_can_reach_sourced_not_upgrade_past():
    # 有 2 独立锚点：final_tier 给 sourced，但不应越过声明升到 observed
    feat = {"value": "v", "rationale": "r", "provenance": "inferred",
            "source_refs": [{"source_domain": "a"}, {"source_domain": "b"}]}
    r = adv.check_feature(feat)
    assert r["tier_after"] == "sourced"


# ============================ ip_prescreen 词汇级 + 诚实边界 ============================
def test_ip_prescreen_lexical_hit():
    res = ip_prescreen.prescreen("我们的主角钢铁侠登场，喊出奥利给")
    terms = {h["term"] for h in res["lexical_hit"]}
    assert "钢铁侠" in terms
    assert "奥利给" in terms
    assert res["ok"] is False


def test_ip_prescreen_structural_defers_to_g0():
    res = ip_prescreen.prescreen("一个普通的悬念开场")
    assert res["structural_check"] == "defer_to_G0_human"
    assert res["structural_check"] == ip_prescreen.DEFER_MARKER
    assert res["ok"] is True  # 无词汇命中


def test_ip_prescreen_param_keywords():
    kw = {"character_names": ["张三"], "catchphrases": [], "proper_nouns": []}
    res = ip_prescreen.prescreen("张三走过来", kw)
    assert any(h["term"] == "张三" for h in res["lexical_hit"])


def test_ip_prescreen_scans_nested_payload():
    payload = {"transferable_patterns": [{"directive": "首镜致敬蜘蛛侠"}]}
    res = ip_prescreen.prescreen(payload)
    assert any(h["term"] == "蜘蛛侠" for h in res["lexical_hit"])


# ============================ g0_gate ============================
def _dna(patterns=None, forbidden=None):
    return {
        "transferable_patterns": patterns if patterns is not None else [
            {"feature_axis": "hook_type", "value": "suspense_question",
             "maps_to": ["screenplay-writer"], "directive": "落 scenes[0].dialogue",
             "ip_layer": "structural", "specificity_ok": True,
             "source_refs": ["REF-1", "REF-2", "REF-3"]},
        ],
        "coherence": {"conflicts": [], "resolved": True},
        "forbidden": forbidden if forbidden is not None else [
            "具体角色名/形象", "具体台词/slogan", "具体分镜构图", "BGM 具体旋律"],
    }


def test_g0_gate_writes_record_and_event(tmp_path):
    project = tmp_path / "proj"
    review = g0_gate.run_gate(project, _dna(), target_platform="douyin")
    # 结构化记录字段
    assert review["gate"] == "G0"
    assert review["reviewer"] == "human_required"
    cl = review["checklist"]
    assert cl["legal_basis"] == "中国《著作权法》"
    assert cl["migrated_structure"]
    assert cl["untouched_expression"]
    assert cl["structural_check"] == "defer_to_G0_human"
    # 记录文件落盘
    assert Path(review["record_path"]).exists()
    # events.jsonl 新增 G0 事件
    events = _ledger.read_events(project)
    g0_events = [e for e in events if e.get("type") == "g0_review"]
    assert len(g0_events) == 1
    assert g0_events[0]["gate"] == "G0"
    assert g0_events[0]["decision"] == review["decision"]


def test_g0_gate_legal_domain_japan(tmp_path):
    review = g0_gate.run_gate(tmp_path / "p", _dna(), target_platform="tokyo")
    assert review["checklist"]["legal_basis"] == "日本法"


def test_g0_gate_per_ref_over_cap_flagged(tmp_path):
    # 单个参考贡献 4 个模式 > 3 → 标记违规并 block
    over = [{"feature_axis": f"ax{i}", "value": "v",
             "directive": "落 scenes[0]", "ip_layer": "structural",
             "specificity_ok": True, "source_refs": ["REF-X"]} for i in range(4)]
    review = g0_gate.run_gate(tmp_path / "p", _dna(patterns=over))
    cl = review["checklist"]
    assert cl["per_ref_cap_ok"] is False
    assert any(v["ref_id"] == "REF-X" and v["pattern_count"] == 4
               for v in cl["per_ref_violations"])
    assert review["decision"] == "block"


def test_g0_gate_lexical_hit_blocks(tmp_path):
    refs = [{"ref_id": "R", "title": "致敬哈利波特", "annotations": {}}]
    review = g0_gate.run_gate(tmp_path / "p", _dna(), references=refs)
    assert any(h["term"] == "哈利波特" for h in review["checklist"]["lexical_hit"])
    assert review["decision"] == "block"


def test_g0_event_idempotent_and_summary_intact(tmp_path):
    project = tmp_path / "p"
    g0_gate.run_gate(project, _dna())
    # summary 仍可重建且不因 g0_review 报错（不计费）
    summary = _ledger.get_summary(project)
    assert summary["total_cny"] == 0.0
    assert summary["event_count"] >= 1
