"""项目初始化单测：骨架目录、project.yaml（C1）、媒体治理三件套。"""
from __future__ import annotations

from pathlib import Path

import init_project


def test_init_creates_skeleton(tmp_path):
    res = init_project.init_project("p1", "测试片", projects_root=str(tmp_path), do_git=False)
    pd = Path(res["project_dir"])
    assert pd.is_dir()
    # 关键阶段目录存在
    for sub in ("03_characters", "06_generations", "07_audio", "09_publish"):
        assert (pd / sub).is_dir()
        assert (pd / sub / ".gitkeep").exists()


def test_init_writes_governance_files(tmp_path):
    res = init_project.init_project("p2", "测试片2", projects_root=str(tmp_path), do_git=False)
    pd = Path(res["project_dir"])
    assert (pd / "project.yaml").exists()
    assert (pd / ".gitignore").exists()
    assert (pd / ".gitattributes").exists()
    assert (pd / "media-manifest.yaml").exists()


def test_init_project_yaml_valid(tmp_path):
    from _common import read_yaml
    from validate import validate_obj
    res = init_project.init_project("p3", "测试片3", projects_root=str(tmp_path), do_git=False)
    proj = read_yaml(Path(res["project_dir"]) / "project.yaml")
    validate_obj(proj, "C1")
    assert proj["title"] == "测试片3"
