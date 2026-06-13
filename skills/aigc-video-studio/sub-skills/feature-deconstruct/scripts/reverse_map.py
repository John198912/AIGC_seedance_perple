#!/usr/bin/env python3
"""反向映射：N≥3 份 C13 → C14 CreativeDNA（核心 IP · 设计稿 v5.0 第五部分）。

确定性、不触网、无 LLM。流程：
  1. 取 N≥3 作品 C13 的结构层共性交集（同一 axis.value 在≥阈值份作品出现）；
     单参考贡献模式数硬上限 ≤3（降版权风险）；
  2. 每条特征按字典 maps_to 映射到阶段，生成 directive（查表模板）；
  3. coherence 校验（查 axis-constraints）：命中 conflict → 报矛盾、要求取舍、resolved=false；
  4. 机械具体性地板：directive 必须含阶段 + 具体字段/槽位/数值 token；
     只含形容词通用套话 → specificity_ok=false，判废；
  5. provenance 传递：inferred 项进入 C14 仅作 advisory，永不门控。
  + forbidden：禁迁具体角色/台词/分镜构图/BGM 旋律。

CLI：
  python reverse_map.py --refs <C13_list.yaml/json> --out <C14.json> [--json]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str((Path(__file__).resolve().parent.parent.parent
                        / "_shared" / "scripts")))
from _common import read_yaml, write_json  # noqa: E402
import feature_dict as fd  # noqa: E402

MIN_REFS = 3                 # N≥3 交集
PER_REF_PATTERN_CAP = 3      # 单参考贡献模式数硬上限

# directive 模板：axis.value → (阶段, 含具体字段/槽位/数值 token 的指令)
# 机械具体性：每条都引用具体 schema 字段/镜头槽位，满足具体性地板。
_DIRECTIVE_TEMPLATES: dict[str, str] = {
    "hook_type.suspense_question":
        "screenplay-writer：脚本首镜文案设为悬念式提问，落 scenes[0].dialogue 字段。",
    "hook_type.shock_open":
        "screenplay-writer：首镜以冲突/震撼事件开场，落 scenes[0].action 字段。",
    "hook_type.direct_promise":
        "screenplay-writer：首镜直给价值承诺，落 scenes[0].dialogue 字段。",
    "emotion_curve_shape.low_start_midrise":
        "screenplay-writer：目标情绪曲线=低起·中段反转上扬，注入编剧提示，"
        "产出后由 emotion_curve.py 校验贴合度与无连续平值。",
    "emotion_curve_shape.flat_low":
        "screenplay-writer：目标情绪曲线=低起压抑，注入编剧提示，"
        "由 emotion_curve.py 事后校验。",
    "pacing.fast_cut":
        "edit-finish：剪辑节拍设为快切高频，单镜 shots[].duration_s ≤ 2s。",
    "pacing.slow_long_take":
        "edit-finish：剪辑节拍设为慢节奏长镜，单镜 shots[].duration_s ≥ 8s。",
    "narrative_structure.three_act":
        "screenplay-writer：叙事骨架=三幕结构，落 screenplay 场次 scenes[] 分段。",
    "narrative_structure.twist_ending":
        "screenplay-writer：结尾反转，落最后一场 scenes[-1].action 字段。",
    "narrative_structure.in_medias_res":
        "screenplay-writer：中段切入开场，落 scenes[0] 场次顺序。",
    "narrative_structure.loop_callback":
        "screenplay-writer：首尾呼应环形结构，scenes[0] 与 scenes[-1] 回扣同一意象。",
    "shot_grammar.fast_cut_handheld":
        "storyboard-director：运镜语法=快切+手持微晃（语法层非具体构图），落 shots[].camera_move。",
    "shot_grammar.slow_dolly":
        "storyboard-director：运镜语法=缓慢推轨，落 shots[].camera_move。",
    "shot_grammar.locked_static":
        "storyboard-director：运镜语法=固定机位，落 shots[].camera_move。",
}

# advisory（①②④）directive：仅顾问，落 concept-brief，标可覆盖
_ADVISORY_TEMPLATES: dict[str, str] = {
    "target_audience": "concept-brief：target_audience 字段填 {value}（advisory，可被创作者覆盖）。",
    "view_scene": "concept-brief：观看场景顾问提示 {value}（不进硬约束）。",
    "engagement_behavior": "concept-brief：互动行为顾问提示 {value}（不进硬约束）。",
}

# 机械具体性地板：具体性 token（阶段+字段/槽位/数值）。命中任一视为具体。
_SPECIFICITY_TOKENS = (
    "scenes[", "shots[", "dialogue", "action", "camera_move", "duration_s",
    "target_audience", "screenplay", "storyboard", "emotion_curve",
)
# 通用套话黑名单（只含形容词→判废）
_VAGUE_PHRASES = ("吸引人", "有趣", "高质量", "更好", "精彩", "完美")

# 禁迁项（表达层，永不迁）
FORBIDDEN = [
    "具体角色名/形象",
    "具体台词/slogan",
    "具体分镜构图",
    "BGM 具体旋律",
]


def _has_specificity(directive: str) -> bool:
    """机械具体性地板：含具体字段/槽位/数值 token 且非纯通用套话。"""
    if any(v in directive for v in _VAGUE_PHRASES) and \
            not any(t in directive for t in _SPECIFICITY_TOKENS):
        return False
    return any(t in directive for t in _SPECIFICITY_TOKENS)


def _intersect_structural(tagsets: list[dict[str, Any]],
                          dictionary: dict[str, Any]) -> list[dict[str, Any]]:
    """取结构层（content）共性交集：同一 axis.value 在 ≥MIN_REFS 份作品出现。

    单参考贡献模式数硬上限 ≤PER_REF_PATTERN_CAP。返回去重的承重特征列表。
    """
    axes = dictionary.get("axes", {})
    # 统计每个 axis.value 出现于哪些 ref，并记一个代表特征
    occur: dict[str, set[str]] = {}
    sample: dict[str, dict[str, Any]] = {}
    per_ref_count: dict[str, int] = {}

    for ts in tagsets:
        ref_id = ts.get("ref_id", "")
        contributed = 0
        for feat in ts.get("features", []):
            if feat.get("domain") != "content":
                continue
            if contributed >= PER_REF_PATTERN_CAP:
                break  # 单参考硬上限
            key = f"{feat['feature_axis']}.{feat['value']}"
            occur.setdefault(key, set()).add(ref_id)
            sample.setdefault(key, feat)
            per_ref_count[ref_id] = per_ref_count.get(ref_id, 0) + 1
            contributed += 1

    common: list[dict[str, Any]] = []
    for key, refs in occur.items():
        if len(refs) >= MIN_REFS:
            feat = dict(sample[key])
            feat["source_refs"] = sorted(refs)
            common.append(feat)
    return common


def _advisory_patterns(tagsets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """收集 ①②④ advisory 特征（永不门控）；去重保序。"""
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for ts in tagsets:
        for feat in ts.get("features", []):
            if feat.get("domain") == "content":
                continue
            key = f"{feat['feature_axis']}.{feat['value']}"
            if key in seen:
                continue
            seen.add(key)
            out.append(feat)
    return out


def _build_pattern(feat: dict[str, Any], dictionary: dict[str, Any]) -> dict[str, Any]:
    """把一条特征映射为 C14 transferable_pattern（含 directive + 具体性判废）。"""
    axis = feat["feature_axis"]
    value = feat["value"]
    meta = dictionary["axes"].get(axis, {})
    key = f"{axis}.{value}"
    domain = feat.get("domain", meta.get("domain", "content"))

    if domain == "content":
        directive = _DIRECTIVE_TEMPLATES.get(
            key, f"（无模板，待补具体阶段+字段）：{axis}={value}")
    else:
        tmpl = _ADVISORY_TEMPLATES.get(axis, "concept-brief：顾问提示 {value}。")
        directive = tmpl.format(value=value)

    provenance = feat.get("provenance", "observed")
    # provenance 传递：inferred 或 ①②④ → advisory，永不门控
    advisory = bool(feat.get("advisory", False)) or provenance == "inferred" \
        or domain != "content"

    return {
        "feature_axis": axis,
        "value": value,
        "provenance": provenance,
        "confidence_tier": feat.get("confidence_tier", "high"),
        "maps_to": list(meta.get("maps_to", [])),
        "directive": directive,
        "ip_layer": "structural",
        "specificity_ok": _has_specificity(directive),
        "advisory": advisory,
    }


def reverse_map(tagsets: list[dict[str, Any]],
                dictionary: dict[str, Any] | None = None,
                constraints: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """N≥3 份 C13 → C14 CreativeDNA。"""
    d = dictionary or fd.load_dictionary()
    rules = constraints if constraints is not None else fd.load_constraints()
    if len(tagsets) < MIN_REFS:
        raise ValueError(f"反向映射需 N≥{MIN_REFS} 份 C13，当前 {len(tagsets)}")

    common = _intersect_structural(tagsets, d)
    patterns = [_build_pattern(f, d) for f in common]
    # 机械具体性地板：判废通用套话项
    patterns = [p for p in patterns if p["specificity_ok"]]

    # ①②④ advisory（永不门控）
    for feat in _advisory_patterns(tagsets):
        p = _build_pattern(feat, d)
        if p["specificity_ok"]:
            patterns.append(p)

    # coherence 校验（仅对承重结构层选定组合查冲突）
    selected = [(p["feature_axis"], p["value"]) for p in patterns
                if not p["advisory"]]
    conflicts = fd.check_coherence(selected, rules)
    has_hard = any(c["relation"] == "conflict" for c in conflicts)

    source_ref_ids = sorted({ref for ts in tagsets for ref in [ts.get("ref_id", "")] if ref})
    return {
        "source_ref_ids": source_ref_ids,
        "transferable_patterns": patterns,
        "coherence": {"conflicts": conflicts, "resolved": not has_hard},
        "forbidden": list(FORBIDDEN),
    }


def _load_tagsets(path: str | Path) -> list[dict[str, Any]]:
    data = read_yaml(path) or {}
    if isinstance(data, list):
        return data
    return data.get("tagsets") or data.get("feature_tag_sets") or []


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="反向映射 C13 → C14（M1，确定性·不触网）")
    parser.add_argument("--refs", required=True, help="C13 列表文件（yaml/json）")
    parser.add_argument("--out", help="C14 输出路径")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    tagsets = _load_tagsets(args.refs)
    dna = reverse_map(tagsets)
    if args.out:
        write_json(args.out, dna)
    if args.json:
        print(json.dumps(dna, ensure_ascii=False))
    else:
        print(f"反向映射完成：{len(dna['transferable_patterns'])} 条模式，"
              f"冲突 {len(dna['coherence']['conflicts'])} 条，"
              f"resolved={dna['coherence']['resolved']}"
              + (f" -> {args.out}" if args.out else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
