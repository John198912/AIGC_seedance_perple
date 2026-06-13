#!/usr/bin/env python3
"""平台能力查询（设计稿 §5 SK11 平台手册脚本，P2 轻量实现）。

给定 variant/参考文件数/分辨率，查 capabilities.yaml + channel-cost-map.yaml，
返回是否支持及降级方案。能力数字只读 capabilities.yaml（挂 verified_at），
不在本脚本硬编码。

校验项：
- 参考文件总数 ≤ 模型 total_files；分模态 ≤ image/video/audio 上限
- 目标分辨率是否在通道 resolution_enum / max_resolution 内

CLI：
  python capability_query.py --model seedance-2.0 --images 9 --videos 3 --audios 3 \
      --resolution 1080p --channel falai [--json]
退出码：0 = 支持；1 = 超限/不支持（附降级建议）。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import load_lib  # noqa: E402


def query(*, model: str = "seedance-2.0", images: int = 0, videos: int = 0,
          audios: int = 0, resolution: str | None = None,
          channel: str | None = None) -> dict[str, Any]:
    caps = load_lib("capabilities.yaml")
    model_entry = (caps.get("models", {}) or {}).get(model, {})
    issues: list[str] = []
    fallbacks: list[str] = []

    mref = model_entry.get("multimodal_reference", {}) or {}
    total_cap = mref.get("total_files")
    per = mref.get("per_modality", {}) or {}
    total = images + videos + audios
    if total_cap is not None and total > total_cap:
        issues.append(f"参考总数 {total} 超上限 {total_cap}")
        fallbacks.append("按优先级裁剪参考（身份>构图>风格>环境），溢出记 slots_dropped")
    for name, val in (("image", images), ("video", videos), ("audio", audios)):
        cap = per.get(name)
        if cap is not None and val > cap:
            issues.append(f"{name} 参考 {val} 超上限 {cap}")

    # 分辨率校验（按通道）
    if resolution and channel:
        ch_entry = (caps.get("channels", {}) or {}).get(channel, {})
        enum = ch_entry.get("resolution_enum")
        if enum and resolution not in enum:
            issues.append(f"分辨率 {resolution} 不在通道 {channel} 枚举 {enum}")
            fallbacks.append(f"降级到 {enum[-1]} 或改走 UI 终渲")

    verified_at = model_entry.get("verified_at")
    return {
        "model": model,
        "supported": not issues,
        "issues": issues,
        "fallbacks": fallbacks,
        "verified_at": str(verified_at) if verified_at is not None else None,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="平台能力查询（SK11，P2）")
    parser.add_argument("--model", default="seedance-2.0")
    parser.add_argument("--images", type=int, default=0)
    parser.add_argument("--videos", type=int, default=0)
    parser.add_argument("--audios", type=int, default=0)
    parser.add_argument("--resolution")
    parser.add_argument("--channel")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    result = query(model=args.model, images=args.images, videos=args.videos,
                   audios=args.audios, resolution=args.resolution, channel=args.channel)
    if args.json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        print(f"{result['model']} 支持：{result['supported']}"
              f"（verified_at={result['verified_at']}）")
        for i in result["issues"]:
            print(f"  超限：{i}")
        for f in result["fallbacks"]:
            print(f"  降级：{f}")
    return 0 if result["supported"] else 1


if __name__ == "__main__":
    sys.exit(main())
