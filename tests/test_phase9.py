"""Phase 9 单测：逆向特征工程模块 M3（deconstruct_cost_cap 第四道闸 + 治理产物陈旧度
校验 + concept-brief 对标驱动顾问路径）。

纪律核验：
- 第四道闸纯增量——无 cap / 零成本时 allowed 与旧路径一致（回归保护）；
  设 cap 且累计 deconstruct 超限 → block 且 allowed=False；
  ledger 聚合出 deconstruct_costs 且既有 take/ai_qc/hidden 字段不变。
- 既有三闸（per_shot / ai_qc）改造前后行为一致。
- verify_capabilities governance：include_governance=False 结构/ok 与旧一致；
  True 时陈旧 lib 进 stale、新鲜的不进、缺 verified_at 记 missing。
- concept_advisory：无锚点 audience 建议 inferred 且 advisory/不门控；≥2 独立锚点
  audience → sourced 但仍 advisory（gating=false）；行为④即便有锚点仍 advisory；
  merge_into_brief 不动原 brief 字段、只加 advisory_block。
确定性、不触网；与既有测试并存不回归。
"""
from __future__ import annotations

import datetime as _dt

import budget_guard
import ledger
import verify_capabilities as vc
import concept_advisory as ca
from _common import read_yaml, write_yaml, project_path


def _set_budget_field(project, key, value):
    """测试辅助：往 project.yaml 的 budget 写入一个字段（增量改）。"""
    proj = read_yaml(project_path(project, "project.yaml"))
    proj.setdefault("budget", {})[key] = value
    write_yaml(project_path(project, "project.yaml"), proj)


# ============================ deconstruct_cost 第四道闸 ============================
def test_deconstruct_no_cap_matches_old_path(project_dir):
    # 无 deconstruct_cost_cap 字段、零成本 → 行为与旧路径一致（放行、无 block）。
    res = budget_guard.check_batch(project_dir, batch_cost_cny=10)
    assert res["allowed"] is True
    assert res["blocks"] == []
    # 新返回键存在但不影响放行
    assert res["deconstruct_projected"] == 0.0


def test_deconstruct_zero_cost_with_cap_no_block(project_dir):
    # 设了 cap 但本批 deconstruct=0 且无历史 → projected 0 ≤ cap → 不拦。
    _set_budget_field(project_dir, "deconstruct_cost_cap_cny", 100)
    res = budget_guard.check_batch(project_dir, batch_cost_cny=10)
    assert res["allowed"] is True
    assert not any("deconstruct" in b for b in res["blocks"])


def test_deconstruct_cap_blocks_when_exceeded(project_dir):
    _set_budget_field(project_dir, "deconstruct_cost_cap_cny", 50)
    # 历史已记 40 元逆向成本，再来一批 20 → 共 60 > 50 → 拦截。
    ledger.append_event(project_dir, {"type": "deconstruct_cost", "cny": 40.0,
                                      "event_id": "dc-1"})
    res = budget_guard.check_batch(project_dir, deconstruct_cost_cny=20)
    assert res["allowed"] is False
    assert res["deconstruct_projected"] == 60.0
    assert any("deconstruct_cost_cap" in b for b in res["blocks"])


def test_ledger_aggregates_deconstruct_costs_others_intact(project_dir):
    # deconstruct_cost 单列且进 total_cny；既有 take/ai_qc/hidden 字段语义不变。
    ledger.append_event(project_dir, {"type": "take_cost", "shot_id": "S1",
                                      "cny": 10.0, "event_id": "t"})
    ledger.append_event(project_dir, {"type": "ai_qc_cost", "cny": 2.0, "event_id": "q"})
    ledger.append_event(project_dir, {"type": "hidden_cost", "category": "sub",
                                      "cny": 5.0, "event_id": "h"})
    ledger.append_event(project_dir, {"type": "deconstruct_cost", "cny": 7.0,
                                      "event_id": "d"})
    s = ledger.get_summary(project_dir)
    assert s["deconstruct_costs"] == 7.0
    # 既有字段不被破坏
    assert s["ai_qc_costs"] == 2.0
    assert s["hidden_costs"]["sub"] == 5.0
    assert s["by_shot"]["S1"]["cny"] == 10.0
    # deconstruct 计入 total（参照 ai_qc）：10 + 2 + 5 + 7 = 24
    assert s["total_cny"] == 24.0


def test_ledger_deconstruct_absent_field_zero(project_dir):
    # 未记任何 deconstruct 事件时，新字段缺省为 0.0，旧聚合不变。
    ledger.append_event(project_dir, {"type": "take_cost", "cny": 3.0, "event_id": "x"})
    s = ledger.get_summary(project_dir)
    assert s["deconstruct_costs"] == 0.0
    assert s["total_cny"] == 3.0


# ============================ 既有三闸不受第四道闸影响（回归保护）============================
def test_existing_per_shot_gate_unchanged(project_dir):
    # 只触发单镜闸的场景：deconstruct 改造后行为与旧一致。
    res = budget_guard.check_batch(project_dir, shot_id="SHOT-07",
                                   batch_cost_cny=100,
                                   genspec={"per_shot_cost_cap_cny": 50})
    assert res["allowed"] is False
    assert res["effective_per_shot_cap"] == 50
    assert any("超上限" in b for b in res["blocks"])
    # 第四道闸未触发
    assert not any("deconstruct" in b for b in res["blocks"])


