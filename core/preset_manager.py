"""
预设管理器
负责预设的CRUD操作、持久化和词条库加载
"""

import json
import os
import uuid
from typing import Dict, List, Optional
from core.utils import get_resource_path, get_user_data_path



# 预设类型常量
PRESET_TYPE_NORMAL_WHITELIST = "normal_whitelist"
PRESET_TYPE_DEEPNIGHT_WHITELIST = "deepnight_whitelist"
PRESET_TYPE_DEEPNIGHT_BLACKLIST = "deepnight_blacklist"


class PresetManager:
    """预设管理器"""

    def __init__(self, data_dir: str = "data"):
        self.data_dir = data_dir
        # presets.json 是用户数据，需读写
        self.presets_file = get_user_data_path(os.path.join(data_dir, "presets.json"))

        # 预设存储结构
        self.normal_general = None
        self.deepnight_general = None
        self.normal_dedicated = {}
        self.deepnight_whitelist_dedicated = {}
        self.deepnight_blacklist = None

        # 词条库缓存
        self._vocab_cache = {}

        # 加载预设
        self.load_presets()

    def load_presets(self):
        """从文件加载预设"""
        if not os.path.exists(self.presets_file):
            # 初始化默认预设
            self._initialize_default_presets()
            self.save_presets()
            return

        try:
            with open(self.presets_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

            self.normal_general = data.get("normal_general")
            self.deepnight_general = data.get("deepnight_general")
            self.normal_dedicated = data.get("normal_dedicated", {})
            self.deepnight_whitelist_dedicated = data.get("deepnight_whitelist_dedicated", {})
            self.deepnight_blacklist = data.get("deepnight_blacklist")

        except Exception as e:
            print(f"[错误] 加载预设失败: {e}")
            self._initialize_default_presets()

    def save_presets(self):
        """保存预设到文件"""
        data = {
            "version": "1.0",
            "normal_general": self.normal_general,
            "deepnight_general": self.deepnight_general,
            "normal_dedicated": self.normal_dedicated,
            "deepnight_whitelist_dedicated": self.deepnight_whitelist_dedicated,
            "deepnight_blacklist": self.deepnight_blacklist
        }

        os.makedirs(self.data_dir, exist_ok=True)

        try:
            with open(self.presets_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[错误] 保存预设失败: {e}")

    def _initialize_default_presets(self):
        """初始化默认预设"""
        # 普通模式通用预设
        self.normal_general = {
            "id": "normal_general",
            "name": "普通通用预设",
            "type": PRESET_TYPE_NORMAL_WHITELIST,
            "affixes": [],
            "is_general": True,
            "is_active": True
        }

        # 深夜模式通用预设
        self.deepnight_general = {
            "id": "deepnight_general",
            "name": "深夜通用预设",
            "type": PRESET_TYPE_DEEPNIGHT_WHITELIST,
            "affixes": [],
            "is_general": True,
            "is_active": True
        }

        # 深夜黑名单预设
        self.deepnight_blacklist = {
            "id": "deepnight_blacklist",
            "name": "深夜黑名单",
            "type": PRESET_TYPE_DEEPNIGHT_BLACKLIST,
            "affixes": [],
            "is_general": False,
            "is_active": True
        }

    def load_vocabulary(self, preset_type: str, for_editing: bool = True) -> List[str]:
        """
        加载词条库

        Args:
            preset_type: 预设类型
            for_editing: 是否用于编辑（True=仅加载常规词条，False=加载完整词条库）

        Returns:
            词条列表（已清洗）
        """
        # 生成缓存键（区分编辑和识别）
        cache_key = f"{preset_type}_{'edit' if for_editing else 'full'}"

        # 检查缓存
        if cache_key in self._vocab_cache:
            return self._vocab_cache[cache_key]

        # 确定词条库文件
        if preset_type == PRESET_TYPE_NORMAL_WHITELIST:
            # 编辑模式：只加载normal.txt
            # 识别模式：加载normal.txt + normal_special.txt
            files = ["normal.txt"] if for_editing else ["normal.txt", "normal_special.txt"]
        elif preset_type == PRESET_TYPE_DEEPNIGHT_WHITELIST:
            files = ["deepnight_pos.txt"]
        elif preset_type == PRESET_TYPE_DEEPNIGHT_BLACKLIST:
            files = ["deepnight_neg.txt"]
        else:
            return []

        vocabulary = []
        for filename in files:
            # 词条库是静态资源，只读
            filepath = get_resource_path(os.path.join(self.data_dir, filename))
            if not os.path.exists(filepath):
                print(f"[警告] 词条库文件不存在: {filepath}")
                continue

            with open(filepath, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue

                    # 支持两种格式：行号→词条 或 直接词条
                    if '→' in line:
                        entry = line.split('→', 1)[1].strip()
                    else:
                        entry = line

                    # 不清洗词条，保留原始格式（包括【】等特殊符号）
                    if entry:
                        vocabulary.append(entry)

        # 缓存
        self._vocab_cache[cache_key] = vocabulary
        return vocabulary

    # ==================== 通用预设操作 ====================

    def get_general_preset(self, mode: str) -> Optional[Dict]:
        """获取通用预设"""
        if mode == "normal":
            return self.normal_general
        elif mode == "deepnight":
            return self.deepnight_general
        return None

    def update_general_preset(self, mode: str, affixes: List[str]):
        """更新通用预设的词条"""
        if mode == "normal":
            self.normal_general["affixes"] = affixes
        elif mode == "deepnight":
            self.deepnight_general["affixes"] = affixes
        self.save_presets()

    # ==================== 专用预设操作 ====================

    def get_dedicated_presets(self, mode: str) -> Dict[str, Dict]:
        """获取专用预设列表"""
        if mode == "normal":
            return self.normal_dedicated
        elif mode == "deepnight":
            return self.deepnight_whitelist_dedicated
        return {}

    def get_active_dedicated_presets(self, mode: str) -> List[Dict]:
        """获取激活的专用预设列表"""
        presets = self.get_dedicated_presets(mode)
        return [p for p in presets.values() if p.get("is_active", True)]

    def create_dedicated_preset(self, mode: str, name: str, affixes: List[str]) -> str:
        """
        创建专用预设

        Returns:
            预设ID
        """
        # 检查数量限制
        presets = self.get_dedicated_presets(mode)
        if len(presets) >= 20:
            raise ValueError("专用预设数量已达上限（20个）")

        # 创建预设
        preset_id = str(uuid.uuid4())
        preset_type = PRESET_TYPE_NORMAL_WHITELIST if mode == "normal" else PRESET_TYPE_DEEPNIGHT_WHITELIST

        preset = {
            "id": preset_id,
            "name": name,
            "type": preset_type,
            "affixes": affixes,
            "is_general": False,
            "is_active": True
        }

        if mode == "normal":
            self.normal_dedicated[preset_id] = preset
        elif mode == "deepnight":
            self.deepnight_whitelist_dedicated[preset_id] = preset

        self.save_presets()
        return preset_id

    def update_dedicated_preset(self, mode: str, preset_id: str, name: str = None, affixes: List[str] = None):
        """更新专用预设"""
        presets = self.get_dedicated_presets(mode)

        if preset_id not in presets:
            raise ValueError(f"预设不存在: {preset_id}")

        if name is not None:
            presets[preset_id]["name"] = name
        if affixes is not None:
            presets[preset_id]["affixes"] = affixes

        self.save_presets()

    def delete_dedicated_preset(self, mode: str, preset_id: str):
        """删除专用预设"""
        presets = self.get_dedicated_presets(mode)

        if preset_id in presets:
            del presets[preset_id]
            self.save_presets()

    def toggle_preset_active(self, mode: str, preset_id: str):
        """切换预设激活状态"""
        presets = self.get_dedicated_presets(mode)

        if preset_id in presets:
            presets[preset_id]["is_active"] = not presets[preset_id].get("is_active", True)
            self.save_presets()

    # ==================== 黑名单预设操作 ====================

    def get_blacklist_preset(self) -> Optional[Dict]:
        """获取黑名单预设"""
        return self.deepnight_blacklist

    def update_blacklist_preset(self, affixes: List[str]):
        """更新黑名单预设的词条"""
        self.deepnight_blacklist["affixes"] = affixes
        self.save_presets()
