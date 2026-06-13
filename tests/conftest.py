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
# Phase 2 子技能脚本目录
SB_SCRIPTS = SKILL_BASE / "sub-skills" / "storyboard-director" / "scripts"
SW_SCRIPTS = SKILL_BASE / "sub-skills" / "screenplay-writer" / "scripts"
CF_SCRIPTS = SKILL_BASE / "sub-skills" / "character-foundry" / "scripts"
QC_SCRIPTS = SKILL_BASE / "sub-skills" / "qc-review" / "scripts"
AP_SCRIPTS = SKILL_BASE / "sub-skills" / "audio-post" / "scripts"
EF_SCRIPTS = SKILL_BASE / "sub-skills" / "edit-finish" / "scripts"
PK_SCRIPTS = SKILL_BASE / "sub-skills" / "publish-kit" / "scripts"
# Phase 7 逆向特征工程模块
FDC_SCRIPTS = SKILL_BASE / "sub-skills" / "feature-deconstruct" / "scripts"

for p in (SHARED_SCRIPTS, PC_SCRIPTS, GR_SCRIPTS, SK0_SCRIPTS,
          SB_SCRIPTS, SW_SCRIPTS, CF_SCRIPTS, QC_SCRIPTS,
          AP_SCRIPTS, EF_SCRIPTS, PK_SCRIPTS, FDC_SCRIPTS):
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


def _write_yaml(path, data):
    """测试辅助：写 yaml（不引入对脚本的依赖）。"""
    import yaml
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
                    encoding="utf-8")


@pytest.fixture
def write_yaml():
    """暴露写 yaml 辅助给测试用。"""
    return _write_yaml


@pytest.fixture
def shotlist_doc(shotlist_shot):
    """一个最小合法的 shotlist 文档（C5），含两个镜头。"""
    s2 = dict(shotlist_shot, shot_id="SHOT-08", order=8,
              ambience_group="加油站", control_level="locked")
    return {"meta": {"shot_count": 2}, "shots": [dict(shotlist_shot, ambience_group="加油站"), s2]}


@pytest.fixture
def make_takelog():
    """构造一个合法 TakeLog（C9），take_id 可定制以触发 VLM 不同裁决分支。"""
    def _make(shot_id="SHOT-07", take_ids=None):
        take_ids = take_ids or [f"{shot_id}-t01", f"{shot_id}-t02"]
        takes = []
        for tid in take_ids:
            takes.append({
                "take_id": tid, "pass": "draft", "channel": "api",
                "file": f"takes/{tid}.mp4",
                "platform_meta": {"seed": 123, "model_version": "seedance-2.0"},
                "scores": {}, "prompt_pattern_tags": ["推轨+逆光"],
                "rejected_reason": None, "status": "ingested",
            })
        return {"shot_id": shot_id, "takes": takes,
                "selected_take": None, "rerun_history": []}
    return _make