def test_existing_ai_qc_gate_unchanged(project_dir):
    res = budget_guard.check_batch(project_dir, qc_cost_cny=250)
    assert res["allowed"] is False
    assert any("ai_qc_cost_cap" in b for b in res["blocks"])
    assert not any("deconstruct" in b for b in res["blocks"])


# ============================ verify_capabilities 治理陈旧度 ============================
def test_governance_excluded_by_default(project_dir):
    # include_governance 默认 False → 结果无 governance 键、ok 仅由旧两项决定。
    res = vc.verify(now=_dt.date(2026, 6, 13))
    assert "governance" not in res
    assert set(res.keys()) == {"now", "expiry", "heartbeat", "ok"}


def test_governance_fresh_when_within_window():
    # 治理 lib verified_at=2026-06-13；基准同日 → 不陈旧。
    gov = vc.check_governance_freshness(now=_dt.date(2026, 6, 13))
    assert gov["ok"] is True
    assert gov["stale"] == []
    # feature-dictionary 额外暴露 version
    fd = next(i for i in gov["items"] if i["name"] == "feature-dictionary.yaml")
    assert "version" in fd


def test_governance_stale_beyond_window():
    # 基准远超 30 天 → 全部陈旧进 stale。
    gov = vc.check_governance_freshness(now=_dt.date(2026, 12, 1))
    assert gov["ok"] is False
    assert len(gov["stale"]) >= 1
    assert "feature-dictionary.yaml" in gov["stale"]


def test_governance_reverify_days_override():
    gov = vc.check_governance_freshness(now=_dt.date(2026, 12, 1), reverify_days=365)
    assert gov["ok"] is True


def test_verify_with_governance_merges_and_affects_ok():
    # include_governance=True 且陈旧 → governance 进结果且拉低 ok。
    res = vc.verify(now=_dt.date(2026, 12, 1), include_governance=True)
    assert "governance" in res
    assert res["governance"]["ok"] is False
    assert res["ok"] is False


# ============================ concept_advisory 对标驱动顾问 ============================
def _audience_feat(refs):
    return {"feature_axis": "target_audience", "value": "Z世代夜猫子",
            "provenance": "inferred", "source_refs": refs, "rationale": "对标推断"}


def test_advisory_no_anchor_audience_inferred_not_gated():
    dna = {"transferable_patterns": [_audience_feat([])]}
    adv = ca.build_advisory(dna)
    assert adv["count"] == 1
    s = adv["advisory_suggestions"][0]
    assert s["domain"] == "audience"
    assert s["provenance"] == "inferred"   # 无锚点封顶 inferred
    assert s["advisory"] is True
    assert s["gating"] is False            # 永不门控
    assert s["overridable"] is True


def test_advisory_two_anchors_audience_sourced_still_advisory():
    feat = _audience_feat([{"source_domain": "a"}, {"source_domain": "b"}])
    adv = ca.build_advisory({"transferable_patterns": [feat]})
    s = adv["advisory_suggestions"][0]
    assert s["provenance"] == "sourced"    # ≥2 独立锚点 → sourced
    assert s["advisory"] is True           # 仍为顾问
    assert s["gating"] is False            # 仍不门控


def test_advisory_behavior_stays_advisory_even_with_anchors():
    # 行为域④即便有 2 独立锚点也维持 advisory、不门控；
    # 并承接 M2「行为信号不可由解构直接观测」纪律：强制封顶 inferred，
    # 绝不因 source_refs 被 final_tier 升回 sourced。
    feat = {"feature_axis": "engagement_behavior", "value": "rewatch_loop",
            "provenance": "sourced",
            "source_refs": [{"source_domain": "a"}, {"source_domain": "b"}]}
    adv = ca.build_advisory({"transferable_patterns": [feat]})
    s = adv["advisory_suggestions"][0]
    assert s["domain"] == "behavior"
    assert s["advisory"] is True
    assert s["gating"] is False
    assert s["provenance"] == "inferred"   # 带双锚点也强制 inferred
    assert s.get("forced_inferred") is True


def test_advisory_skips_structural_content_axis():
    # 结构层③（content）轴不进顾问路径。
    feat = {"feature_axis": "hook_type", "value": "suspense", "domain": "content",
            "source_refs": []}
    adv = ca.build_advisory({"transferable_patterns": [feat]})
    assert adv["count"] == 0


def test_advisory_note_present():
    adv = ca.build_advisory({"transferable_patterns": [_audience_feat([])]})
    assert adv["note"] == "对标驱动顾问建议，永不门控，创作者可覆盖"


def test_merge_into_brief_preserves_original_fields():
    brief = {"logline": "一句话", "worldview": "末世", "style": "赛博"}
    adv = ca.build_advisory({"transferable_patterns": [_audience_feat([])]})
    merged = ca.merge_into_brief(brief, adv)
    # 原字段一律不动
    assert merged["logline"] == "一句话"
    assert merged["worldview"] == "末世"
    assert merged["style"] == "赛博"
    # 只新增 advisory_block
    assert merged["advisory_block"] == adv
    # 不就地修改原 brief
    assert "advisory_block" not in brief


def test_advisory_reads_reverse_map_bucketed_domains():
    # reverse_map 按域分桶也能被收集。
    rm = {"scene": [{"feature_axis": "view_scene", "value": "睡前碎片",
                     "source_refs": []}]}
    adv = ca.build_advisory({}, rm)
    assert adv["count"] == 1
    assert adv["advisory_suggestions"][0]["domain"] == "scene"
