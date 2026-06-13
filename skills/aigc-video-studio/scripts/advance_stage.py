#!/usr/bin/env python3
"""状态推进（设计稿 §5 SK0 / §7.1 状态机 / §4 单写者矩阵，P1）。

职责（project.yaml 状态段的唯一写者）：
- 校验当前 stage 产物齐备（按 STAGE_ARTIFACTS）+ 关卡 Gate 已 passed 才推进
- 推进后落版本快照到 project.yaml.versions[]
- 状态变更追写 ledger/events.jsonl（事件源 type=stage_advance，单写者）
- git 自动 commit（git 不可用则跳过、不阻断）

设计纪律：
- 校验失败不得推进，并给出缺失产物/未过 Gate 的修复指引。
- 凭证绝不入仓；本脚本不读任何凭证。

CLI：
  python advance_stage.py --project <dir> [--json]
  python advance_stage.py --project <dir> --to S6_GENERATION [--force] [--no-git] [--json]
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

# 本脚本在 scripts/，需定位 _shared/scripts
SHARED_SCRIPTS = (Path(__file__).resolve().parent.parent
                  / "sub-skills" / "_shared" / "scripts")
sys.path.insert(0, str(SHARED_SCRIPTS))
from _common import read_yaml, write_yaml, project_path, ensure_validate_importable  # noqa: E402
import ledger as _ledger  # noqa: E402

ensure_validate_importable()
from validate import validate_obj  # noqa: E402

# 状态机线性顺序（设计稿 §7.1）
STAGE_ORDER = [
    "S0_IDEA", "S1_BRIEF", "S2_SCRIPT", "S3_CHARACTER", "S4_STORYBOARD",
    "S5_PROMPTS", "S6_GENERATION", "S7_AUDIO_POST", "S8_EDIT", "S9_PUBLISH", "DONE",
]

# 推进“到达某 stage”前，当前 stage 应齐备的产物（相对项目目录的存在性检查）。
# 用 glob 片段：任一匹配即视为存在。
STAGE_ARTIFACTS: dict[str, list[str]] = {
    "S1_BRIEF": ["01_brief/brief.md"],
    "S2_SCRIPT": ["02_screenplay/screenplay.md"],
    "S3_CHARACTER": ["03_characters/*/card.yaml"],
    "S4_STORYBOARD": ["04_storyboard/shotlist.yaml"],
    "S5_PROMPTS": ["05_prompts/genspecs/*.yaml"],
    "S6_GENERATION": ["06_generations/*/takes.yaml"],
    "S7_AUDIO_POST": ["07_audio/audio-plan.md"],
    "S8_EDIT": ["08_edit/edl.md"],
    "S9_PUBLISH": ["09_publish/**/*"],
}

# 推进到某 stage 前，必须 passed 的强制人工 Gate（设计稿 §7.1：G3/G6 永不自动；
# G8 完整性终审 / G9 发布确认 同为强制人工，发布不可逆）。
STAGE_REQUIRED_GATE: dict[str, str] = {
    "S4_STORYBOARD": "G3_character",   # 离开 S3 进 S4 需角色定稿
    "S7_AUDIO_POST": "G6_select",      # 离开 S6 进 S7 需选片通过
    "S9_PUBLISH": "G8_integrity",      # 离开 S8 进 S9 需完整性终审通过
    "DONE": "G9_publish",              # 离开 S9 进 DONE 需发布确认（不可逆）
}

# 可配置 Gate（设计稿 §7.1：G7 音画合成确认，默认自动）。
# 语义：默认 AUTO，不阻断；仅当显式 status=rejected 才拦截（如人工/premium 否决）。
# 缺省（gate 不存在或 pending）视为自动放行。
STAGE_AUTO_GATE: dict[str, str] = {
    "S8_EDIT": "G7_audio",             # 离开 S7 进 S8：音画合成确认，默认自动
}


def _now_iso() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def next_stage(current: str) -> str:
    """返回 current 的下一 stage；已是终态则抛错。"""
    if current not in STAGE_ORDER:
        raise ValueError(f"未知 stage：{current}（合法：{STAGE_ORDER}）")
    idx = STAGE_ORDER.index(current)
    if idx >= len(STAGE_ORDER) - 1:
        raise ValueError(f"已处于终态 {current}，无法继续推进")
    return STAGE_ORDER[idx + 1]


def _artifacts_present(project: str | Path, stage: str) -> list[str]:
    """返回 stage 缺失的产物 glob（空列表表示齐备）。"""
    missing = []
    root = Path(project)
    for pattern in STAGE_ARTIFACTS.get(stage, []):
        if not any(root.glob(pattern)):
            missing.append(pattern)
    return missing


def check_can_advance(project: str | Path, current: str, target: str) -> dict[str, Any]:
    """校验从 current 推进到 target 的前置条件。返回 {ok, missing_artifacts, gate}。"""
    proj = read_yaml(project_path(project, "project.yaml"))
    missing = _artifacts_present(project, current)

    gates = proj.get("gates") or {}

    gate_name = STAGE_REQUIRED_GATE.get(target)
    gate_ok = True
    gate_status = None
    if gate_name:
        gate = gates.get(gate_name, {})
        gate_status = gate.get("status")
        gate_ok = gate_status == "passed"

    # 可配置 Gate（G7）：默认自动放行，仅显式 rejected 拦截。
    auto_gate_name = STAGE_AUTO_GATE.get(target)
    auto_gate_ok = True
    auto_gate_status = None
    if auto_gate_name:
        auto_gate_status = gates.get(auto_gate_name, {}).get("status")
        auto_gate_ok = auto_gate_status != "rejected"

    return {
        "ok": not missing and gate_ok and auto_gate_ok,
        "current": current,
        "target": target,
        "missing_artifacts": missing,
        "required_gate": gate_name,
        "gate_status": gate_status,
        "gate_ok": gate_ok,
        "auto_gate": auto_gate_name,
        "auto_gate_status": auto_gate_status,
        "auto_gate_ok": auto_gate_ok,
    }


def _git_commit(project: str | Path, message: str) -> str | None:
    """git add -A + commit；返回 commit hash。git 不可用/无变更则返回 None。"""
    proj = Path(project)
    try:
        subprocess.run(["git", "add", "-A"], cwd=proj, check=True, capture_output=True)
        r = subprocess.run(["git", "commit", "-m", message], cwd=proj,
                           capture_output=True, text=True)
        if r.returncode != 0:
            return None  # 无变更或未配置身份等，不阻断
        h = subprocess.run(["git", "rev-parse", "HEAD"], cwd=proj,
                           check=True, capture_output=True, text=True)
        return h.stdout.strip()
    except (FileNotFoundError, subprocess.CalledProcessError):
        return None


def advance(project: str | Path, *, to: str | None = None, force: bool = False,
            do_git: bool = True) -> dict[str, Any]:
    """推进项目 stage。返回结果摘要。

    force=True 跳过产物/Gate 校验（用于人工干预），但仍落快照与事件。
    """
    proj_path = project_path(project, "project.yaml")
    proj = read_yaml(proj_path)
    current = proj["stage"]
    target = to or next_stage(current)

    check = check_can_advance(project, current, target)
    if not check["ok"] and not force:
        hints = []
        if check["missing_artifacts"]:
            hints.append(f"当前 stage {current} 缺产物：{check['missing_artifacts']}")
        if not check["gate_ok"]:
            hints.append(f"推进到 {target} 需 Gate {check['required_gate']} "
                         f"passed（当前：{check['gate_status']}）")
        if not check.get("auto_gate_ok", True):
            hints.append(f"推进到 {target} 的可配置 Gate {check['auto_gate']} "
                         f"被否决（rejected），需复核音画合成")
        return {"advanced": False, "current": current, "target": target,
                "check": check, "hints": hints}

    # 落版本快照（设计稿 §5 SK0 ⑤）
    snapshot = {
        "v": len(proj.get("versions", [])) + 1,
        "stage_from": current,
        "stage_to": target,
        "at": _now_iso(),
        "forced": force,
    }
    proj.setdefault("versions", []).append(snapshot)
    proj["stage"] = target

    # project.yaml 写前校验 C1（本脚本是状态段唯一写者）
    validate_obj(proj, "C1")
    write_yaml(proj_path, proj)

    # 状态变更追写事件源（单写者矩阵：stage_advance 不计费）
    _ledger.append_event(project, {
        "type": "stage_advance",
        "note": f"{current} -> {target}" + ("（force）" if force else ""),
    })

    commit = _git_commit(project, f"chore(stage): {current} -> {target}") if do_git else None

    return {
        "advanced": True,
        "current": current,
        "target": target,
        "version": snapshot["v"],
        "commit": commit,
        "check": check,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="状态推进 + Gate 校验 + 版本快照 + 自动 commit（SK0）")
    parser.add_argument("--project", required=True)
    parser.add_argument("--to", help="目标 stage（缺省推进到下一 stage）")
    parser.add_argument("--force", action="store_true", help="跳过产物/Gate 校验（人工干预）")
    parser.add_argument("--no-git", action="store_true", help="跳过 git commit")
    parser.add_argument("--check-only", action="store_true", help="仅校验不推进")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    if args.check_only:
        proj = read_yaml(project_path(args.project, "project.yaml"))
        current = proj["stage"]
        target = args.to or next_stage(current)
        result: Any = check_can_advance(args.project, current, target)
    else:
        result = advance(args.project, to=args.to, force=args.force,
                         do_git=not args.no_git)

    if args.json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        if args.check_only:
            print(f"可推进：{result['ok']}（{result['current']} -> {result['target']}）")
            if result["missing_artifacts"]:
                print(f"  缺产物：{result['missing_artifacts']}")
            if not result["gate_ok"]:
                print(f"  需 Gate {result['required_gate']}={result['gate_status']}")
        elif result["advanced"]:
            print(f"已推进：{result['current']} -> {result['target']} "
                  f"(v{result['version']}, commit={result['commit'] or '跳过'})")
        else:
            print(f"未推进：{result['current']} -> {result['target']}")
            for h in result["hints"]:
                print(f"  - {h}")

    # 退出码：推进失败 / 校验不通过 → 1
    if args.check_only:
        return 0 if result["ok"] else 1
    return 0 if result["advanced"] else 1


if __name__ == "__main__":
    sys.exit(main())
