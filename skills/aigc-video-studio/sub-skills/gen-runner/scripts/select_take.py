#!/usr/bin/env python3
"""选片决议（设计稿 §5 SK6 / §7.2，P1）。

G6 选片是强制人工审美 Gate——本脚本只**落实**人已做出的选择（确定性写入），
不替导演做判断：
- 在 takes.yaml 写 selected_take + 该 take.status=selected
- 更新 shotlist.yaml 对应镜头 status（默认 selected；终渲后由调用方置 locked）
- git 自动 commit

护栏：被选中的 take 不得是 VLM auto_reject 的废片（防误选）。

单写者注记：takes.yaml 写者为 ingest/vlm_screen；选片决议是 SK6 的收尾写入，
此处对 takes.yaml 仅写 selected_take 与所选 take 状态（窄写），shotlist.yaml 由 SK6 维护。

CLI：
  python select_take.py --project <dir> --shot SHOT-07 --take SHOT-07-t05 [--no-git] [--json]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str((Path(__file__).resolve().parent.parent.parent
                        / "_shared" / "scripts")))
from _common import read_yaml, write_yaml, project_path, ensure_validate_importable  # noqa: E402

ensure_validate_importable()
from validate import validate_obj  # noqa: E402


def _git_commit(project: str | Path, message: str) -> str | None:
    proj = Path(project)
    try:
        subprocess.run(["git", "add", "-A"], cwd=proj, check=True, capture_output=True)
        r = subprocess.run(["git", "commit", "-m", message], cwd=proj,
                           capture_output=True, text=True)
        if r.returncode != 0:
            return None
        h = subprocess.run(["git", "rev-parse", "HEAD"], cwd=proj,
                           check=True, capture_output=True, text=True)
        return h.stdout.strip()
    except (FileNotFoundError, subprocess.CalledProcessError):
        return None


def select_take(project: str | Path, shot_id: str, take_id: str, *,
                shot_status: str = "selected", do_git: bool = True) -> dict[str, Any]:
    """落实选片。返回结果摘要。"""
    shot_dir = project_path(project, "06_generations", shot_id)
    takes_path = shot_dir / "takes.yaml"
    takelog = read_yaml(takes_path)

    take = next((t for t in takelog.get("takes", []) if t.get("take_id") == take_id), None)
    if take is None:
        raise ValueError(f"未找到 take：{take_id}（镜头 {shot_id}）")

    verdict = (take.get("scores", {}).get("agent_vlm", {}) or {}).get("verdict")
    if verdict == "auto_reject":
        raise ValueError(f"{take_id} 已被 VLM auto_reject，不可选为定版")

    takelog["selected_take"] = take_id
    take["status"] = "selected"
    validate_obj(takelog, "C9")
    write_yaml(takes_path, takelog)

    # 更新 shotlist.yaml 该镜状态（若存在）
    shotlist_path = project_path(project, "04_storyboard", "shotlist.yaml")
    shotlist_updated = False
    if shotlist_path.exists():
        shotlist = read_yaml(shotlist_path)
        for shot in shotlist.get("shots", []):
            if shot.get("shot_id") == shot_id:
                shot["status"] = shot_status
                shotlist_updated = True
                break
        if shotlist_updated:
            validate_obj(shotlist, "C5")
            write_yaml(shotlist_path, shotlist)

    commit = _git_commit(project, f"feat(select): {shot_id} 选定 {take_id}") if do_git else None

    return {
        "shot_id": shot_id,
        "selected_take": take_id,
        "shotlist_updated": shotlist_updated,
        "shot_status": shot_status if shotlist_updated else None,
        "commit": commit,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="选片决议 + 更新 shotlist + git commit（SK6）")
    parser.add_argument("--project", required=True)
    parser.add_argument("--shot", required=True)
    parser.add_argument("--take", required=True)
    parser.add_argument("--shot-status", default="selected",
                        help="写回 shotlist 的该镜 status（终渲完成可传 locked）")
    parser.add_argument("--no-git", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    result = select_take(args.project, args.shot, args.take,
                        shot_status=args.shot_status, do_git=not args.no_git)

    if args.json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        print(f"{result['shot_id']} 选定 {result['selected_take']}"
              f"（shotlist {'已更新' if result['shotlist_updated'] else '未更新'}, "
              f"commit={result['commit'] or '跳过'}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
