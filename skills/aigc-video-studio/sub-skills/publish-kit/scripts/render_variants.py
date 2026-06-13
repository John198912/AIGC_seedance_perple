#!/usr/bin/env python3
"""多画幅适配 + 平台发布包（设计稿 §5 SK10，Q-8，Phase 4 可用实现）。

两层能力：
1. `plan_variants`：按 master 画幅生成多画幅裁切计划（21:9→16:9→9:16→1:1），
   含目标尺寸与裁切策略（中心安全框 + 关键主体保护占位）。仅产计划，不实裁切。
2. `build_package`：为每个 target_platform 产出 `09_publish/<platform>/` 发布包：
   - variants.yaml（多画幅适配表）
   - cover.yaml（封面候选，调用 cover_extractor）
   - metadata.yaml（标题/标签/发布时段等冷启动建议占位）
   - aigc-declaration.md（AIGC 声明合规 + 水印说明，强制）
   - README.md（人读发布清单）

媒体实体（成片/封面图）为占位文件，遵守项目 .gitignore（09_publish/ 不入仓）。
确定性：尺寸/策略/平台清单均由输入派生，可复现，不触网。

CLI：
  python render_variants.py --source-aspect 16:9 [--targets 9:16 1:1] [--json]
  python render_variants.py --project <dir> [--platforms douyin bilibili] [--json]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str((Path(__file__).resolve().parent.parent.parent
                        / "_shared" / "scripts")))
from _common import read_yaml, write_yaml, project_path  # noqa: E402

# 当前脚本目录可导入同目录 cover_extractor
sys.path.insert(0, str(Path(__file__).resolve().parent))
import cover_extractor  # noqa: E402

# 常见目标画幅 → 基准 1080 短边的像素尺寸
ASPECT_DIMS = {
    "21:9": (2520, 1080),
    "16:9": (1920, 1080),
    "9:16": (1080, 1920),
    "1:1": (1080, 1080),
    "4:5": (1080, 1350),
}
DEFAULT_TARGETS = ["16:9", "9:16", "1:1"]

# 平台默认偏好画幅（活文档雏形，详见 references/platform-rules.md）
PLATFORM_ASPECT = {
    "douyin": "9:16",
    "kuaishou": "9:16",
    "xiaohongshu": "9:16",
    "bilibili": "16:9",
    "youtube": "16:9",
    "youtube_shorts": "9:16",
}
# 各平台 AIGC 标注义务（强制声明）
PLATFORM_AIGC = {
    "douyin": "须开启平台「AI 生成」标识 + 画面水印，违规限流。",
    "kuaishou": "须勾选「AIGC 内容」声明。",
    "xiaohongshu": "须标注「AI 创作」并避免误导性真人宣称。",
    "bilibili": "须在简介声明 AIGC 并开启「虚拟/AI」标签。",
    "youtube": "须在「Altered or synthetic content」处声明合成内容。",
    "youtube_shorts": "同 YouTube：声明合成内容。",
}


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


def _load_project_meta(project: str | Path) -> dict[str, Any]:
    pj = project_path(project, "project.yaml")
    return read_yaml(pj) if pj.exists() else {}


def _aigc_declaration_md(platform: str, title: str) -> str:
    """AIGC 声明合规文档（强制）。"""
    obligation = PLATFORM_AIGC.get(platform, "按平台规则标注 AIGC 生成内容。")
    return (f"# AIGC 声明合规（{platform}）\n\n"
            f"作品《{title}》全片由 AIGC（Seedance 2.0 等）生成，发布前须完成：\n\n"
            f"- **平台标注义务**：{obligation}\n"
            f"- **画面水印**：成片右下角保留「AI 生成」水印（不可移除）。\n"
            f"- **IP 合规**：致敬/改编类已核验版权风险；命中即阻断自动发布并人工复核。\n"
            f"- **不可逆提示**：发布为不可逆动作，须经 G9 导演终确认。\n")


def build_package(project: str | Path, *,
                  platforms: list[str] | None = None) -> dict[str, Any]:
    """为每个目标平台生成 09_publish/<platform>/ 发布包。"""
    meta = _load_project_meta(project)
    title = meta.get("title", "未命名")
    source_aspect = meta.get("aspect_ratio", "16:9")
    platforms = platforms or meta.get("target_platform") or ["douyin"]

    cover = cover_extractor.extract(project, top=3)
    packages: list[dict[str, Any]] = []
    for plat in platforms:
        primary_aspect = PLATFORM_ASPECT.get(plat, "16:9")
        # 适配目标：平台主画幅优先，附通用 1:1
        targets = list(dict.fromkeys([primary_aspect, "1:1"]))
        variants = plan_variants(source_aspect, targets)

        pdir = project_path(project, "09_publish", plat)
        pdir.mkdir(parents=True, exist_ok=True)

        write_yaml(pdir / "variants.yaml", variants)
        write_yaml(pdir / "cover.yaml", cover)
        metadata = {
            "platform": plat,
            "title": title,
            "primary_aspect": primary_aspect,
            "tags_suggested": meta.get("style_keywords", []) or [],
            "cold_start_note": "标题/标签/首图/发布时段为建议占位，导演终定（不代发）。",
            "aigc_declared": True,
        }
        write_yaml(pdir / "metadata.yaml", metadata)
        (pdir / "aigc-declaration.md").write_text(
            _aigc_declaration_md(plat, title), encoding="utf-8")
        (pdir / "README.md").write_text(
            _readme_md(plat, title, variants, cover), encoding="utf-8")

        packages.append({
            "platform": plat,
            "dir": str(pdir),
            "primary_aspect": primary_aspect,
            "variant_count": len(variants["variants"]),
            "cover_candidates": len(cover["candidates"]),
            "files": ["variants.yaml", "cover.yaml", "metadata.yaml",
                      "aigc-declaration.md", "README.md"],
        })
    return {"title": title, "source_aspect": source_aspect, "packages": packages}


def _readme_md(platform: str, title: str, variants: dict[str, Any],
               cover: dict[str, Any]) -> str:
    lines = [f"# 发布包 · {platform}", "",
             f"作品：《{title}》", "",
             "## 多画幅变体", "",
             "| 画幅 | 尺寸 | 裁切策略 |", "|---|---|---|"]
    for v in variants["variants"]:
        if v.get("error"):
            lines.append(f"| {v['aspect']} | — | {v['error']} |")
        else:
            lines.append(f"| {v['aspect']} | {v['width']}x{v['height']} | {v['strategy']} |")
    lines += ["", "## 封面候选", ""]
    for c in cover["candidates"]:
        lines.append(f"- `{c['shot_id']}`（score={c['score']}）"
                     f" frame=`{c.get('first_frame')}`")
    lines += ["", "## 合规", "",
              "见 `aigc-declaration.md`（AIGC 声明 + 水印 + IP 合规，发布前 G9 终确认）。", ""]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="多画幅适配 + 平台发布包（SK10）")
    parser.add_argument("--source-aspect", default="16:9")
    parser.add_argument("--targets", nargs="+", default=DEFAULT_TARGETS)
    parser.add_argument("--project", help="给定则产出 09_publish/<platform>/ 发布包")
    parser.add_argument("--platforms", nargs="+", help="目标平台（缺省读 project.yaml）")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    if args.project:
        result = build_package(args.project, platforms=args.platforms)
        if args.json:
            print(json.dumps(result, ensure_ascii=False))
        else:
            print(f"《{result['title']}》发布包（源画幅 {result['source_aspect']}）：")
            for p in result["packages"]:
                print(f"  {p['platform']} → {p['dir']}（{p['variant_count']} 画幅 / "
                      f"{p['cover_candidates']} 封面候选）")
        return 0

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
