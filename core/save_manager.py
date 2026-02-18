"""
存档管理模块
处理Steam用户识别、存档备份与恢复
"""

import os
import re
import shutil
from datetime import datetime


class SaveManager:
    """存档管理器"""

    # 默认Steam安装路径
    DEFAULT_STEAM_PATHS = [
        r"C:\Program Files (x86)\Steam",
        r"C:\Program Files\Steam",
        r"D:\Steam",
        r"D:\Program Files (x86)\Steam",
        r"D:\Program Files\Steam",
    ]

    # 存档目录
    SAVE_DIR_BASE = os.path.join(os.environ.get("APPDATA", ""), "Nightreign")
    SAVE_FILENAME = "NR0000.sl2"

    # 备份目录
    BACKUP_DIR = "data/save_backups"

    def __init__(self, steam_path: str = ""):
        self.steam_path = steam_path or self._detect_steam_path()
        self.users = {}
        self._load_steam_users()
        os.makedirs(self.BACKUP_DIR, exist_ok=True)

    def _detect_steam_path(self) -> str:
        """自动检测Steam安装路径"""
        for path in self.DEFAULT_STEAM_PATHS:
            vdf_path = os.path.join(path, "config", "loginusers.vdf")
            if os.path.exists(vdf_path):
                return path
        return ""

    def _parse_vdf(self, content: str) -> dict:
        """简易VDF解析器"""
        result = {}
        stack = [result]
        key = None

        for line in content.split('\n'):
            line = line.strip()
            if not line or line.startswith('//'):
                continue

            kv_match = re.match(r'"([^"]*?)"\s+"([^"]*?)"', line)
            if kv_match:
                stack[-1][kv_match.group(1)] = kv_match.group(2)
                continue

            key_match = re.match(r'"([^"]*?)"', line)
            if key_match:
                key = key_match.group(1)
                continue

            if line == '{':
                if key is not None:
                    new_dict = {}
                    stack[-1][key] = new_dict
                    stack.append(new_dict)
                    key = None
                continue

            if line == '}':
                if len(stack) > 1:
                    stack.pop()
                continue

        return result

    def _load_steam_users(self):
        """从loginusers.vdf加载Steam用户信息"""
        self.users = {}
        if not self.steam_path:
            return

        vdf_path = os.path.join(self.steam_path, "config", "loginusers.vdf")
        if not os.path.exists(vdf_path):
            return

        try:
            with open(vdf_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()

            data = self._parse_vdf(content)
            users_data = data.get("users", {})
            for steam_id, info in users_data.items():
                if isinstance(info, dict):
                    self.users[steam_id] = {
                        "name": info.get("PersonaName", info.get("AccountName", steam_id)),
                        "account_name": info.get("AccountName", ""),
                        "most_recent": info.get("MostRecent", "0") == "1"
                    }
        except Exception as e:
            print(f"[错误] 解析Steam用户信息失败: {e}")

    def get_users(self) -> dict:
        """获取所有Steam用户"""
        return self.users

    def get_most_recent_user(self) -> str:
        """获取最近登录的用户ID"""
        for steam_id, info in self.users.items():
            if info.get("most_recent"):
                return steam_id
        if self.users:
            return next(iter(self.users))
        return ""

    def get_save_path(self, steam_id: str) -> str:
        """获取指定用户的存档路径"""
        return os.path.join(self.SAVE_DIR_BASE, steam_id, self.SAVE_FILENAME)

    def get_save_info(self, steam_id: str) -> dict:
        """获取存档信息"""
        save_path = self.get_save_path(steam_id)
        if not os.path.exists(save_path):
            return {"exists": False, "modified_time": "", "size": 0}

        stat = os.stat(save_path)
        modified_time = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
        return {
            "exists": True,
            "modified_time": modified_time,
            "size": stat.st_size
        }

    def get_backups(self, steam_id: str) -> list:
        """获取指定用户的所有备份"""
        backup_dir = os.path.join(self.BACKUP_DIR, steam_id)
        if not os.path.exists(backup_dir):
            return []

        backups = []
        for filename in os.listdir(backup_dir):
            if filename.endswith(".sl2"):
                filepath = os.path.join(backup_dir, filename)
                stat = os.stat(filepath)
                modified_time = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
                display_name = filename[:-4]
                backups.append({
                    "filename": filename,
                    "display_name": display_name,
                    "path": filepath,
                    "modified_time": modified_time,
                    "size": stat.st_size
                })

        backups.sort(key=lambda x: x["modified_time"], reverse=True)
        return backups

    def backup_save(self, steam_id: str, backup_name: str = "") -> tuple:
        """备份存档"""
        save_path = self.get_save_path(steam_id)
        if not os.path.exists(save_path):
            return False, "存档文件不存在"

        if not backup_name:
            backup_name = datetime.now().strftime("%Y%m%d_%H%M%S")

        backup_name = re.sub(r'[<>:"/\\|?*]', '_', backup_name)
        backup_dir = os.path.join(self.BACKUP_DIR, steam_id)
        os.makedirs(backup_dir, exist_ok=True)

        backup_path = os.path.join(backup_dir, f"{backup_name}.sl2")
        if os.path.exists(backup_path):
            return False, f"已存在同名备份: {backup_name}"

        try:
            shutil.copy2(save_path, backup_path)
            return True, f"备份成功: {backup_name}"
        except Exception as e:
            return False, f"备份失败: {e}"

    def restore_save(self, steam_id: str, backup_path: str) -> tuple:
        """恢复存档"""
        if not os.path.exists(backup_path):
            return False, "备份文件不存在"

        save_path = self.get_save_path(steam_id)
        save_dir = os.path.dirname(save_path)
        os.makedirs(save_dir, exist_ok=True)

        try:
            # 如果当前存档存在，先备份到游戏存档目录（.sl2.bak）
            if os.path.exists(save_path):
                bak_path = save_path + ".bak"
                shutil.copy2(save_path, bak_path)

            # 恢复备份
            shutil.copy2(backup_path, save_path)
            return True, "存档恢复成功"
        except Exception as e:
            return False, f"恢复失败: {e}"

    def rename_backup(self, old_path: str, new_name: str) -> tuple:
        """重命名备份"""
        if not os.path.exists(old_path):
            return False, "备份文件不存在"

        new_name = re.sub(r'[<>:"/\\|?*]', '_', new_name)
        new_path = os.path.join(os.path.dirname(old_path), f"{new_name}.sl2")

        if os.path.exists(new_path):
            return False, f"已存在同名备份: {new_name}"

        try:
            os.rename(old_path, new_path)
            return True, f"重命名成功: {new_name}"
        except Exception as e:
            return False, f"重命名失败: {e}"

    def delete_backup(self, backup_path: str) -> tuple:
        """删除备份"""
        if not os.path.exists(backup_path):
            return False, "备份文件不存在"

        try:
            os.remove(backup_path)
            return True, "删除成功"
        except Exception as e:
            return False, f"删除失败: {e}"

    def set_steam_path(self, steam_path: str):
        """设置Steam路径并重新加载用户"""
        self.steam_path = steam_path
        self._load_steam_users()
