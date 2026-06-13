"""Phase 10 单测：逆向特征工程模块 M4（数据闭环层）。

四条核心纪律核验：
- 幸存者偏差硬规则：run_backtest 收到 abs_threshold → raise；只桶内相对比较（构造
  跨桶数据，断言不混桶）；pooled_effect 正确。
- C15 = 第一方实绩锚点：C15 schema 校验通过 + validate 别名 C15→channelperf；
  ingest CSV 强制 source=first_party；bucket_incomplete 行被排除；as_anchor 经
  provenance.final_tier → observed；C15 可选、永不门控。
- 贝叶斯非频率派：双门槛（区间下界 > min_effect 才采纳）；无 prior=无信息先验；
  confidence_band 为定性档；显式损失函数推荐动作。
- 日落/休眠：结构层轴证据不足 → hibernate（非 retire）；①②④可 retire；leading TTL
  比 lagging 短（衰减更快 / 更早 stale）。

另含：轴发现只提案不写字典；版本化字典轴集合冻结（minor 内增删轴 raise）。
确定性、不触网；与既有测试并存不回归。
"""
from __future__ import annotations

import csv as _csv

import pytest

import channel_perf
import backtest
import bayes_criterion as bayes
import axis_discovery
import dict_versioning as dv
import evidence_budget as eb
import provenance
import validate


# ============================ 纪律2：C15 schema + 摄入 + 锚点 ============================
def _min_c15():
    return {
        "project_id": "p1",
        "channel": "douyin",
        "axis_level_metrics": {"completion_rate": 0.4},
        "bucket": {"account": "acc1", "time_bucket": "2026W10", "topic_bucket": "美食"},
        "source": "first_party",
        "collected_at": "2026-03-01",
    }


def test_c15_schema_validates_and_alias_resolves():
    # 别名 C15 → channelperf；最小合法对象校验通过。
    assert validate.resolve_contract("C15") == "C15"
    assert validate.resolve_contract("channelperf") == "C15"
    validate.validate_obj(_min_c15(), "C15")  # 不抛即通过


def test_c15_schema_rejects_non_first_party_source():
    bad = _min_c15()
    bad["source"] = "third_party"
    from validate import ValidationError
    with pytest.raises(ValidationError):
        validate.validate_obj(bad, "C15")


def test_ingest_csv_forces_first_party(tmp_path):
    path = tmp_path / "perf.csv"
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = _csv.DictWriter(fh, fieldnames=[
            "project_id", "channel", "account", "time_bucket", "topic_bucket",
            "completion_rate", "interaction_rate", "source", "collected_at"])
        w.writeheader()
        # 即便 CSV 标了第三方，也强制 first_party
        w.writerow({"project_id": "p1", "channel": "douyin", "account": "a1",
                    "time_bucket": "2026W10", "topic_bucket": "美食",
                    "completion_rate": "0.5", "interaction_rate": "0.1",
                    "source": "third_party", "collected_at": "2026-03-01"})
    rows = channel_perf.ingest_csv(str(path))
    assert len(rows) == 1
    assert rows[0]["source"] == "first_party"
    assert rows[0]["axis_level_metrics"]["completion_rate"] == 0.5


def test_ingest_csv_marks_bucket_incomplete(tmp_path):
    path = tmp_path / "perf.csv"
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = _csv.DictWriter(fh, fieldnames=[
            "project_id", "channel", "account", "time_bucket", "topic_bucket",
            "completion_rate"])
        w.writeheader()
        # 缺 topic_bucket → bucket_incomplete
        w.writerow({"project_id": "p1", "channel": "douyin", "account": "a1",
                    "time_bucket": "2026W10", "topic_bucket": "",
                    "completion_rate": "0.5"})
    rows = channel_perf.ingest_csv(str(path))
    assert rows[0]["bucket_incomplete"] is True


def test_as_anchor_yields_observed_via_provenance():
    anchor = channel_perf.as_anchor(_min_c15())
    assert anchor["origin"] == "first_party"
    feature = {"provenance": "inferred", "source_refs": [anchor]}
    # 第一方锚点 → final_tier observed（复用 M2 provenance，未改其行为）
    assert provenance.final_tier(feature) == "observed"


