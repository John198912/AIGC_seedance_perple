#!/usr/bin/env python3
"""Prompt QC 两级处理（设计稿 §5 SK5 / §6.1，S-P1-3）。

第一级（结构，硬阻断，确定性无噪声）：
  CRAFT 八要素缺项检测 -> structural_blockers[]。任一缺失即阻断出卡。

第二级（语义，仅排序/标红，不阻断）：
  craft_score（建议 ≥75）/ deai_score（≥70）/ rubric_anchor_drift（>15 告警）。
  本阶段为占位接口：提供确定性的启发式占位评分 + 可注入的 scorer 回调，
  真实语义评分由 LLM-as-Judge（按 judge-rubric.md 锚点）在推理层完成。

CLI：
  python prompt_qc.py --genspec <genspec.yaml> [--json]
退出码：0 = 通过结构校验；1 = 存在 structural_blockers（硬阻断）。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Callable

sys.path.insert(0, str((Path(__file__).resolve().parent.parent.parent
                        / "_shared" / "scripts")))
from _common import read_yaml  # noqa: E402

# CRAFT 八要素（设计稿 §6.1）
CRAFT_ELEMENTS = [
    "deai_texture",   # 去AI味质感
    "subject",        # 主体
    "action",         # 动作
    "environment",    # 背景/环境
    "visual_style",   # 视觉风格
    "camera",         # 相机/摄影
    "composition",    # 构图坐标
    "mood",           # 情绪/氛围
]

# 八要素 -> 在 genspec.prompt 中的来源字段（确定性检测）
ELEMENT_SOURCES: dict[str, Callable[[dict[str, Any]], str]] = {
    "deai_texture": lambda p: p.get("layer0_deai", ""),
    "subject": lambda p: p.get("layer1_setting", ""),
    "action": lambda p: p.get("layer3_shot", ""),
    "environment": lambda p: p.get("layer1_setting", ""),
    "visual_style": lambda p: p.get("layer2_style", ""),
    "camera": lambda p: p.get("layer3_shot", ""),
    "composition": lambda p: p.get("layer3_shot", ""),
    "mood": lambda p: p.get("layer2_style", "") + p.get("layer3_shot", ""),
}

# 各要素的关键词探针（确定性，缺词即判缺项）
ELEMENT_PROBES: dict[str, list[str]] = {
    "deai_texture": ["质感", "颗粒", "真实", "skin", "texture", "film"],
    "subject": ["角色", "主体", "character", "subject"],
    "action": ["动作", "画面内容", "action", "移", "走", "停"],
    "environment": ["场景", "环境", "scene", "背景"],
    "visual_style": ["风格", "色", "style", "基调"],
    "camera": ["运镜", "镜", "camera", "dolly", "推", "拉"],
    "composition": ["构图", "景别", "三分", "对角", "composition"],
    "mood": ["情绪", "氛围", "mood", "黄昏", "紧张", "末日"],
}


def find_structural_blockers(genspec: dict[str, Any]) -> list[str]:
    """检测八要素缺项。返回缺失要素列表（空表示通过结构校验）。"""
    prompt = genspec.get("prompt", {})
    blockers = []
    for elem in CRAFT_ELEMENTS:
        source = ELEMENT_SOURCES[elem](prompt)
        probes = ELEMENT_PROBES[elem]
        if not source or not any(probe in source for probe in probes):
            blockers.append(elem)
    return blockers


def _heuristic_score(genspec: dict[str, Any], blockers: list[str]) -> dict[str, Any]:
    """占位语义评分（确定性启发式）。真实评分由 LLM-as-Judge 替换。"""
    base = 100 - len(blockers) * 10
    prompt = genspec.get("prompt", {})
    deai_len = len(prompt.get("layer0_deai", ""))
    craft_score = max(0, min(100, base))
    deai_score = max(0, min(100, 60 + min(40, deai_len // 5)))
    return {
        "craft_score": craft_score,
        "deai_score": deai_score,
        "rubric_anchor_drift": 0,
    }


def run_qc(genspec: dict[str, Any],
           scorer: Callable[[dict[str, Any], list[str]], dict[str, Any]] | None = None
           ) -> dict[str, Any]:
    """对 GenSpec 跑两级 QC，返回填充后的 prompt_qc 段。

    scorer：可选语义评分回调（LLM-as-Judge 接入点）；缺省用确定性启发式占位。
    """
    blockers = find_structural_blockers(genspec)
    if scorer is None:
        scorer = _heuristic_score
    scores = scorer(genspec, blockers)
    return {
        "structural_blockers": blockers,
        "craft_score": scores.get("craft_score"),
        "deai_score": scores.get("deai_score"),
        "rubric_anchor_drift": scores.get("rubric_anchor_drift"),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Prompt QC 两级处理（SK5）")
    parser.add_argument("--genspec", required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    genspec = read_yaml(args.genspec)
    qc = run_qc(genspec)

    if args.json:
        print(json.dumps(qc, ensure_ascii=False))
    else:
        if qc["structural_blockers"]:
            print(f"硬阻断：缺失八要素 {qc['structural_blockers']}")
        else:
            print(f"结构校验通过 | craft={qc['craft_score']} deai={qc['deai_score']} "
                  f"drift={qc['rubric_anchor_drift']}")

    return 1 if qc["structural_blockers"] else 0


if __name__ == "__main__":
    sys.exit(main())
