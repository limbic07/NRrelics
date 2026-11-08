"""
存档管理模块
处理Steam用户识别、存档备份与恢复
"""

import os
import re
import shutil
import tempfile
from datetime import datetime
from core.utils import get_user_data_path, log_debug

try:
    import winreg
except ImportError:  # 非 Windows 环境下仍可运行路径相关测试
    winreg = None



class SaveManager:
    """存档管理器"""

    # 存档目录
    SAVE_DIR_BASE = os.path.join(os.environ.get("APPDATA", ""), "Nightreign")
    SAVE_FILENAME = "NR0000.sl2"

    # 备份目录
    BACKUP_DIR = get_user_data_path("data/save_backups")
    @staticmethod
    def _temporary_path(directory: str) -> str:
        fd, path = tempfile.mkstemp(prefix=".nrrelic_backup_", dir=directory)
        os.close(fd)
        return path

    def __init__(self, steam_path: str = ""):
        configured_path = self._normalize_steam_path(steam_path)
        self.steam_path = (configured_path if self.is_valid_steam_path(configured_path)
                           else self.detect_steam_path())
        self.users = {}
        self._load_steam_users()
        os.makedirs(self.BACKUP_DIR, exist_ok=True)

    @staticmethod
    def _normalize_steam_path(path: str) -> str:
        """接受注册表中的 SteamPath、SteamExe 以及手动选择的目录。"""
        if not path:
            return ""
        path = str(path).strip().strip('"').strip()
        if not path:
            return ""
        path = os.path.normpath(os.path.expandvars(path))
        if os.path.basename(path).lower() == "steam.exe":
            path = os.path.dirname(path)
        return path

    @classmethod
    def is_valid_steam_path(cls, path: str) -> bool:
        """安装目录应包含 Steam 程序或已登录用户配置。"""
        path = cls._normalize_steam_path(path)
        return bool(path) and (
            os.path.isfile(os.path.join(path, "steam.exe")) or
            os.path.isfile(os.path.join(path, "config", "loginusers.vdf"))
        )

    @staticmethod
    def _registry_steam_paths():
        """优先读取 Steam 官方安装信息，覆盖任意盘符和自定义目录。"""
        if winreg is None:
            return []
        locations = (
            (winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam", ("SteamPath", "SteamExe")),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Valve\Steam", ("InstallPath", "SteamPath")),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam", ("InstallPath", "SteamPath")),
        )
        paths = []
        for hive, key_name, value_names in locations:
            try:
                with winreg.OpenKey(hive, key_name) as key:
                    for value_name in value_names:
                        try:
                            value, _ = winreg.QueryValueEx(key, value_name)
                            if value:
                                paths.append(value)
                        except OSError:
                            continue
            except OSError:
                continue
        return paths

    @classmethod
    def detect_steam_path(cls) -> str:
        """注册表优先；失效时检查所有盘符上的常见安装目录。"""
        candidates = list(cls._registry_steam_paths())
        try:
            drives = os.listdrives()
        except (AttributeError, OSError):
            drives = []
        for drive in drives:
            candidates.extend(os.path.join(drive, suffix) for suffix in (
                "Steam", os.path.join("Program Files (x86)", "Steam"),
                os.path.join("Program Files", "Steam"),
                os.path.join("Games", "Steam"), os.path.join("Apps", "Steam"),
            ))
        candidates.extend(os.path.join(os.environ[name], "Steam")
                          for name in ("ProgramFiles(x86)", "ProgramFiles")
                          if os.environ.get(name))

        seen = set()
        configuration_only_path = ""
        for candidate in candidates:
            path = cls._normalize_steam_path(candidate)
            key = os.path.normcase(path)
            if key not in seen:
                seen.add(key)
                if cls.is_valid_steam_path(path):
                    if os.path.isfile(os.path.join(path, "steam.exe")):
                        return path
                    if not configuration_only_path:
                        configuration_only_path = path
        return configuration_only_path

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
            log_debug(f"[错误] 解析Steam用户信息失败: {e}")

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

        temp_save = None
        try:
            temp_save = self._temporary_path(backup_dir)
            shutil.copy2(save_path, temp_save)
            os.replace(temp_save, backup_path)
            temp_save = None
            return True, f"备份成功: {backup_name}"
        except Exception as e:
            return False, f"备份失败: {e}"
        finally:
            if temp_save and os.path.exists(temp_save):
                os.remove(temp_save)

    def restore_save(self, steam_id: str, backup_path: str) -> tuple:
        """仅恢复游戏存档，不读取或修改遗物数据库。"""
        if not os.path.exists(backup_path):
            return False, "备份文件不存在"
        save_path = self.get_save_path(steam_id)
        save_dir = os.path.dirname(save_path)
        temp_save = None
        try:
            os.makedirs(save_dir, exist_ok=True)
            temp_save = self._temporary_path(save_dir)
            shutil.copy2(backup_path, temp_save)
            if os.path.exists(save_path):
                shutil.copy2(save_path, save_path + ".bak")
            os.replace(temp_save, save_path)
            temp_save = None
            return True, "存档恢复成功；如需更新遗物库存，请在遗物管理中点击刷新库存"
        except Exception as e:
            return False, f"恢复失败: {e}"
        finally:
            if temp_save and os.path.exists(temp_save):
                os.remove(temp_save)

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
        configured_path = self._normalize_steam_path(steam_path)
        self.steam_path = (configured_path if self.is_valid_steam_path(configured_path)
                           else self.detect_steam_path())
        self._load_steam_users()
