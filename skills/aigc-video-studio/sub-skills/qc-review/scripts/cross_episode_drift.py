#!/usr/bin/env python3
"""跨集角色一致性漂移检查（设计稿 §7.3 剧集模式 / §9 V2，SK7）。

剧集模式下角色卡为全剧共享资产，但各集独立生成易产生「同角色跨集长相漂移」。
本脚本用 vlm_screen 的确定性 mock 比对各集同角色的代表帧与基线（角色卡），
输出漂移报告：每个共享角色 × 每集一条比对，标 ok/drift，并汇总告警。

确定性：复用 vlm_screen 的 mock 裁决（由 take_id 派生），不触网、可复现。
mock 约定（沿用 vlm_screen）：代表样本 id 含 "fail"→ 判定漂移；含 "weak"→ 待核；
其余 → 一致。真实场景由多模态模型替换 scorer。

CLI：
  python cross_episode_drift.py --project <dir> [--out 08_edit/cross-episode-drift.yaml] [--json]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

SHARED = (Path(__file__).resolve().parent.parent.parent / "_shared" / "scripts")
sys.path.insert(0, str(SHARED))
from _common import read_yaml, write_yaml, project_path  # noqa: E402
import vlm_screen  # noqa: E402


def _shared_character_ids(project: str | Path) -> list[str]:
    """全剧共享角色（03_characters/<id>/card.yaml）。"""
    chars_dir = project_path(project, "03_characters")
    ids: list[str] = []
    if chars_dir.exists():
        for card in sorted(chars_dir.glob("*/card.yaml")):
            ids.append(read_yaml(card).get("id") or card.parent.name)
    return ids


def _episodes(project: str | Path) -> list[dict[str, Any]]:
    proj = read_yaml(project_path(project, "project.yaml"))
    return proj.get("episodes") or []


def _episode_character_sample(project: str | Path, ep_id: str,
                              char_id: str) -> dict[str, Any] | None:
    """取某集中含该角色的第一镜的代表样本（选定 take 或镜头 id），供 mock 比对。

    优先该集 shotlist 里含该角色的镜头的 selected_take；缺则用镜头 id 作样本占位。
    """
    sl = project_path(project, "02_screenplay", "episodes", ep_id,
                      "04_storyboard", "shotlist.yaml")
    if not sl.exists():
        return None
    for shot in sorted(read_yaml(sl).get("shots", []), key=lambda s: s.get("order", 0)):
        if char_id in (shot.get("characters") or []):
            sid = shot["shot_id"]
            tp = project_path(project, "02_screenplay", "episodes", ep_id,
                              "06_generations", sid, "takes.yaml")
            sample_id = f"{ep_id}-{sid}-{char_id}"
            if tp.exists():
                sel = read_yaml(tp).get("selected_take")
                if sel:
                    sample_id = sel
            return {"shot_id": sid, "sample_id": sample_id}
    return None


def check_drift(project: str | Path) -> dict[str, Any]:
    """对全剧共享角色逐集跑一致性比对。"""
    config = vlm_screen._vlm_config()
    chars = _shared_character_ids(project)
    episodes = _episodes(project)

    comparisons: list[dict[str, Any]] = []
    drift_chars: set[str] = set()
    for cid in chars:
        for ep in episodes:
            ep_id = ep.get("id")
            sample = _episode_character_sample(project, ep_id, cid)
            if sample is None:
                continue
            # 复用 vlm_screen 确定性裁决：把样本当作一条 take 跑 identity 比对
            fake_take = {"take_id": sample["sample_id"], "vlm_protocol_hint": "static"}
            agent_vlm = vlm_screen.screen_take(fake_take, config, mock=True)
            consistent = agent_vlm["identity"] == "PASS"
            status = "ok" if consistent else (
                "drift" if agent_vlm["identity"] == "FAIL" else "needs_review")
            if status == "drift":
                drift_chars.add(cid)
            comparisons.append({
                "character": cid,
                "episode": ep_id,
                "shot_id": sample["shot_id"],
                "sample_id": sample["sample_id"],
                "identity": agent_vlm["identity"],
                "confidence": agent_vlm["confidence"],
                "status": status,
            })

    return {
        "characters_checked": chars,
        "episode_count": len(episodes),
        "comparisons": comparisons,
        "drift_characters": sorted(drift_chars),
        "ok": not drift_chars,
    }


def render_md(report: dict[str, Any]) -> str:
    lines = ["# 跨集角色一致性漂移报告", "",
             f"共享角色：{', '.join(report['characters_checked']) or '（无）'}",
             f"剧集数：{report['episode_count']}", "",
             "| 角色 | 集 | 镜头 | 样本 | 一致性 | 置信 | 结论 |",
             "|---|---|---|---|---|---|---|"]
    for c in report["comparisons"]:
        lines.append(f"| {c['character']} | {c['episode']} | {c['shot_id']} "
                     f"| {c['sample_id']} | {c['identity']} | {c['confidence']} | {c['status']} |")
    lines.append("")
    if report["drift_characters"]:
        lines.append(f"> ⚠ 检出跨集漂移角色：{', '.join(report['drift_characters'])}，"
                     f"建议回基线角色卡重锁 identity_strategy 或登记 variant。")
    else:
        lines.append("> 未检出跨集漂移。")
    return "\n".join(lines) + "\n"


def generate(project: str | Path, *, out: str | Path | None = None) -> dict[str, Any]:
    report = check_drift(project)
    out_path = Path(out) if out else project_path(project, "08_edit", "cross-episode-drift.yaml")
    write_yaml(out_path, report)
    md_path = out_path.with_suffix(".md")
    md_path.write_text(render_md(report), encoding="utf-8")
    return {"out": str(out_path), "md_out": str(md_path),
            "comparison_count": len(report["comparisons"]),
            "drift_characters": report["drift_characters"], "ok": report["ok"]}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="跨集角色漂移检查（SK7，剧集量产 V2）")
    parser.add_argument("--project", required=True)
    parser.add_argument("--out")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    result = generate(args.project, out=args.out)
    if args.json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        print(f"跨集比对 {result['comparison_count']} 条 -> {result['out']}")
        if result["drift_characters"]:
            print(f"  ⚠ 漂移角色：{result['drift_characters']}")
        else:
            print("  无漂移")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
