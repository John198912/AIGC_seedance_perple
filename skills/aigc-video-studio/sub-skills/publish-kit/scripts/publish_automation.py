#!/usr/bin/env python3
"""多平台发布自动化（设计稿 §9 路线图 Q-8，半自动·不真实调用平台 API）。

在 render_variants.build_package（逐平台发布包）之上，批量为多平台生成：
- 各平台发布包（复用 render_variants）
- 统一发布元数据（标题/标签/画幅/AIGC 声明状态/计划发布时段占位）
- 一键发布清单 publish-checklist.md（人工逐平台勾选执行；发布为不可逆动作，G9 终确认）
- 汇总 publish-automation.yaml（机读，供后续观众反馈闭环 D-7 关联）

半自动纪律：**不真实调用任何平台 API**，仅产物料 + 清单，导演人工逐平台发布；
AIGC 声明强制；媒体实体走 media-manifest 不入仓。

确定性：平台清单/画幅/声明由 project.yaml + 平台表派生，可复现、不触网。

CLI：
  python publish_automation.py --project <dir> [--platforms douyin bilibili] [--json]
"""
from __future__ import annotations

import argparse
import datetime
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str((Path(__file__).resolve().parent.parent.parent
                        / "_shared" / "scripts")))
from _common import read_yaml, write_yaml, project_path  # noqa: E402

# 同目录可导入 render_variants（逐平台发布包）
sys.path.insert(0, str(Path(__file__).resolve().parent))
import render_variants  # noqa: E402


def _load_meta(project: str | Path) -> dict[str, Any]:
    pj = project_path(project, "project.yaml")
    return read_yaml(pj) if pj.exists() else {}


def build_automation(project: str | Path, *,
                     platforms: list[str] | None = None) -> dict[str, Any]:
    """批量产多平台发布物料 + 统一元数据 + 一键清单（半自动）。"""
    meta = _load_meta(project)
    title = meta.get("title", "未命名")
    platforms = platforms or meta.get("target_platform") or ["douyin"]

    # 复用 render_variants 逐平台产包
    pkg_result = render_variants.build_package(project, platforms=platforms)
    pkg_by_plat = {p["platform"]: p for p in pkg_result["packages"]}

    entries: list[dict[str, Any]] = []
    for plat in platforms:
        pkg = pkg_by_plat.get(plat, {})
        entries.append({
            "platform": plat,
            "primary_aspect": render_variants.PLATFORM_ASPECT.get(plat, "16:9"),
            "package_dir": pkg.get("dir", ""),
            "aigc_obligation": render_variants.PLATFORM_AIGC.get(
                plat, "按平台规则标注 AIGC 生成内容。"),
            "aigc_declared": True,
            "publish_action": "manual",  # 半自动：不代发
            "status": "ready",
        })

    automation = {
        "semi_automatic": True,
        "calls_platform_api": False,
        "title": title,
        "generated_at": datetime.date.today().isoformat(),
        "platform_count": len(entries),
        "platforms": entries,
    }
    out_dir = project_path(project, "09_publish")
    out_dir.mkdir(parents=True, exist_ok=True)
    write_yaml(out_dir / "publish-automation.yaml", automation)
    (out_dir / "publish-checklist.md").write_text(
        render_checklist_md(automation), encoding="utf-8")
    automation["checklist"] = str(out_dir / "publish-checklist.md")
    automation["manifest"] = str(out_dir / "publish-automation.yaml")
    return automation


def render_checklist_md(automation: dict[str, Any]) -> str:
    lines = [f"# 一键发布清单 · 《{automation['title']}》", "",
             "> Q-8 半自动 · **不代发**：逐平台人工执行，发布为不可逆动作，须经 G9 导演终确认。",
             f"> 生成于 {automation['generated_at']}，共 {automation['platform_count']} 个平台。", ""]
    for e in automation["platforms"]:
        lines += [f"## {e['platform']}（主画幅 {e['primary_aspect']}）", "",
                  f"- [ ] 取用发布包：`{e['package_dir']}`",
                  f"- [ ] 完成 AIGC 标注：{e['aigc_obligation']}",
                  "- [ ] 校验封面 / 标题 / 标签（见包内 metadata.yaml）",
                  "- [ ] 导演 G9 终确认后人工发布（脚本不代发）", ""]
    return "\n".join(lines) + "\n"


def generate(project: str | Path, *,
             platforms: list[str] | None = None) -> dict[str, Any]:
    automation = build_automation(project, platforms=platforms)
    return {"manifest": automation["manifest"], "checklist": automation["checklist"],
            "platform_count": automation["platform_count"],
            "platforms": [e["platform"] for e in automation["platforms"]]}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="多平台发布自动化（Q-8，半自动·不代发）")
    parser.add_argument("--project", required=True)
    parser.add_argument("--platforms", nargs="+", help="目标平台（缺省读 project.yaml）")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    result = generate(args.project, platforms=args.platforms)
    if args.json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        print(f"多平台发布物料（{result['platform_count']} 平台：{'、'.join(result['platforms'])}）")
        print(f"  一键清单 -> {result['checklist']}")
        print(f"  汇总     -> {result['manifest']}")
        print("  注：半自动·不代发，逐平台人工发布并经 G9 终确认。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
