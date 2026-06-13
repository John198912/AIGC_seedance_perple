#!/usr/bin/env python3
"""初始化项目骨架（设计稿 §3.1 / §5 SK0，S-P0-4 媒体治理）。

职责：
- 建 projects/<slug>/ 文件骨架（§3.1 目录布局）
- 写 project.yaml（契约 C1）并经 validate 校验
- git init（若 git 可用；不可用则跳过且不阻断）
- 生成媒体治理三件套：.gitignore / .gitattributes / media-manifest.yaml

CLI：
  python init_project.py --slug my-film --title "我的短片" [--profile premium]
                         [--projects-root projects] [--no-git] [--json]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

# _shared/scripts 在 sub-skills/_shared/scripts；本脚本在 scripts/，需定位 _shared
SHARED_SCRIPTS = (Path(__file__).resolve().parent.parent
                  / "sub-skills" / "_shared" / "scripts")
sys.path.insert(0, str(SHARED_SCRIPTS))
from _common import write_yaml, ensure_validate_importable  # noqa: E402

ensure_validate_importable()
from validate import validate_obj  # noqa: E402

# §3.1 目录骨架
SUBDIRS = [
    "01_brief",
    "02_screenplay/episodes",
    "03_characters",
    "03_style/refs",
    "03_scenes",
    "04_storyboard/boards",
    "04b_previs",
    "05_prompts/genspecs",
    "05_prompts/taskcards",
    "06_generations",
    "07_audio",
    "08_edit/master",
    "09_publish",
    "ledger",
]

# 媒体治理：项目级 .gitignore（设计稿 §3.1 / §4 S-P0-4）
PROJECT_GITIGNORE = """\
# 媒体治理（设计稿 §3.1 / §4 S-P0-4）：Git 只管文本契约 + media-manifest。
06_generations/**/inbox/
06_generations/**/_unmatched/
06_generations/**/takes/
07_audio/
08_edit/master/
09_publish/

# 媒体扩展名
*.mp4
*.mov
*.wav
*.mp3
*.png
*.jpg
*.jpeg

# 凭证绝不入仓
.env
.env.*
*.key
"""

# git-lfs 白名单（少量关键媒体：定角图/选定首帧）
PROJECT_GITATTRIBUTES = """\
# git-lfs 白名单（设计稿 §4 S-P0-4）：仅少量关键媒体走 lfs
03_characters/**/turnaround/*.png filter=lfs diff=lfs merge=lfs -text
04_storyboard/boards/*.png filter=lfs diff=lfs merge=lfs -text
"""


def default_project(slug: str, title: str, profile: str) -> dict[str, Any]:
    """生成符合 C1 的最小可用 project.yaml。"""
    return {
        "id": slug,
        "title": title,
        "format": "short_film",
        "profile": profile,
        "platform_strategy": "dual",
        "execution_default": "hybrid",
        "target_platform": ["douyin", "bilibili"],
        "aspect_ratio": "16:9",
        "duration_target_s": 180,
        "stage": "S0_IDEA",
        "gates": {
            "G1_concept": {"status": "pending"},
            "G3_character": {"status": "pending"},
            "G6_select": {"status": "pending"},
        },
        "budget": {
            "token_budget_cny": 3000,
            "alert_threshold": 0.8,
            "per_shot_cost_cap_cny": 80,
            "ai_qc_cost_cap_cny": 200,
        },
        "api_config": {
            "fal_key_env": "FAL_KEY",
            "volcano_ak_env": "VOLCANO_AK",
            "max_concurrent": 4,
            "queue_backend": "polling",
            "retry_429": {"max": 5, "backoff": "exponential", "base_s": 2},
            "balance_alert_cny": 50,
            "fallback_on_quota_exhausted": "ui_only",
            "health_heartbeat_min": 10,
        },
        "language": {
            "ui_lang": "zh",
            "compiled_lang_by_channel": {
                "volcano": "zh", "jimeng": "zh",
                "falai": "en", "higgsfield": "en", "openart": "en",
            },
        },
        "platform_risk": {
            "primary": "higgsfield",
            "fallback_chain": ["openart", "jimeng", "api_falai", "api_volcano"],
            "local_is_source_of_truth": True,
            "avoid_annual_plan": True,
            "capabilities_reverify_days": 30,
        },
        "episodes": None,
        "versions": [],
    }


def _git_init(project_dir: Path) -> bool:
    """尝试 git init；失败/无 git 不阻断。返回是否成功。"""
    try:
        subprocess.run(["git", "init", "-q"], cwd=project_dir, check=True,
                       capture_output=True)
        return True
    except (FileNotFoundError, subprocess.CalledProcessError):
        return False


def init_project(slug: str, title: str, *, profile: str = "premium",
                 projects_root: str | Path = "projects",
                 do_git: bool = True) -> dict[str, Any]:
    """创建项目骨架。返回结果摘要 dict。"""
    project_dir = Path(projects_root) / slug
    project_dir.mkdir(parents=True, exist_ok=True)

    created = []
    for sub in SUBDIRS:
        d = project_dir / sub
        d.mkdir(parents=True, exist_ok=True)
        # 让空目录可被 git 跟踪
        keep = d / ".gitkeep"
        if not keep.exists():
            keep.write_text("", encoding="utf-8")
        created.append(sub)

    # project.yaml（C1）—— 写前校验
    proj = default_project(slug, title, profile)
    validate_obj(proj, "C1")
    write_yaml(project_dir / "project.yaml", proj)

    # 媒体治理三件套
    (project_dir / ".gitignore").write_text(PROJECT_GITIGNORE, encoding="utf-8")
    (project_dir / ".gitattributes").write_text(PROJECT_GITATTRIBUTES, encoding="utf-8")
    write_yaml(project_dir / "media-manifest.yaml",
               {"media": [], "note": "媒体 hash+路径索引；实体由 backup.py 同步外部存储"})

    git_ok = _git_init(project_dir) if do_git else False

    return {
        "project_dir": str(project_dir),
        "subdirs_created": created,
        "git_initialized": git_ok,
        "files": ["project.yaml", ".gitignore", ".gitattributes", "media-manifest.yaml"],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="初始化 AIGC 短视频项目骨架")
    parser.add_argument("--slug", required=True, help="项目 slug（kebab-case）")
    parser.add_argument("--title", required=True, help="项目标题")
    parser.add_argument("--profile", default="premium",
                        choices=["premium", "series", "rapid", "exploration"])
    parser.add_argument("--projects-root", default="projects")
    parser.add_argument("--no-git", action="store_true", help="跳过 git init")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    result = init_project(args.slug, args.title, profile=args.profile,
                          projects_root=args.projects_root, do_git=not args.no_git)

    if args.json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        print(f"项目已初始化：{result['project_dir']}")
        print(f"  目录数：{len(result['subdirs_created'])}")
        print(f"  git init：{'成功' if result['git_initialized'] else '跳过/不可用'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
