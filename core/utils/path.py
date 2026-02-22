"""
路径处理工具 - 支持开发和打包环境
"""

import sys
import os
from pathlib import Path


def get_app_root() -> Path:
    """
    获取应用根目录。
    开发环境：项目根目录
    打包环境：可执行文件所在目录
    """
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).parent
    else:
        # core/utils/path.py -> core/utils/ -> core/ -> root/
        return Path(__file__).parent.parent.parent


def get_resource_path(relative_path: str) -> str:
    """
    获取静态资源文件的绝对路径（打包入exe的文件）。
    兼容开发环境（直接运行）和打包环境（PyInstaller --add-data）。

    Args:
        relative_path: 相对于项目根目录的路径，例如 "data/template.jpg"

    Returns:
        str: 文件的绝对路径字符串 (OpenCV/RapidOCR 等库通常需要字符串)
    """
    if hasattr(sys, '_MEIPASS'):
        # PyInstaller 打包后的临时目录
        base_path = Path(sys._MEIPASS)
    else:
        base_path = Path(__file__).parent.parent.parent

    full_path = base_path / relative_path
    return str(full_path.resolve())


def get_user_data_path(relative_path: str) -> str:
    """
    获取用户数据文件的绝对路径（需读写的文件）。
    始终指向可执行文件同级目录下的文件。

    Args:
        relative_path: 相对于应用根目录的路径，例如 "data/settings.json"

    Returns:
        str: 文件的绝对路径字符串
    """
    base_path = get_app_root()
    full_path = base_path / relative_path

    # 确保父目录存在
    ensure_dir(Path(full_path).parent)

    return str(full_path.resolve())


def ensure_dir(directory_path: Path):
    """确保目录存在，不存在则创建"""
    if not directory_path.exists():
        directory_path.mkdir(parents=True, exist_ok=True)
