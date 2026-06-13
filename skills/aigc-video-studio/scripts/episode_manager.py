#!/usr/bin/env python3
"""剧集管理（设计稿 §7.3 series 档 / §9 V2，SK0）。

剧集模式下 03_characters/、03_style/ 为全剧共享资产；02_screenplay/episodes/ 下
每集一个 ep-NN.md + 每集独立 shotlist 与账本目录，汇总到剧级 dashboard。

职责：
- create：新建一集（ep-NN.md 占位 + episodes/ep-NN/ 独立工作目录 + 写回 project.episodes）
- list：列出全部剧集（读 project.episodes）
- dashboard：汇总各集状态/镜头数/账本，产出剧级 dashboard.md

设计纪律：
- 共享资产单写者：角色/风格在剧级目录唯一来源，各集只读引用，避免跨集漂移。
- 确定性：编号/路径由输入派生，可复现，不触网。
- 写 project.yaml（C1）前必经 validate。

CLI：
  python episode_manager.py --project <dir> create --title "第一集 沙暴" [--json]
  python episode_manager.py --project <dir> list [--json]
  python episode_manager.py --project <dir> dashboard [--json]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

SHARED_SCRIPTS = (Path(__file__).resolve().parent.parent
                  / "sub-skills" / "_shared" / "scripts")
sys.path.insert(0, str(SHARED_SCRIPTS))
from _common import read_yaml, write_yaml, project_path, ensure_validate_importable  # noqa: E402

ensure_validate_importable()
from validate import validate_obj  # noqa: E402

# 每集独立工作目录（剧集内复用单片骨架的关键子目录，角色/风格不在此，全剧共享）
EPISODE_SUBDIRS = [
    "04_storyboard/boards",
    "05_prompts/genspecs",
    "05_prompts/taskcards",
    "06_generations",
    "07_audio",
    "08_edit/master",
    "ledger",
]


def _ensure_series(project: str | Path) -> dict[str, Any]:
    """读 project.yaml 并确认是 series 模式。"""
    proj = read_yaml(project_path(project, "project.yaml"))
    if proj.get("format") != "series":
        raise ValueError("该项目非 series 模式（project.format 须为 series）")
    return proj


def _next_ep_no(episodes: list[dict[str, Any]]) -> int:
    used = {e.get("no") for e in episodes if e.get("no") is not None}
    n = 1
    while n in used:
        n += 1
    return n


def create_episode(project: str | Path, title: str) -> dict[str, Any]:
    """新建一集：ep-NN.md 占位 + 独立工作目录 + 写回 project.episodes。"""
    proj = _ensure_series(project)
    episodes = list(proj.get("episodes") or [])
    no = _next_ep_no(episodes)
    ep_id = f"ep-{no:02d}"

    # ep-NN.md 剧本占位（每集独立剧本，角色/风格走全剧共享）
    ep_md = project_path(project, "02_screenplay", "episodes", f"{ep_id}.md")
    ep_md.parent.mkdir(parents=True, exist_ok=True)
    if not ep_md.exists():
        ep_md.write_text(
            f"# {ep_id} · {title}\n\n"
            f"> 第 {no} 集剧本。角色卡见全剧共享 `03_characters/`，"
            f"风格圣经见 `03_style/`（剧级唯一来源，本集只读引用）。\n\n"
            f"## 剧情梗概\n\n（待写）\n\n## 场景\n\n（待写）\n",
            encoding="utf-8")

    # 每集独立工作目录
    created = []
    for sub in EPISODE_SUBDIRS:
        d = project_path(project, "02_screenplay", "episodes", ep_id, sub)
        d.mkdir(parents=True, exist_ok=True)
        (d / ".gitkeep").touch()
        created.append(sub)

    entry = {"no": no, "id": ep_id, "title": title,
             "screenplay": f"02_screenplay/episodes/{ep_id}.md",
             "workdir": f"02_screenplay/episodes/{ep_id}", "stage": "S2_SCRIPT"}
    episodes.append(entry)
    proj["episodes"] = episodes
    validate_obj(proj, "C1")
    write_yaml(project_path(project, "project.yaml"), proj)
    return {"episode": entry, "subdirs_created": created}


def list_episodes(project: str | Path) -> list[dict[str, Any]]:
    proj = _ensure_series(project)
    return list(proj.get("episodes") or [])


def _episode_shot_count(project: str | Path, ep_id: str) -> int:
    sl = project_path(project, "02_screenplay", "episodes", ep_id,
                      "04_storyboard", "shotlist.yaml")
    if sl.exists():
        return len(read_yaml(sl).get("shots", []) or [])
    return 0


def build_dashboard(project: str | Path) -> dict[str, Any]:
    """汇总各集状态/镜头数到剧级 dashboard。"""
    proj = _ensure_series(project)
    episodes = proj.get("episodes") or []
    rows = []
    for e in episodes:
        rows.append({
            "no": e.get("no"),
            "id": e.get("id"),
            "title": e.get("title"),
            "stage": e.get("stage", "S2_SCRIPT"),
            "shot_count": _episode_shot_count(project, e.get("id", "")),
        })
    return {"series_id": proj.get("id"), "series_title": proj.get("title"),
            "episode_count": len(rows), "episodes": rows}


def render_dashboard_md(dash: dict[str, Any]) -> str:
    lines = [f"# 剧级 Dashboard · {dash['series_title']}（{dash['series_id']}）", "",
             f"剧集数：{dash['episode_count']}", "",
             "| # | 集 | 标题 | 阶段 | 镜头数 |", "|---|---|---|---|---|"]
    for r in dash["episodes"]:
        lines.append(f"| {r['no']} | {r['id']} | {r['title']} "
                     f"| {r['stage']} | {r['shot_count']} |")
    lines += ["", "> 角色/风格为全剧共享资产（剧级唯一来源），各集只读引用，"
              "每集跑跨集漂移检查（cross_episode_drift.py）。"]
    return "\n".join(lines) + "\n"


def generate_dashboard(project: str | Path) -> dict[str, Any]:
    dash = build_dashboard(project)
    out = project_path(project, "dashboard.md")
    out.write_text(render_dashboard_md(dash), encoding="utf-8")
    return {"out": str(out), "episode_count": dash["episode_count"]}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="剧集管理（SK0，剧集量产 V2）")
    parser.add_argument("--project", required=True)
    parser.add_argument("action", choices=["create", "list", "dashboard"])
    parser.add_argument("--title", help="create 时的集标题")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    if args.action == "create":
        if not args.title:
            parser.error("create 需 --title")
        result = create_episode(args.project, args.title)
        if args.json:
            print(json.dumps(result, ensure_ascii=False))
        else:
            ep = result["episode"]
            print(f"新建剧集 {ep['id']} · {ep['title']}（工作目录 {ep['workdir']}）")
    elif args.action == "list":
        eps = list_episodes(args.project)
        if args.json:
            print(json.dumps(eps, ensure_ascii=False))
        else:
            for e in eps:
                print(f"  {e['id']} · {e['title']}（{e.get('stage')}）")
    else:  # dashboard
        result = generate_dashboard(args.project)
        if args.json:
            print(json.dumps(result, ensure_ascii=False))
        else:
            print(f"剧级 dashboard -> {result['out']}（{result['episode_count']} 集）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
