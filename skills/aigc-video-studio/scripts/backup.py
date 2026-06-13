#!/usr/bin/env python3
"""关键资产定期备份/灾备清单（设计稿 §5 SK0，S-P2，P2 轻量实现）。

职责（轻量）：扫描项目内“关键文本态资产”（契约 + 媒体清单），生成备份清单
manifest（含相对路径 + sha256 + 字节数），供外部同步工具（rsync/对象存储）使用。
媒体实体不由 Git 托管——本脚本只对清单内文件做哈希索引（与 media-manifest 同源理念）。

确定性：哈希与清单顺序稳定可复现。本脚本不写状态文件、不删任何文件。

CLI：
  python backup.py --project <dir> [--out ledger/backup-manifest.yaml] [--json]
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

SHARED_SCRIPTS = (Path(__file__).resolve().parent.parent
                  / "sub-skills" / "_shared" / "scripts")
sys.path.insert(0, str(SHARED_SCRIPTS))
from _common import write_yaml, project_path  # noqa: E402

# 关键资产 glob（文本契约优先；媒体由 media-manifest 单独索引）
ASSET_GLOBS = [
    "project.yaml", "media-manifest.yaml",
    "01_brief/*.md", "02_screenplay/**/*.md",
    "03_characters/**/*.yaml", "04_storyboard/*.yaml",
    "05_prompts/**/*.yaml", "05_prompts/**/*.json",
    "06_generations/**/takes.yaml", "ledger/events.jsonl", "ledger/summary.yaml",
    "08_edit/*.md", "09_publish/**/*.md",
]


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def build_manifest(project: str | Path) -> dict[str, Any]:
    """扫描关键资产，返回备份清单 dict。"""
    root = Path(project)
    seen: set[str] = set()
    entries: list[dict[str, Any]] = []
    for pattern in ASSET_GLOBS:
        for f in sorted(root.glob(pattern)):
            if not f.is_file():
                continue
            rel = str(f.relative_to(root))
            if rel in seen:
                continue
            seen.add(rel)
            entries.append({"path": rel, "sha256": _sha256(f),
                            "bytes": f.stat().st_size})
    return {
        "generated_at": _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "asset_count": len(entries),
        "total_bytes": sum(e["bytes"] for e in entries),
        "assets": entries,
    }


def backup(project: str | Path, *, out: str | Path | None = None) -> dict[str, Any]:
    manifest = build_manifest(project)
    out_path = Path(out) if out else project_path(project, "ledger", "backup-manifest.yaml")
    write_yaml(out_path, manifest)
    manifest["manifest_path"] = str(out_path)
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="关键资产备份清单（SK0，P2）")
    parser.add_argument("--project", required=True)
    parser.add_argument("--out", help="清单输出路径（缺省 ledger/backup-manifest.yaml）")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    manifest = backup(args.project, out=args.out)
    if args.json:
        print(json.dumps(manifest, ensure_ascii=False))
    else:
        print(f"备份清单 {manifest['asset_count']} 项 / {manifest['total_bytes']} 字节 "
              f"-> {manifest['manifest_path']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
