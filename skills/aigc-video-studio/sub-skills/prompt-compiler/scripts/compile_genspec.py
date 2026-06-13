#!/usr/bin/env python3
"""GenSpec 编译（设计稿 §5 SK5 / §6，C6）。

职责：
- 四层结构编译（第零层去AI味 + 设定/风格/分镜）模板渲染
- 槽位预算分配器：身份>构图>风格>环境，总数 ≤12（图9/视频3/音频3），溢出记 slots_dropped
- reference_label_map 生成（语义名 -> @ImageN）
- render_passes 双 pass（draft:api/720p + final:ui/1080p）
- schema 校验（C6）

CLI：
  python compile_genspec.py --shot SHOT-07 --shotlist <path> --out <genspec.yaml> [--json]

本阶段以确定性模板渲染为主；创意性语义评分留给 prompt_qc 的占位接口与 LLM 推理层。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str((Path(__file__).resolve().parent.parent.parent
                        / "_shared" / "scripts")))
from _common import (read_yaml, write_yaml, load_lib, project_path,  # noqa: E402
                     ensure_validate_importable)

ensure_validate_importable()
from validate import validate_obj  # noqa: E402

# 槽位预算（设计稿 §1.1 / capabilities.yaml）
TOTAL_FILES_CAP = 12
PER_MODALITY_CAP = {"image": 9, "video": 3, "audio": 3}
# slot -> 计入哪个模态配额
SLOT_MODALITY = {
    "image": "image", "start_frame": "image", "end_frame": "image",
    "video": "video", "audio": "audio",
}
# role 优先级（数字越小越优先）：身份>构图>风格>环境
ROLE_PRIORITY = {"identity": 1, "composition": 2, "motion": 3, "style": 4, "environment": 5}

# 行为逻辑分层模板（设计稿 §6.2，S-P1-5）：戏种 -> 中间层（处境/动作|情绪/因果之外的可变层）。
# 各戏种统一为：处境层 -> [动作层|情绪层] -> 因果层 -> 留白层。
DRAMA_LAYER_TEMPLATES = {
    "动作戏": ["处境层", "动作层", "因果层", "留白层"],
    "情感戏": ["处境层", "情绪层", "因果层", "留白层"],
    "追逐戏": ["处境层", "动作层", "因果层", "留白层"],
}
DEFAULT_DRAMA_TYPE = "动作戏"


def build_behavior_logic(shot: dict[str, Any],
                         character_cards: dict[str, dict[str, Any]] | None = None
                         ) -> dict[str, Any]:
    """行为逻辑分层增强（设计稿 §6.2 R1–R5）。

    按 shot.drama_type 选分层模板，从主角 CharacterCard.feature_card.behavior_traits
    自动提取动机填充各层；R4 留白层显式声明非关键细节交模型自由发挥。
    返回 {drama_type, layers:[{layer,text}], motivation_source, layered_text}。
    确定性：仅由镜头字段 + 角色卡派生，无随机、不触网。
    """
    character_cards = character_cards or {}
    drama_type = shot.get("drama_type") or DEFAULT_DRAMA_TYPE
    layer_names = DRAMA_LAYER_TEMPLATES.get(drama_type,
                                            DRAMA_LAYER_TEMPLATES[DEFAULT_DRAMA_TYPE])

    # R5 素材来源：动机优先取自主角 behavior_traits
    chars = shot.get("characters", [])
    lead = chars[0] if chars else None
    traits = ""
    if lead and lead in character_cards:
        fc = character_cards[lead].get("feature_card", {})
        traits = (fc.get("behavior_traits") or "").strip()
    motivation_source = f"{lead}.behavior_traits" if traits else "（无 behavior_traits，留空待补）"

    action = (shot.get("action_logic") or "").strip()
    scene = (shot.get("scene") or "").strip()

    layers: list[dict[str, str]] = []
    for name in layer_names:
        if name == "处境层":
            text = f"处境：{scene or '（场景待定）'}"
        elif name == "动作层":
            text = f"动作/位移：{action or '（动作待定）'}"
        elif name == "情绪层":
            text = f"外显情绪/微表情：{action or '（情绪表达待定）'}"
        elif name == "因果层":
            # R1 动机补全 + R2 情绪因果：挂动机从句，优先取 behavior_traits
            motive = traits or "（动机待补，建议回填 behavior_traits）"
            text = f"动机/因果（R1/R2）：{motive}"
        else:  # 留白层（R4）
            text = "留白（R4）：非关键细节（周边环境/次要元素）交由模型自由发挥，不锁死每一帧"
        layers.append({"layer": name, "text": text})

    layered_text = "；".join(f"{l['layer']}→{l['text']}" for l in layers)
    return {
        "drama_type": drama_type,
        "layers": layers,
        "motivation_source": motivation_source,
        "layered_text": layered_text,
    }


def build_composition_block(shot: dict[str, Any]) -> str:
    """坐标化构图注入（设计稿 §6.2 A.2）。

    把 composition 的坐标化写法（三分/对角线/画面分割）规范化为分镜层可注入文本，
    缺省给出三分法占位以保证八要素 composition 不缺项。
    """
    comp = (shot.get("composition") or "").strip()
    shot_size = (shot.get("shot_size") or "").strip()
    if not comp:
        comp = "主体置三分线交点（默认），留白侧引导视线（坐标化占位）"
    return f"景别：{shot_size or '（景别待定）'}；构图（坐标化）：{comp}"


def allocate_slots(candidate_slots: list[dict[str, Any]]) -> tuple[list[dict], list[dict]]:
    """槽位预算分配器。

    输入候选参考槽位（每条含 file/slot/role），按 role 优先级排序，
    在总数 ≤12 与每模态上限约束下分配，溢出者记入 slots_dropped。
    返回 (kept, dropped)。
    """
    def sort_key(s: dict[str, Any]) -> tuple[int, int]:
        explicit = s.get("priority")
        role_pri = ROLE_PRIORITY.get(s.get("role"), 99)
        return (explicit if explicit is not None else role_pri, role_pri)

    ordered = sorted(candidate_slots, key=sort_key)
    kept: list[dict[str, Any]] = []
    dropped: list[dict[str, Any]] = []
    modality_used = {"image": 0, "video": 0, "audio": 0}

    for s in ordered:
        modality = SLOT_MODALITY.get(s["slot"], "image")
        over_total = len(kept) >= TOTAL_FILES_CAP
        over_modality = modality_used[modality] >= PER_MODALITY_CAP[modality]
        if over_total or over_modality:
            reason = "超总12" if over_total else f"超{modality}模态上限"
            dropped.append({**s, "reason": reason})
            continue
        # 归一 priority 字段（schema 必填）
        item = dict(s)
        item.setdefault("priority", ROLE_PRIORITY.get(s.get("role"), 99))
        kept.append(item)
        modality_used[modality] += 1

    return kept, dropped


def build_label_map(kept_slots: list[dict[str, Any]],
                    characters: list[str]) -> dict[str, str]:
    """生成 reference_label_map：语义名 -> @ImageN（按 image 类槽位顺序）。"""
    label_map: dict[str, str] = {}
    image_idx = 0
    # 角色身份槽位优先映射到角色语义名
    char_iter = iter(characters)
    for s in kept_slots:
        if SLOT_MODALITY.get(s["slot"]) == "image":
            image_idx += 1
            placeholder = f"@Image{image_idx}"
            if s.get("role") == "identity":
                sem = next(char_iter, None)
                key = f"@{sem}" if sem else f"@{Path(s['file']).stem}"
            else:
                key = f"@{Path(s['file']).stem}"
            label_map[key] = placeholder
    return label_map


def _compile_layers(shot: dict[str, Any], style_core: str = "",
                    character_cards: dict[str, dict[str, Any]] | None = None
                    ) -> dict[str, str]:
    """四层结构渲染（确定性模板）。第零层去AI味从 deai-keywords 注入。

    分镜层（layer3）融入：坐标化构图（A.2）+ 行为逻辑分层（A.1，§6.2）。
    """
    deai = load_lib("deai-keywords.yaml")
    pos = "，".join(deai["base"]["positive"])
    neg = ", ".join(deai["base"]["negative"])
    layer0 = f"正向：{pos}；反向：{neg}"

    chars = "、".join(shot.get("characters", [])) or "（无指定角色）"
    layer1 = (f"角色：{chars}；场景：{shot.get('scene', '')}；"
              f"声音：{shot.get('audio_cue', '')}")
    layer2 = f"风格核心：{style_core or '（待 style-bible 注入）'}"

    composition_block = build_composition_block(shot)
    behavior = build_behavior_logic(shot, character_cards)
    layer3 = (f"{composition_block}；"
              f"运镜：{shot.get('camera_move', '')}；"
              f"行为逻辑（{behavior['drama_type']}）：{behavior['layered_text']}")

    compiled_zh = f"【去AI味】{pos}\n【设定】{layer1}\n【风格】{layer2}\n【分镜】{layer3}"
    return {
        "layer0_deai": layer0,
        "layer1_setting": layer1,
        "layer2_style": layer2,
        "layer3_shot": layer3,
        "compiled_zh": compiled_zh,
        "compiled_en": "(English compiled prompt placeholder)",
    }


def _build_render_passes(shot: dict[str, Any]) -> list[dict[str, Any]]:
    """按 control_level 生成 render_passes（设计稿 routing-rules）。"""
    control = shot.get("control_level", "guided")
    draft = {
        "pass": "draft", "channel": "api",
        "endpoint": "falai_reference_to_video", "resolution": "720p",
        "camera_handling": "fallback_text",
        "rolling": {
            "takes_planned": 4, "max_takes": 8,
            "qualified_def": "vlm.verdict==pass 且 human>=4",
            "prior": "Beta(1,3)",
            "stop_rule": "[已有>=1达标 且 E[p]*V_marginal < C_take] 或 takes>=max 或 累计>=per_shot_cost_cap",
            "fallback_simple_rule": "N个达标即停 + 成本上限",
        },
    }
    final = {
        "pass": "final", "channel": "ui", "entry": "cinema_studio",
        "platform": "higgsfield", "resolution": "1080p",
        "source_take": "selected", "rolling": {"takes_planned": 1, "max_takes": 2},
    }
    if control == "free":
        return [draft]            # 氛围空镜：放手赌即兴，仅 draft
    if control == "locked":
        return [final]            # 叙事关键帧：可只保 final 一 pass（直接 UI 高保真）
    return [draft, final]         # guided：双 pass


def collect_candidate_slots(shot: dict[str, Any]) -> list[dict[str, Any]]:
    """从镜头定义收集候选参考槽位（身份/构图/风格等）。

    本阶段以镜头字段确定性派生；真实场景由 SK5 结合角色卡/风格库组装。
    """
    slots: list[dict[str, Any]] = []
    for c in shot.get("characters", []):
        slots.append({"file": f"03_characters/{c}/turnaround/front.png",
                      "slot": "image", "role": "identity"})
    if shot.get("first_frame"):
        slots.append({"file": shot["first_frame"], "slot": "start_frame",
                      "role": "composition"})
    # 显式提供的额外候选（可选）
    slots.extend(shot.get("extra_reference_slots", []))
    return slots


def _build_continuity(shot: dict[str, Any]) -> dict[str, Any] | None:
    """尾帧延续（A.4，设计稿 §6.2 / C6.continuity）。

    从镜头的 continuity 字段派生 prev_shot/last_frame_file/micro_motion_lead_s，
    供 make_taskcards 在 API/UI 卡注入尾帧延续参考。镜头未声明则返回 None。
    """
    cont = shot.get("continuity")
    if not cont:
        return None
    out: dict[str, Any] = {}
    if cont.get("prev_shot"):
        out["prev_shot"] = cont["prev_shot"]
    if cont.get("last_frame_file"):
        out["last_frame_file"] = cont["last_frame_file"]
    lead = cont.get("micro_motion_lead_s")
    if lead is not None:
        out["micro_motion_lead_s"] = lead
    return out or None


def compile_genspec(shot: dict[str, Any], *, version: int = 1,
                    model: str = "seedance-2.0",
                    style_core: str = "",
                    character_cards: dict[str, dict[str, Any]] | None = None
                    ) -> dict[str, Any]:
    """把单个镜头定义编译为 GenSpec（C6）。

    character_cards: {角色id -> CharacterCard}，供行为逻辑分层（§6.2）取 behavior_traits。
    """
    candidates = collect_candidate_slots(shot)
    kept, dropped = allocate_slots(candidates)
    label_map = build_label_map(kept, shot.get("characters", []))

    genspec = {
        "shot_id": shot["shot_id"],
        "version": version,
        "changelog": [{"v": version, "note": "初版（compile_genspec 生成）"}],
        "model": model,
        "audio_mode": shot.get("audio_mode", "native"),
        "prompt": _compile_layers(shot, style_core, character_cards),
        "reference_slots": kept,
        "slots_dropped": dropped,
        "reference_label_map": label_map,
        "render_passes": _build_render_passes(shot),
        "compliance_applied": [],
        "prompt_qc": {
            "structural_blockers": [],
            "craft_score": None,
            "deai_score": None,
            "rubric_anchor_drift": None,
        },
        "acceptance": [],
    }
    continuity = _build_continuity(shot)
    if continuity:
        genspec["continuity"] = continuity
    validate_obj(genspec, "C6")
    return genspec


def load_character_cards(project: str | Path | None,
                         char_ids: list[str]) -> dict[str, dict[str, Any]]:
    """从项目 03_characters/<id>/card.yaml 加载指定角色卡（缺失则跳过）。"""
    if not project:
        return {}
    cards: dict[str, dict[str, Any]] = {}
    for cid in char_ids:
        cp = project_path(project, "03_characters", cid, "card.yaml")
        if cp.exists():
            cards[cid] = read_yaml(cp)
    return cards


def compile_variants(shot: dict[str, Any], *, style_cores: list[str] | None = None,
                     character_cards: dict[str, dict[str, Any]] | None = None,
                     **kwargs) -> list[dict[str, Any]]:
    """同一镜头编译多提示词变体（A/B 并行探索，S-P1-6 / exploration 档）。

    每个 style_core 产出一个 GenSpec 变体，version 递增，并打不同 prompt_pattern_tag
    （variant-A/B/...）供下游抽卡后用 metrics.compare_ab 对比命中率。
    style_cores 缺省给两路（A/B）默认基调。
    """
    style_cores = style_cores or ["写实克制基调", "高反差戏剧基调"]
    out: list[dict[str, Any]] = []
    for i, core in enumerate(style_cores):
        g = compile_genspec(shot, version=i + 1, style_core=core,
                            character_cards=character_cards, **kwargs)
        tag = f"variant-{chr(ord('A') + i)}"
        g["prompt_pattern_tag"] = tag
        g["changelog"] = [{"v": i + 1, "note": f"A/B 变体 {tag}：style_core={core}"}]
        validate_obj(g, "C6")
        out.append(g)
    return out


def compile_from_shotlist(shotlist_path: str | Path, shot_id: str,
                          *, project: str | Path | None = None,
                          **kwargs) -> dict[str, Any]:
    shotlist = read_yaml(shotlist_path)
    for shot in shotlist.get("shots", []):
        if shot.get("shot_id") == shot_id:
            if project and "character_cards" not in kwargs:
                kwargs["character_cards"] = load_character_cards(
                    project, shot.get("characters", []))
            return compile_genspec(shot, **kwargs)
    raise ValueError(f"shotlist 中找不到镜头：{shot_id}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="GenSpec 编译（SK5）")
    parser.add_argument("--shot", required=True)
    parser.add_argument("--shotlist", required=True)
    parser.add_argument("--project", help="项目目录（用于加载角色卡 behavior_traits）")
    parser.add_argument("--out", help="输出 genspec.yaml 路径；缺省打印到 stdout")
    parser.add_argument("--style-core", default="")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    genspec = compile_from_shotlist(args.shotlist, args.shot,
                                    project=args.project, style_core=args.style_core)

    if args.out:
        write_yaml(args.out, genspec)
    if args.json:
        print(json.dumps(genspec, ensure_ascii=False))
    elif not args.out:
        print(json.dumps(genspec, ensure_ascii=False, indent=2))
    else:
        print(f"GenSpec 已编译：{args.out}（kept={len(genspec['reference_slots'])}, "
              f"dropped={len(genspec['slots_dropped'])}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