# ============================ 纪律1：幸存者偏差 / 分层控混淆回测 ============================
def _c15_row(account, topic, treat_value, completion):
    return {
        "project_id": "p1", "channel": "douyin", "source": "first_party",
        "bucket": {"account": account, "time_bucket": "2026W10", "topic_bucket": topic},
        "axes": {"hook_type": treat_value},
        "axis_level_metrics": {"completion_rate": completion},
    }


def test_run_backtest_rejects_abs_threshold():
    rows = [_c15_row("a1", "美食", "shock_open", 0.5)]
    with pytest.raises(ValueError):
        backtest.run_backtest(rows, "hook_type", "shock_open", "completion_rate",
                              abs_threshold=0.3)


def test_backtest_within_bucket_only_no_cross_mixing():
    # 桶A：treatment 高（0.6）vs control 低（0.4）→ 桶内 +0.2
    # 桶B：treatment 0.3 vs control 0.2 → 桶内 +0.1
    # 若错误地跨桶混合，control 均值会被另一桶污染，pooled 不会等于 (0.2+0.1)/2=0.15
    rows = [
        _c15_row("a1", "美食", "shock_open", 0.6),
        _c15_row("a1", "美食", "plain", 0.4),
        _c15_row("a2", "科技", "shock_open", 0.3),
        _c15_row("a2", "科技", "plain", 0.2),
    ]
    res = backtest.run_backtest(rows, "hook_type", "shock_open", "completion_rate")
    assert res["buckets_used"] == 2
    assert res["pooled_effect"] == pytest.approx(0.15)
    # 每桶相对差独立、不混桶
    diffs = sorted(b["abs_diff"] for b in res["per_bucket"] if b["abs_diff"] is not None)
    assert diffs == pytest.approx([0.1, 0.2])


def test_backtest_drops_bucket_incomplete():
    rows = [
        _c15_row("a1", "美食", "shock_open", 0.6),
        _c15_row("a1", "美食", "plain", 0.4),
        {"project_id": "p1", "channel": "douyin", "source": "first_party",
         "bucket_incomplete": True, "axes": {"hook_type": "shock_open"},
         "axis_level_metrics": {"completion_rate": 0.99}},
    ]
    res = backtest.run_backtest(rows, "hook_type", "shock_open", "completion_rate")
    assert res["buckets_used"] == 1
    assert res["pooled_effect"] == pytest.approx(0.2)


# ============================ 纪律3：贝叶斯判据 ============================
def test_bayes_uninformative_prior_when_none():
    post = bayes.posterior([0.1, 0.12, 0.11])
    assert post["prior_used"] is False
    assert post["post_mean"] == pytest.approx(0.11, abs=0.01)


def test_bayes_double_threshold_adopt():
    # 一致的正向大效应 → 区间下界应 > min_effect → 采纳
    res = bayes.evaluate([0.2, 0.21, 0.19, 0.2], min_effect=0.02)
    assert res["adopt_gate_passed"] is True
    assert res["decision"] == "candidate_adopt"
    assert res["confidence_band"] in bayes.CONFIDENCE_BANDS


def test_bayes_double_threshold_insufficient_when_interval_straddles():
    # 效应跨零、方差大 → 区间下界不过门槛 → 证据不足维持
    res = bayes.evaluate([0.3, -0.3, 0.05, -0.1], min_effect=0.02)
    assert res["adopt_gate_passed"] is False
    assert res["decision"] in ("insufficient_hold", "candidate_retire")


def test_bayes_confidence_band_is_qualitative():
    res = bayes.evaluate([0.2, 0.21, 0.19], min_effect=0.02)
    assert isinstance(res["confidence_band"], str)
    assert res["confidence_band"] in bayes.CONFIDENCE_BANDS


def test_bayes_loss_function_recommends_action():
    res = bayes.evaluate([0.2, 0.21, 0.19], min_effect=0.02)
    assert res["recommended_action"] in ("adopt", "retire", "hold")
    assert "expected_loss_adopt" in res and "expected_loss_retire" in res


# ============================ 轴发现：只提案不写字典 ============================
def _dict_with_axes(*names):
    return {"version": "0.1.0-seed", "axes": {n: {"domain": "content"} for n in names}}


def test_axis_discovery_proposes_above_min_support():
    dictionary = _dict_with_axes("hook_type")
    batch = [{"features": [{"feature_axis": "new_axis", "value": v}]} for v in
             ["x", "y", "z"]]  # support 3
    res = axis_discovery.discover(batch, dictionary, min_support=3)
    assert res["auto_write_dictionary"] is False
    assert len(res["proposals"]) == 1
    prop = res["proposals"][0]
    assert prop["candidate_axis"] == "new_axis"
    assert prop["status"] == "candidate"


