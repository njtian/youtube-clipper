#!/usr/bin/env python3
"""
输出 .env 中配置的 OUTPUT_DIR（解析为绝对路径）。
供 Skill 在创建输出目录前获取生成文件的基础目录。
在 youtube-clipper 目录下执行：python3 scripts/get_output_dir.py
"""

import os
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_ROOT = SCRIPT_DIR.parent


def get_output_base_dir() -> Path:
    """从 .env 读取 OUTPUT_DIR，未设置时默认 ./.output，返回解析后的绝对路径。"""
    try:
        from dotenv import load_dotenv
        load_dotenv(SKILL_ROOT / ".env")
    except ImportError:
        pass
    raw = os.environ.get("OUTPUT_DIR", "./.output")
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = (SKILL_ROOT / path).resolve()
    return path


if __name__ == "__main__":
    try:
        base = get_output_base_dir()
        print(base)
    except Exception as e:
        sys.stderr.write(f"get_output_dir: {e}\n")
        sys.exit(1)
