"""Phase 7 单测：逆向特征工程模块 M1（结构层逆向 + 反向映射 + 共享字典）。

覆盖：字典加载与轴元数据、C12/C13/C14 schema 校验通过、deconstruct 结构层
observed / ①②④ advisory、reverse_map 共性交集、coherence 命中冲突（快切+手持 vs
慢压抑）、机械具体性地板判废通用套话、inferred 永不门控、forbidden 存在。
确定性、不触网；与既有测试并存不回归。
"""
from __future__ import annotations

import pytest

import feature_dict as fd
import deconstruct
import reverse_map
from validate import validate_obj, ValidationError


# ============================ 字典加载与轴元数据 ============================
def test_dictionary_loads_and_axis_metadata():
    d = fd.load_dictionary()
    assert d["version"] == "0.1.0-seed"
    assert d.get("verified_at")
    hook = fd.get_axis("hook_type", d)
    assert hook["domain"] == "content"
    assert hook["gating"] is True
    assert hook["signal_kind"] == "leading"
    assert hook["information"] == "high"
    assert "screenplay-writer" in hook["maps_to"]
    assert "suspense_question" in hook["values"]
    # 五条结构层轴齐备
    for axis in ("hook_type", "emotion_curve_shape", "pacing",
                 "narrative_structure", "shot_grammar"):
        assert fd.is_gating(axis, d) is True


def test_advisory_axes_never_gating():
    d = fd.load_dictionary()
    for axis in ("target_audience", "view_scene", "engagement_behavior"):
        meta = fd.get_axis(axis, d)
        assert meta["gating"] is False
        assert meta["domain"] in {"audience", "scene", "behavior"}


def test_axis_value_valid():
    d = fd.load_dictionary()
    assert fd.axis_value_valid("pacing", "fast_cut", d)
    assert not fd.axis_value_valid("pacing", "no_such_value", d)


# ============================ C12/C13/C14 schema 校验 ============================
def _c12(ref_id="REF-1", title="样片1", structural=None, audience=None):
    structural = structural if structural is not None else {
        "hook_type": "suspense_question",
        "emotion_curve_shape": "low_start_midrise",
        "shot_grammar": "fast_cut_handheld",
    }
    ann = {"visual": {"palette": "低饱和暖黄", "camera": "推,手持"},
           "structural": structural}
    if audience:
        ann["structural"] = {**structural, **audience}
    return {"ref_id": ref_id, "title": title, "source": "影片X（仅文本）",
            "annotations": ann, "ip_note": "致敬向，注意发布端风险"}


def test_c12_schema_valid():
    validate_obj(_c12(), "C12")
    validate_obj(_c12(), "reference_work")  # 别名


def test_c13_schema_valid():
    ts = deconstruct.deconstruct_one(_c12())
    validate_obj(ts, "C13")
    validate_obj(ts, "featuretagset")


def test_c14_schema_valid():
    tagsets = [deconstruct.deconstruct_one(_c12(ref_id=f"REF-{i}")) for i in range(3)]
    dna = reverse_map.reverse_map(tagsets)
    validate_obj(dna, "C14")
    validate_obj(dna, "creativedna")


def test_c13_schema_rejects_bad_provenance():
    bad = {"ref_id": "R", "features": [{
        "feature_axis": "hook_type", "value": "suspense_question",
        "domain": "content", "provenance": "guessed", "confidence_tier": "high"}]}
    with pytest.raises(ValidationError):
        validate_obj(bad, "C13")


# ============================ deconstruct 结构层 observed / ①②④ advisory ============================
def test_deconstruct_structural_observed():
    ts = deconstruct.deconstruct_one(_c12())
    content = [f for f in ts["features"] if f["domain"] == "content"]
    assert content, "应有结构层承重特征"
    for f in content:
        assert f["provenance"] == "observed"
        assert f["confidence_tier"] == "high"
        assert f["advisory"] is False


def test_deconstruct_advisory_124():
    ref = _c12(audience={"target_audience": "young_male_18_24",
                         "view_scene": "bedtime_fragment"})
    ts = deconstruct.deconstruct_one(ref)
    adv = [f for f in ts["features"] if f["domain"] in {"audience", "scene", "behavior"}]
    assert adv, "应有 ①②④ 顾问特征"
    for f in adv:
        assert f["advisory"] is True
        assert f["provenance"] == "inferred"  # 无外部锚点封顶 inferred


def test_deconstruct_rejects_out_of_dict_value():
    ref = _c12(structural={"hook_type": "nonexistent_value"})
    ts = deconstruct.deconstruct_one(ref)
    assert not any(f["feature_axis"] == "hook_type" for f in ts["features"])


