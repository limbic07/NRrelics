"""工具类模块"""

import json
from pathlib import Path


class ConfigManager:
    """配置管理器"""

    @staticmethod
    def load_config(config_path: str = "config/settings.json") -> dict:
        """加载配置文件"""
        path = Path(config_path)
        if path.exists():
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}

    @staticmethod
    def save_config(config: dict, config_path: str = "config/settings.json"):
        """保存配置文件"""
        path = Path(config_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
