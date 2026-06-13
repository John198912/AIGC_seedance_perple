#!/usr/bin/env python3
"""多画幅适配计划（设计稿 §5 SK10，Q-8，P2 轻量实现）。

根据 master 画幅生成多画幅裁切计划（21:9→16:9→9:16→1:1），含目标尺寸与
裁切策略（中心安全框 + 关键主体保护占位）。本阶段只产计划，不做实际裁切。

CLI：
  python render_variants.py --source-aspect 16:9 [--targets 9:16 1:1] [--json]
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import Any

# 常见目标画幅 → 基准 1080 短边的像素尺寸
ASPECT_DIMS = {
    "21:9": (2520, 1080),
    "16:9": (1920, 1080),
    "9:16": (1080, 1920),
    "1:1": (1080, 1080),
    "4:5": (1080, 1350),
}
DEFAULT_TARGETS = ["16:9", "9:16", "1:1"]


def _ratio(aspect: str) -> float:
    w, h = aspect.split(":")
    return float(w) / float(h)


def plan_variants(source_aspect: str, targets: list[str]) -> dict[str, Any]:
    src_r = _ratio(source_aspect)
    variants = []
    for t in targets:
        if t not in ASPECT_DIMS:
            variants.append({"aspect": t, "error": "未知目标画幅"})
            continue
        tgt_r = _ratio(t)
        if tgt_r > src_r:
            strategy = "上下加画 / 左右裁切（目标更宽）"
        elif tgt_r < src_r:
            strategy = "左右裁切，保中心安全框（目标更高）"
        else:
            strategy = "等比缩放"
        w, h = ASPECT_DIMS[t]
        variants.append({"aspect": t, "width": w, "height": h, "strategy": strategy})
    return {"source_aspect": source_aspect, "variants": variants}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="多画幅适配计划（SK10，P2）")
    parser.add_argument("--source-aspect", default="16:9")
    parser.add_argument("--targets", nargs="+", default=DEFAULT_TARGETS)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    plan = plan_variants(args.source_aspect, args.targets)
    if args.json:
        print(json.dumps(plan, ensure_ascii=False))
    else:
        print(f"源画幅 {plan['source_aspect']} → 适配：")
        for v in plan["variants"]:
            if v.get("error"):
                print(f"  {v['aspect']}: {v['error']}")
            else:
                print(f"  {v['aspect']} {v['width']}x{v['height']}: {v['strategy']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