# ============================ reverse_map 共性交集 ============================
def test_reverse_map_common_intersection():
    common = {"hook_type": "suspense_question",
              "narrative_structure": "three_act",
              "shot_grammar": "slow_dolly"}
    tagsets = [deconstruct.deconstruct_one(_c12(ref_id=f"REF-{i}", structural=common))
               for i in range(3)]
    dna = reverse_map.reverse_map(tagsets)
    axes = {p["feature_axis"] for p in dna["transferable_patterns"]}
    assert "hook_type" in axes and "narrative_structure" in axes
    assert dna["source_ref_ids"] == ["REF-0", "REF-1", "REF-2"]


def test_reverse_map_requires_min_refs():
    tagsets = [deconstruct.deconstruct_one(_c12(ref_id="REF-1"))]
    with pytest.raises(ValueError):
        reverse_map.reverse_map(tagsets)


def test_reverse_map_per_ref_cap():
    # 单参考贡献模式数硬上限 ≤3：给 4 个结构轴，只取 3 个
    structural = {"hook_type": "suspense_question",
                  "emotion_curve_shape": "low_start_midrise",
                  "pacing": "slow_long_take",
                  "narrative_structure": "three_act"}
    tagsets = [deconstruct.deconstruct_one(_c12(ref_id=f"REF-{i}", structural=structural))
               for i in range(3)]
    dna = reverse_map.reverse_map(tagsets)
    content_axes = [p for p in dna["transferable_patterns"] if not p["advisory"]]
    assert len(content_axes) <= 3


# ============================ coherence 命中冲突 ============================
def test_coherence_hits_conflict():
    # 快切+手持 与 低起压抑慢节奏 = conflict
    structural = {"shot_grammar": "fast_cut_handheld",
                  "emotion_curve_shape": "flat_low"}
    tagsets = [deconstruct.deconstruct_one(_c12(ref_id=f"REF-{i}", structural=structural))
               for i in range(3)]
    dna = reverse_map.reverse_map(tagsets)
    conflicts = dna["coherence"]["conflicts"]
    assert any(c["relation"] == "conflict" for c in conflicts)
    assert dna["coherence"]["resolved"] is False


def test_check_coherence_direct():
    hits = fd.check_coherence([("shot_grammar", "fast_cut_handheld"),
                               ("emotion_curve_shape", "flat_low")])
    assert any(h["relation"] == "conflict" for h in hits)
    # 无冲突组合
    assert fd.check_coherence([("hook_type", "suspense_question")]) == []


# ============================ 机械具体性地板判废通用套话 ============================
def test_specificity_floor_rejects_vague():
    assert reverse_map._has_specificity(
        "screenplay-writer：落 scenes[0].dialogue 字段。") is True
    assert reverse_map._has_specificity("要有吸引人的开头") is False
    assert reverse_map._has_specificity("更好更精彩") is False


def test_specificity_floor_filters_patterns():
    # 字典外无模板的轴会产生无具体 token 的 directive → 判废
    # 用真实结构轴确保留存的都具体
    structural = {"hook_type": "suspense_question",
                  "shot_grammar": "slow_dolly"}
    tagsets = [deconstruct.deconstruct_one(_c12(ref_id=f"REF-{i}", structural=structural))
               for i in range(3)]
    dna = reverse_map.reverse_map(tagsets)
    assert all(p["specificity_ok"] for p in dna["transferable_patterns"])


# ============================ inferred 永不门控 ============================
def test_inferred_never_gating():
    tagsets = [deconstruct.deconstruct_one(
        _c12(ref_id=f"REF-{i}", audience={"target_audience": "young_male_18_24"}))
        for i in range(3)]
    dna = reverse_map.reverse_map(tagsets)
    adv = [p for p in dna["transferable_patterns"]
           if p["feature_axis"] == "target_audience"]
    assert adv, "①②④ 应出现在 C14 顾问模式中"
    for p in adv:
        assert p["advisory"] is True
        assert p["provenance"] == "inferred"


# ============================ forbidden 存在 ============================
def test_forbidden_present():
    tagsets = [deconstruct.deconstruct_one(_c12(ref_id=f"REF-{i}")) for i in range(3)]
    dna = reverse_map.reverse_map(tagsets)
    assert dna["forbidden"], "C14 必须含 forbidden 禁迁项"
    joined = "".join(dna["forbidden"])
    assert "台词" in joined and "BGM" in joined
