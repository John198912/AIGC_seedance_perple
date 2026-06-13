#!/usr/bin/env python3
"""复用镜头库（设计稿 §7.3 剧集量产 / §9 V2，SK0）。

空镜/转场镜头跨集复用：维护剧级 reuse-shots.yaml 索引（轻量契约），
登记可复用镜头（空镜/转场/资料镜）的选定成片与标签，供后续集查询命中、避免重复抽卡。

索引契约 reuse-shots.yaml：
  reusable:
    - reuse_id: RS-001
      kind: empty|transition|stock     # 空镜/转场/资料
      tags: [沙暴, 黄昏, 加油站]
      source_episode: ep-01
      source_shot: SHOT-03
      file: <选定成片相对路径>
      duration_s: 4

确定性：reuse_id 顺序派生；查询为标签交集打分，可复现、不触网。

CLI：
  python reuse_shots.py --project <dir> register --kind empty --tags 沙暴,黄昏 \
      --episode ep-01 --shot SHOT-03 --file path.mp4 --duration 4 [--json]
  python reuse_shots.py --project <dir> query --tags 沙暴,加油站 [--kind empty] [--top 3] [--json]
  python reuse_shots.py --project <dir> list [--json]
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
from _common import read_yaml, write_yaml, project_path  # noqa: E402

INDEX_REL = "reuse-shots.yaml"
KINDS = ("empty", "transition", "stock")


def _index_path(project: str | Path) -> Path:
    return project_path(project, INDEX_REL)


def load_index(project: str | Path) -> dict[str, Any]:
    p = _index_path(project)
    if p.exists():
        data = read_yaml(p) or {}
        data.setdefault("reusable", [])
        return data
    return {"reusable": []}


def _next_reuse_id(items: list[dict[str, Any]]) -> str:
    nums = [int(i["reuse_id"].split("-")[1]) for i in items
            if i.get("reuse_id", "").startswith("RS-")]
    return f"RS-{(max(nums) + 1 if nums else 1):03d}"


def register(project: str | Path, *, kind: str, tags: list[str],
             episode: str, shot: str, file: str,
             duration_s: float = 0.0) -> dict[str, Any]:
    if kind not in KINDS:
        raise ValueError(f"kind 须为 {KINDS} 之一")
    index = load_index(project)
    items = index["reusable"]
    entry = {
        "reuse_id": _next_reuse_id(items),
        "kind": kind,
        "tags": tags,
        "source_episode": episode,
        "source_shot": shot,
        "file": file,
        "duration_s": duration_s,
    }
    items.append(entry)
    write_yaml(_index_path(project), index)
    return entry


def query(project: str | Path, *, tags: list[str], kind: str | None = None,
          top: int = 3) -> dict[str, Any]:
    """按标签交集打分检索可复用镜头（命中标签越多分越高），可选 kind 过滤。"""
    index = load_index(project)
    want = set(tags)
    scored = []
    for item in index["reusable"]:
        if kind and item.get("kind") != kind:
            continue
        overlap = want & set(item.get("tags", []))
        if not overlap:
            continue
        scored.append({**item, "match_score": len(overlap),
                       "matched_tags": sorted(overlap)})
    scored.sort(key=lambda x: (-x["match_score"], x["reuse_id"]))
    return {"query_tags": tags, "kind": kind, "top": top,
            "candidates": scored[:top], "total_matched": len(scored)}


def list_all(project: str | Path) -> list[dict[str, Any]]:
    return load_index(project)["reusable"]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="复用镜头库（SK0，剧集量产 V2）")
    parser.add_argument("--project", required=True)
    parser.add_argument("action", choices=["register", "query", "list"])
    parser.add_argument("--kind", choices=list(KINDS))
    parser.add_argument("--tags", help="逗号分隔标签")
    parser.add_argument("--episode")
    parser.add_argument("--shot")
    parser.add_argument("--file")
    parser.add_argument("--duration", type=float, default=0.0)
    parser.add_argument("--top", type=int, default=3)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    tags = [t.strip() for t in (args.tags or "").split(",") if t.strip()]

    if args.action == "register":
        for req in ("kind", "episode", "shot", "file"):
            if not getattr(args, req):
                parser.error(f"register 需 --{req}")
        result = register(args.project, kind=args.kind, tags=tags,
                          episode=args.episode, shot=args.shot,
                          file=args.file, duration_s=args.duration)
        out = result
    elif args.action == "query":
        out = query(args.project, tags=tags, kind=args.kind, top=args.top)
    else:
        out = {"reusable": list_all(args.project)}

    if args.json:
        print(json.dumps(out, ensure_ascii=False))
    else:
        print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
