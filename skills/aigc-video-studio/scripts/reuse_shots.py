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

D-6 资产复用索引深化（asset-index.yaml）：在镜头复用之外扩展为「带标签的资产索引」，
统一登记空镜/转场/角色变体（character_variant）等可复用资产，每条含
  asset_id / kind / tags / source（来源说明）/ file / hash（内容指纹，去重）/
  reuse_scope（project|series|global，可复用范围）。
查询同样按标签交集打分，附 kind / scope 过滤。媒体实体不入仓，走 media-manifest。

确定性：reuse_id/asset_id 顺序派生；hash 由 file+tags 派生；查询为标签交集打分，可复现、不触网。

CLI：
  python reuse_shots.py --project <dir> register --kind empty --tags 沙暴,黄昏 \
      --episode ep-01 --shot SHOT-03 --file path.mp4 --duration 4 [--json]
  python reuse_shots.py --project <dir> query --tags 沙暴,加油站 [--kind empty] [--top 3] [--json]
  python reuse_shots.py --project <dir> list [--json]
  # D-6 资产索引：
  python reuse_shots.py --project <dir> register-asset --kind character_variant \
      --tags 锈牛仔,蒙尘 --source ep-02 --file path.png --scope series [--json]
  python reuse_shots.py --project <dir> query-asset --tags 锈牛仔 [--kind character_variant] \
      [--scope series] [--top 3] [--json]
  python reuse_shots.py --project <dir> list-asset [--json]
"""
from __future__ import annotations

import argparse
import hashlib
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

# D-6 资产索引（在镜头复用之外，统一带标签资产库）
ASSET_INDEX_REL = "asset-index.yaml"
ASSET_KINDS = ("empty", "transition", "stock", "character_variant")
REUSE_SCOPES = ("project", "series", "global")


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


# ============================ D-6 资产复用索引深化 ============================
def _asset_index_path(project: str | Path) -> Path:
    return project_path(project, ASSET_INDEX_REL)


def load_asset_index(project: str | Path) -> dict[str, Any]:
    p = _asset_index_path(project)
    if p.exists():
        data = read_yaml(p) or {}
        data.setdefault("assets", [])
        return data
    return {"assets": []}


def _next_asset_id(items: list[dict[str, Any]]) -> str:
    nums = [int(i["asset_id"].split("-")[1]) for i in items
            if i.get("asset_id", "").startswith("AST-")]
    return f"AST-{(max(nums) + 1 if nums else 1):03d}"


def _content_hash(file: str, tags: list[str]) -> str:
    """内容指纹：由文件相对路径 + 标签派生（确定性占位，真实场景换文件 sha256）。"""
    basis = file + "|" + ",".join(sorted(tags))
    return "sha-" + hashlib.sha256(basis.encode("utf-8")).hexdigest()[:16]


def register_asset(project: str | Path, *, kind: str, tags: list[str],
                   source: str, file: str,
                   reuse_scope: str = "project") -> dict[str, Any]:
    """登记一条可复用资产（空镜/转场/资料/角色变体）。同 hash 视为已存在，去重返回原条目。"""
    if kind not in ASSET_KINDS:
        raise ValueError(f"kind 须为 {ASSET_KINDS} 之一")
    if reuse_scope not in REUSE_SCOPES:
        raise ValueError(f"reuse_scope 须为 {REUSE_SCOPES} 之一")
    index = load_asset_index(project)
    items = index["assets"]
    h = _content_hash(file, tags)
    existing = next((a for a in items if a.get("hash") == h), None)
    if existing:
        return existing
    entry = {
        "asset_id": _next_asset_id(items),
        "kind": kind,
        "tags": tags,
        "source": source,
        "file": file,
        "hash": h,
        "reuse_scope": reuse_scope,
    }
    items.append(entry)
    write_yaml(_asset_index_path(project), index)
    return entry


def query_assets(project: str | Path, *, tags: list[str], kind: str | None = None,
                 scope: str | None = None, top: int = 3) -> dict[str, Any]:
    """按标签交集打分检索资产，可选 kind / reuse_scope 过滤。"""
    index = load_asset_index(project)
    want = set(tags)
    scored = []
    for item in index["assets"]:
        if kind and item.get("kind") != kind:
            continue
        if scope and item.get("reuse_scope") != scope:
            continue
        overlap = want & set(item.get("tags", []))
        if not overlap:
            continue
        scored.append({**item, "match_score": len(overlap),
                       "matched_tags": sorted(overlap)})
    scored.sort(key=lambda x: (-x["match_score"], x["asset_id"]))
    return {"query_tags": tags, "kind": kind, "scope": scope, "top": top,
            "candidates": scored[:top], "total_matched": len(scored)}


def list_assets(project: str | Path) -> list[dict[str, Any]]:
    return load_asset_index(project)["assets"]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="复用镜头库 + 资产索引（SK0，剧集量产 V2 / D-6）")
    parser.add_argument("--project", required=True)
    parser.add_argument("action", choices=["register", "query", "list",
                                           "register-asset", "query-asset", "list-asset"])
    parser.add_argument("--kind")
    parser.add_argument("--tags", help="逗号分隔标签")
    parser.add_argument("--episode")
    parser.add_argument("--shot")
    parser.add_argument("--source", help="资产来源说明（register-asset）")
    parser.add_argument("--scope", choices=list(REUSE_SCOPES), help="资产可复用范围")
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
        out = register(args.project, kind=args.kind, tags=tags,
                       episode=args.episode, shot=args.shot,
                       file=args.file, duration_s=args.duration)
    elif args.action == "query":
        out = query(args.project, tags=tags, kind=args.kind, top=args.top)
    elif args.action == "list":
        out = {"reusable": list_all(args.project)}
    elif args.action == "register-asset":
        for req in ("kind", "source", "file"):
            if not getattr(args, req):
                parser.error(f"register-asset 需 --{req}")
        out = register_asset(args.project, kind=args.kind, tags=tags,
                             source=args.source, file=args.file,
                             reuse_scope=args.scope or "project")
    elif args.action == "query-asset":
        out = query_assets(args.project, tags=tags, kind=args.kind,
                           scope=args.scope, top=args.top)
    else:  # list-asset
        out = {"assets": list_assets(args.project)}

    if args.json:
        print(json.dumps(out, ensure_ascii=False))
    else:
        print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
