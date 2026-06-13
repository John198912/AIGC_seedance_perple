"""脚本共享工具：路径解析、yaml/json 读写、原子写。

所有 P0 脚本复用本模块，避免重复实现 I/O 与路径逻辑。
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

import yaml

# _shared 目录（schemas/ libs/ scripts/ 的父级）
SHARED_DIR = Path(__file__).resolve().parent.parent
SCHEMA_DIR = SHARED_DIR / "schemas"
LIBS_DIR = SHARED_DIR / "libs"


def ensure_validate_importable() -> None:
    """把 _shared/scripts 加入 sys.path，使其他目录的脚本可 import validate。"""
    scripts_dir = str(Path(__file__).resolve().parent)
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)


def read_yaml(path: str | Path) -> Any:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"找不到文件：{p}")
    return yaml.safe_load(p.read_text(encoding="utf-8"))


def write_yaml(path: str | Path, data: Any) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    text = yaml.safe_dump(data, allow_unicode=True, sort_keys=False)
    _atomic_write(p, text)


def read_json(path: str | Path) -> Any:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"找不到文件：{p}")
    return json.loads(p.read_text(encoding="utf-8"))


def write_json(path: str | Path, data: Any) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(data, ensure_ascii=False, indent=2)
    _atomic_write(p, text)


def _atomic_write(path: Path, text: str) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def load_lib(name: str) -> Any:
    """读取 _shared/libs/ 下的某个 yaml 库文件。"""
    return read_yaml(LIBS_DIR / name)


def project_path(project: str | Path, *parts: str) -> Path:
    return Path(project).joinpath(*parts)
