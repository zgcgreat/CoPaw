# -*- coding: utf-8 -*-
from pathlib import Path

from .constant import WORKING_DIR


def get_config_path() -> Path:
    """获取配置文件路径."""
    return WORKING_DIR / "config.json"


def ensure_working_dir() -> Path:
    """确保工作目录存在."""
    WORKING_DIR.mkdir(parents=True, exist_ok=True)
    return WORKING_DIR
