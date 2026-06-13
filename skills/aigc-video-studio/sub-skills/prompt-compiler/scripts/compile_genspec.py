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
from _common import read_yaml, write_yaml, load_lib, ensure_validate_importable  # noqa: E402

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


def _compile_layers(shot: dict[str, Any], style_core: str = "") -> dict[str, str]:
    """四层结构渲染（确定性模板）。第零层去AI味从 deai-keywords 注入。"""
    deai = load_lib("deai-keywords.yaml")
    pos = "，".join(deai["base"]["positive"])
    neg = ", ".join(deai["base"]["negative"])
    layer0 = f"正向：{pos}；反向：{neg}"

    chars = "、".join(shot.get("characters", [])) or "（无指定角色）"
    layer1 = (f"角色：{chars}；场景：{shot.get('scene', '')}；"
              f"声音：{shot.get('audio_cue', '')}")
    layer2 = f"风格核心：{style_core or '（待 style-bible 注入）'}"
    layer3 = (f"景别与构图：{shot.get('shot_size', '')} / {shot.get('composition', '')}；"
              f"运镜：{shot.get('camera_move', '')}；"
              f"画面内容：{shot.get('action_logic', '')}")

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


def compile_genspec(shot: dict[str, Any], *, version: int = 1,
                    model: str = "seedance-2.0",
                    style_core: str = "") -> dict[str, Any]:
    """把单个镜头定义编译为 GenSpec（C6）。"""
    candidates = collect_candidate_slots(shot)
    kept, dropped = allocate_slots(candidates)
    label_map = build_label_map(kept, shot.get("characters", []))

    genspec = {
        "shot_id": shot["shot_id"],
        "version": version,
        "changelog": [{"v": version, "note": "初版（compile_genspec 生成）"}],
        "model": model,
        "audio_mode": "native",
        "prompt": _compile_layers(shot, style_core),
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
    validate_obj(genspec, "C6")
    return genspec


def compile_from_shotlist(shotlist_path: str | Path, shot_id: str,
                          **kwargs) -> dict[str, Any]:
    shotlist = read_yaml(shotlist_path)
    for shot in shotlist.get("shots", []):
        if shot.get("shot_id") == shot_id:
            return compile_genspec(shot, **kwargs)
    raise ValueError(f"shotlist 中找不到镜头：{shot_id}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="GenSpec 编译（SK5）")
    parser.add_argument("--shot", required=True)
    parser.add_argument("--shotlist", required=True)
    parser.add_argument("--out", help="输出 genspec.yaml 路径；缺省打印到 stdout")
    parser.add_argument("--style-core", default="")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    genspec = compile_from_shotlist(args.shotlist, args.shot, style_core=args.style_core)

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
