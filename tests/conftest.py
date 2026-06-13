"""pytest 公共夹具：把各脚本目录加入 sys.path，提供构造夹具的工具。"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SKILL_BASE = REPO_ROOT / "skills" / "aigc-video-studio"
SHARED_SCRIPTS = SKILL_BASE / "sub-skills" / "_shared" / "scripts"
PC_SCRIPTS = SKILL_BASE / "sub-skills" / "prompt-compiler" / "scripts"
GR_SCRIPTS = SKILL_BASE / "sub-skills" / "gen-runner" / "scripts"
SK0_SCRIPTS = SKILL_BASE / "scripts"

for p in (SHARED_SCRIPTS, PC_SCRIPTS, GR_SCRIPTS, SK0_SCRIPTS):
    sp = str(p)
    if sp not in sys.path:
        sys.path.insert(0, sp)


@pytest.fixture
def shotlist_shot():
    """一个最小但 CRAFT 八要素齐备的镜头定义（供编译/出卡用）。"""
    return {
        "shot_id": "SHOT-07",
        "scene": "废弃加油站，黄昏逆光，沙尘弥漫",
        "order": 7,
        "duration_s": 8,
        "characters": ["robo-cowboy"],
        "shot_size": "中景到特写",
        "control_level": "guided",
        "camera_move": "缓慢推轨至面部",
        "composition": "主体居右三分纵线，视线导向左上对角",
        "action_logic": "锈牛仔听到声响停步，紧张地压低帽檐，右手移向腰部转轮",
        "audio_cue": "风声渐弱，金属吱呀声渐近，无对白",
        "first_frame": "04_storyboard/boards/SHOT-07-frame.png",
        "status": "generating",
    }


@pytest.fixture
def project_dir(tmp_path):
    """初始化一个临时项目（不 git），返回项目目录 Path。"""
    import init_project
    res = init_project.init_project("test-proj", "测试项目",
                                    projects_root=str(tmp_path), do_git=False)
    return Path(res["project_dir"])
