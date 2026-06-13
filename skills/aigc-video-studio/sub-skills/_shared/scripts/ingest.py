#!/usr/bin/env python3
"""inbox 回收（设计稿 §5 SK6 回收流程，S-P2-7 _unmatched 容错）。

流程：
- 扫 06_generations/SHOT-xx/inbox/
- 文件名解析为 SHOT-xx-tNN[_seed<seed>].<ext> 规范命名，移入 takes/
- 写 TakeLog（takes.yaml，C9，含 pass/seed/channel）
- 记账（追写 ledger events.jsonl）
- 无法匹配的文件移入 _unmatched/（不阻断）
- 幂等：同一来源文件（按内容 hash）重复 ingest 不重复登记

文件名匹配规则（宽松，覆盖人工/adapter 两类产物）：
  SHOT-07-t03.mp4
  SHOT-07-t03_seed12345.mp4
  SHOT-07-t3.mov          -> 归一为 t03
  shot-07_t03.mp4         -> 大小写/分隔符宽松
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import read_yaml, write_yaml, project_path, ensure_validate_importable  # noqa: E402
import ledger as _ledger  # noqa: E402

ensure_validate_importable()
from validate import validate_obj  # noqa: E402

# 宽松匹配：SHOT-<num>-t<num>[_seed<num>]
NAME_RE = re.compile(
    r"^shot[-_]?(?P<shot>\d+)[-_]?t(?P<take>\d+)(?:[-_]?seed(?P<seed>\d+))?$",
    re.IGNORECASE,
)


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def parse_name(stem: str) -> dict[str, Any] | None:
    m = NAME_RE.match(stem)
    if not m:
        return None
    shot = f"SHOT-{int(m.group('shot')):02d}"
    take = f"t{int(m.group('take')):02d}"
    seed = int(m.group("seed")) if m.group("seed") else None
    return {"shot_id": shot, "take_num": take, "seed": seed}


def _takelog_path(shot_dir: Path) -> Path:
    return shot_dir / "takes.yaml"


def _load_takelog(shot_dir: Path, shot_id: str) -> dict[str, Any]:
    path = _takelog_path(shot_dir)
    if path.exists():
        return read_yaml(path)
    return {"shot_id": shot_id, "takes": [], "selected_take": None, "rerun_history": []}


def ingest_shot(project: str | Path, shot_id: str, *, pass_: str = "draft",
                channel: str = "api", model_version: str = "seedance-2.0",
                cost_cny: float = 0.0) -> dict[str, Any]:
    """回收单个镜头的 inbox。返回结果摘要。"""
    shot_dir = project_path(project, "06_generations", shot_id)
    inbox = shot_dir / "inbox"
    takes_dir = shot_dir / "takes"
    unmatched = shot_dir / "_unmatched"
    takes_dir.mkdir(parents=True, exist_ok=True)

    result = {"shot_id": shot_id, "ingested": [], "unmatched": [], "skipped": []}
    if not inbox.exists():
        return result

    takelog = _load_takelog(shot_dir, shot_id)
    # 已登记的来源 hash（幂等键）
    known_hashes = {t.get("source_hash") for t in takelog["takes"] if t.get("source_hash")}

    for f in sorted(inbox.iterdir()):
        if not f.is_file():
            continue
        parsed = parse_name(f.stem)
        if parsed is None:
            # 无法匹配 → _unmatched/，不阻断
            unmatched.mkdir(parents=True, exist_ok=True)
            dest = unmatched / f.name
            if not dest.exists():
                f.rename(dest)
            result["unmatched"].append(f.name)
            continue

        file_hash = _sha256(f)
        if file_hash in known_hashes:
            # 幂等：内容已登记，删除 inbox 中的重复副本
            f.unlink()
            result["skipped"].append(f.name)
            continue

        # 规范命名
        seed = parsed["seed"]
        seed_part = f"_seed{seed}" if seed is not None else ""
        new_name = f"{parsed['shot_id']}-{parsed['take_num']}{seed_part}{f.suffix}"
        dest = takes_dir / new_name
        # 若目标已存在但内容不同（极少见），加去重后缀
        if dest.exists() and _sha256(dest) != file_hash:
            dest = takes_dir / f"{parsed['shot_id']}-{parsed['take_num']}{seed_part}-{file_hash[:6]}{f.suffix}"
        f.rename(dest)

        take_id = f"{parsed['shot_id']}-{parsed['take_num']}"
        take_entry = {
            "take_id": take_id,
            "pass": pass_,
            "file": f"takes/{dest.name}",
            "channel": channel,
            "source_hash": file_hash,
            "platform_meta": {
                "seed": seed,
                "model_version": model_version,
            },
            "scores": {},
            "rejected_reason": None,
            "status": "ingested",
        }
        takelog["takes"].append(take_entry)
        known_hashes.add(file_hash)
        result["ingested"].append(dest.name)

        # 记账（事件源，幂等）
        _ledger.append_event(project, {
            "event_id": f"take-{shot_id}-{file_hash[:12]}",
            "type": "take_cost",
            "shot_id": shot_id,
            "pass": pass_,
            "channel": channel,
            "cny": cost_cny,
            "note": f"ingest {dest.name}",
        })

    # 写 TakeLog（写前校验 C9）—— 仅当为该 schema 必填字段精简
    _validate_takelog(takelog)
    write_yaml(_takelog_path(shot_dir), takelog)
    return result


def _validate_takelog(takelog: dict[str, Any]) -> None:
    # source_hash 是内部幂等字段，C9 允许 additionalProperties，故可保留
    validate_obj(takelog, "C9")


def ingest_all(project: str | Path, **kwargs) -> list[dict[str, Any]]:
    """遍历所有 SHOT-xx 目录回收。"""
    gen_dir = project_path(project, "06_generations")
    results = []
    if not gen_dir.exists():
        return results
    for shot_dir in sorted(gen_dir.iterdir()):
        if shot_dir.is_dir() and shot_dir.name.startswith("SHOT-"):
            results.append(ingest_shot(project, shot_dir.name, **kwargs))
    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="inbox 回收（ingest）")
    parser.add_argument("--project", required=True)
    parser.add_argument("--shot", help="只回收指定镜头；缺省回收全部")
    parser.add_argument("--pass", dest="pass_", default="draft", choices=["draft", "final"])
    parser.add_argument("--channel", default="api", choices=["api", "ui"])
    parser.add_argument("--model-version", default="seedance-2.0")
    parser.add_argument("--cost-cny", type=float, default=0.0)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    kwargs = {"pass_": args.pass_, "channel": args.channel,
              "model_version": args.model_version, "cost_cny": args.cost_cny}
    if args.shot:
        results = [ingest_shot(args.project, args.shot, **kwargs)]
    else:
        results = ingest_all(args.project, **kwargs)

    if args.json:
        print(json.dumps(results, ensure_ascii=False))
    else:
        for r in results:
            print(f"{r['shot_id']}: 回收 {len(r['ingested'])} / 未匹配 {len(r['unmatched'])} "
                  f"/ 跳过 {len(r['skipped'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
