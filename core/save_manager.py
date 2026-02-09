"""存档管理模块"""

import json
import os
from datetime import datetime


class SaveManager:
    """游戏存档管理器"""

    def __init__(self, save_dir: str = "saves"):
        self.save_dir = save_dir
        os.makedirs(save_dir, exist_ok=True)

    def save_result(self, data: dict, filename: str = None) -> str:
        """保存识别结果"""
        if filename is None:
            filename = f"result_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

        filepath = os.path.join(self.save_dir, filename)
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        return filepath

    def load_result(self, filename: str) -> dict:
        """加载识别结果"""
        filepath = os.path.join(self.save_dir, filename)
        if not os.path.exists(filepath):
            return {}

        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