def test_axis_discovery_below_min_support_no_proposal():
    dictionary = _dict_with_axes("hook_type")
    batch = [{"features": [{"feature_axis": "rare_axis", "value": "x"}]}]
    res = axis_discovery.discover(batch, dictionary, min_support=3)
    assert res["proposals"] == []


def test_axis_discovery_skips_known_axes():
    dictionary = _dict_with_axes("hook_type")
    batch = [{"features": [{"feature_axis": "hook_type", "value": "x"}]} for _ in range(5)]
    res = axis_discovery.discover(batch, dictionary, min_support=1)
    assert res["unknown_axes"] == {}


# ============================ 版本化字典：轴集合冻结 ============================
def test_versioning_add_axis_is_major():
    old = _dict_with_axes("a")
    new = _dict_with_axes("a", "b")
    cls = dv.classify_change(old, new)
    assert cls["change_type"] == "major"
    assert cls["added_axes"] == ["b"]


def test_versioning_weight_only_is_minor():
    old = {"version": "1.0.0", "axes": {"a": {"domain": "content", "weight": "high"}}}
    new = {"version": "1.0.0", "axes": {"a": {"domain": "content", "weight": "low"}}}
    cls = dv.classify_change(old, new)
    assert cls["change_type"] == "minor"
    assert cls["modified_axes"] == ["a"]


def test_versioning_minor_with_axis_change_raises():
    # 轴集合在一个 major 内冻结：minor bump 却伴随增删轴 → raise
    with pytest.raises(ValueError):
        dv.bump("1.0.0", "minor", added_or_removed=True)


def test_versioning_publish_does_not_write_disk_and_diffs_sparse():
    old = _dict_with_axes("a", "b")
    new = _dict_with_axes("a", "b", "c")
    rec = dv.publish(old, new)
    assert rec["written_to_disk"] is False
    assert rec["to_version"] == "1.0.0"  # 0.x major bump → 1.0.0（old 默认 0.0.0）
    # 稀疏 diff：只含新轴 c × 既有轴 {a,b}，不含既有轴两两组合
    pairs = {(d["new_axis"], d["existing_axis"]) for d in rec["diffs"]}
    assert pairs == {("c", "a"), ("c", "b")}


# ============================ 纪律4：日落 / 休眠 + TTL ============================
def _dict_with_domains():
    return {"axes": {
        "hook_type": {"domain": "content", "signal_kind": "leading"},
        "target_audience": {"domain": "audience", "signal_kind": "lagging"},
    }}


def test_sunset_content_axis_hibernates_not_retire():
    d = _dict_with_domains()
    res = eb.sunset_check("hook_type", d, evidence_count=10, budget_N=5,
                          posterior_band="insufficient")
    assert res["action"] == "hibernate"


def test_sunset_advisory_axis_can_retire():
    d = _dict_with_domains()
    res = eb.sunset_check("target_audience", d, evidence_count=10, budget_N=5,
                          posterior_band="insufficient")
    assert res["action"] == "retire"


def test_sunset_within_budget_deprioritizes():
    d = _dict_with_domains()
    res = eb.sunset_check("hook_type", d, evidence_count=2, budget_N=5,
                          posterior_band="insufficient")
    assert res["action"] == "deprioritize"


def test_sunset_sufficient_evidence_keeps():
    d = _dict_with_domains()
    res = eb.sunset_check("hook_type", d, evidence_count=10, budget_N=5,
                          posterior_band="lean_adopt")
    assert res["action"] == "keep"


def test_ttl_leading_decays_faster_than_lagging():
    lead = eb.ttl_decay("leading", 30)
    lag = eb.ttl_decay("lagging", 30)
    # 同样 30 天：leading 已半衰（更快衰减），lagging 衰减更少
    assert lead["decay_weight"] < lag["decay_weight"]
    assert lead["halflife_days"] < lag["halflife_days"]


def test_ttl_leading_goes_stale_earlier():
    # leading 2×半衰=60 天即 stale；同样 60 天 lagging 尚未 stale（半衰 90）
    assert eb.ttl_decay("leading", 60)["stale"] is True
    assert eb.ttl_decay("lagging", 60)["stale"] is False
