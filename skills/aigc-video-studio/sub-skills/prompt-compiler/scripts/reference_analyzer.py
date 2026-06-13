#!/usr/bin/env python3
"""参考片风格迁移分析器（设计稿 §9 路线图 D-2，半自动·需人工确认）。

输入参考片「元数据 + 人工标注」（mock 视觉分析，不接真实视觉模型，确定性），
提取一组风格描述子（色调/胶片颗粒/光照/构图法/运镜/节奏），
产出 03_style/style-transfer-suggestion.md（人读建议）+ 可并入 style-bible 的结构化片段。

半自动纪律：本脚本只产「建议」，所有描述子均标注「需人工确认」，
不自动写入 style-bible.md（导演择优手工并入），避免把臆测当事实锁死下游。

输入参考片记录（reference_clips.yaml 或 CLI 单条），字段：
  title: 参考片名
  source: 来源说明（链接/影片名，仅文本，不触网）
  annotations:          # 人工标注（自然语言关键词，可缺）
    palette: 低饱和暖黄、青影调
    lighting: 硬光侧逆光、丁达尔
    grain: 35mm 胶片颗粒中等
    composition: 三分法、对角线引导
    camera: 缓慢推轨、手持微晃
    pace: 慢节奏长镜

确定性：描述子由标注关键词按词典确定性归一映射派生，可复现、不触网。

CLI：
  python reference_analyzer.py --project <dir> [--refs 03_style/reference_clips.yaml]
      [--out 03_style/style-transfer-suggestion.md] [--json]
  python reference_analyzer.py --title "银翼杀手2049" --palette "低饱和暖黄,青影调" \
      --lighting "硬光侧逆光" --grain "35mm中等" --json   # 单条 mock
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str((Path(__file__).resolve().parent.parent.parent
                        / "_shared" / "scripts")))
from _common import read_yaml, project_path  # noqa: E402

# 风格维度（顺序即建议展示顺序）；每维 → (中文名, 缺省占位)
DESCRIPTOR_DIMS: list[tuple[str, str, str]] = [
    ("palette", "色调", "（未标注，建议人工补：主色温/饱和度/影调）"),
    ("lighting", "光照", "（未标注，建议人工补：光质/方向/对比）"),
    ("grain", "胶片颗粒", "（未标注，建议人工补：颗粒强度/胶片型号）"),
    ("composition", "构图法", "（未标注，建议人工补：三分/对角/中心/对称）"),
    ("camera", "运镜", "（未标注，建议人工补：推拉摇移/手持/稳定器）"),
    ("pace", "节奏", "（未标注，建议人工补：镜头时长/剪辑频率）"),
]

# 关键词归一映射（mock「视觉分析」：把零散标注词收敛为规范风格描述子）。
# 确定性：纯查表，命中即追加规范化提示词，未命中保留原标注。
NORMALIZE_HINTS: dict[str, dict[str, str]] = {
    "palette": {"暖": "暖色温倾向", "青": "青影调阴影", "低饱和": "低饱和克制",
                "高饱和": "高饱和强烈"},
    "lighting": {"硬光": "硬光高对比", "柔光": "柔光低对比", "逆光": "逆光轮廓",
                 "丁达尔": "体积光丁达尔"},
    "grain": {"35mm": "35mm 胶片质感", "16mm": "16mm 粗颗粒", "中等": "颗粒中等"},
    "composition": {"三分": "三分法构图", "对角": "对角线引导", "中心": "中心构图",
                    "对称": "对称式构图"},
    "camera": {"推": "推轨向前", "拉": "拉远", "手持": "手持微晃", "稳定": "稳定器平滑"},
    "pace": {"慢": "慢节奏长镜", "快": "快剪高频", "长镜": "长镜头调度"},
}


def _normalize(dim: str, raw: str) -> list[str]:
    """把一条标注归一为规范化描述子列表（命中查表追加规范词，保留原词）。"""
    raw = (raw or "").strip()
    if not raw:
        return []
    out: list[str] = []
    hints = NORMALIZE_HINTS.get(dim, {})
    for token in [t.strip() for t in raw.replace("，", ",").split(",") if t.strip()]:
        norm = next((v for k, v in hints.items() if k in token), None)
        out.append(norm or token)
    # 去重保序
    seen: set[str] = set()
    return [x for x in out if not (x in seen or seen.add(x))]


def analyze_clip(clip: dict[str, Any]) -> dict[str, Any]:
    """对单条参考片记录提取风格描述子（半自动）。"""
    ann = clip.get("annotations", {}) or {}
    descriptors: dict[str, Any] = {}
    for key, zh, placeholder in DESCRIPTOR_DIMS:
        norm = _normalize(key, ann.get(key, ""))
        descriptors[key] = {
            "label_zh": zh,
            "values": norm,
            "text": "、".join(norm) if norm else placeholder,
            "confirmed": False,  # 半自动：一律待人工确认
        }
    return {
        "title": clip.get("title", "（未命名参考片）"),
        "source": clip.get("source", ""),
        "descriptors": descriptors,
    }


def analyze(clips: list[dict[str, Any]]) -> dict[str, Any]:
    """批量分析参考片，返回 {clips:[...], style_bible_fragment: {...}}。"""
    analyzed = [analyze_clip(c) for c in clips]
    # 合并所有片的描述子为一份可并入 style-bible 的结构化片段（去重保序）
    fragment: dict[str, list[str]] = {key: [] for key, _, _ in DESCRIPTOR_DIMS}
    for a in analyzed:
        for key in fragment:
            for v in a["descriptors"][key]["values"]:
                if v not in fragment[key]:
                    fragment[key].append(v)
    return {
        "semi_automatic": True,
        "needs_human_confirm": True,
        "clip_count": len(analyzed),
        "clips": analyzed,
        "style_bible_fragment": fragment,
    }


def render_md(result: dict[str, Any]) -> str:
    lines = ["# 参考片风格迁移建议（style-transfer-suggestion）", "",
             "> D-2 半自动 · **需人工确认**：以下描述子由参考片标注经确定性归一派生，",
             "> 仅作 style-bible 候选片段，导演择优手工并入 `03_style/style-bible.md`，",
             "> 脚本不自动写入下游契约（避免把臆测锁死）。", ""]
    for a in result["clips"]:
        lines += [f"## 《{a['title']}》", ""]
        if a["source"]:
            lines.append(f"来源：{a['source']}")
            lines.append("")
        lines += ["| 维度 | 描述子 | 状态 |", "|---|---|---|"]
        for key, zh, _ in DESCRIPTOR_DIMS:
            d = a["descriptors"][key]
            status = "✅ 已确认" if d["confirmed"] else "⚠ 需人工确认"
            lines.append(f"| {zh} | {d['text']} | {status} |")
        lines.append("")

    frag = result["style_bible_fragment"]
    lines += ["## 可并入 style-bible 的合并片段（候选）", "",
              "> 复制确认后的条目到 style-bible.md，未确认项请先核验或删除。", ""]
    for key, zh, _ in DESCRIPTOR_DIMS:
        vals = frag.get(key, [])
        lines.append(f"- **{zh}**：{('、'.join(vals)) if vals else '（待补）'}")
    lines.append("")
    return "\n".join(lines) + "\n"


def load_reference_clips(project: str | Path,
                         refs_path: str | Path | None = None) -> list[dict[str, Any]]:
    """读参考片记录文件（缺省 03_style/reference_clips.yaml）。"""
    path = Path(refs_path) if refs_path else project_path(project, "03_style", "reference_clips.yaml")
    if not path.exists():
        return []
    data = read_yaml(path) or {}
    return data.get("reference_clips", []) or []


def generate(project: str | Path, *, refs_path: str | Path | None = None,
             out: str | Path | None = None) -> dict[str, Any]:
    clips = load_reference_clips(project, refs_path)
    result = analyze(clips)
    out_path = Path(out) if out else project_path(project, "03_style", "style-transfer-suggestion.md")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(render_md(result), encoding="utf-8")
    return {"out": str(out_path), "clip_count": result["clip_count"],
            "needs_human_confirm": True,
            "style_bible_fragment": result["style_bible_fragment"]}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="参考片风格迁移分析（D-2，半自动·需人工确认）")
    parser.add_argument("--project", help="项目目录（读 03_style/reference_clips.yaml）")
    parser.add_argument("--refs", help="参考片记录文件路径")
    parser.add_argument("--out", help="建议输出路径")
    # 单条 mock 标注（无项目时直接分析）
    parser.add_argument("--title")
    parser.add_argument("--source", default="")
    parser.add_argument("--palette", default="")
    parser.add_argument("--lighting", default="")
    parser.add_argument("--grain", default="")
    parser.add_argument("--composition", default="")
    parser.add_argument("--camera", default="")
    parser.add_argument("--pace", default="")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    if args.project and not args.title:
        result = generate(args.project, refs_path=args.refs, out=args.out)
        if args.json:
            print(json.dumps(result, ensure_ascii=False))
        else:
            print(f"参考片风格建议（{result['clip_count']} 条）-> {result['out']}（半自动·需人工确认）")
        return 0

    # 单条 mock 模式
    clip = {"title": args.title or "（未命名参考片）", "source": args.source,
            "annotations": {k: getattr(args, k) for k in
                            ("palette", "lighting", "grain", "composition", "camera", "pace")}}
    result = analyze([clip])
    if args.json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        print(render_md(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
