"""
预设管理器
负责预设的CRUD操作、持久化和词条库加载
"""

import json
import os
import uuid
from pathlib import Path
from typing import Dict, List, Optional
from core.utils import get_resource_path, get_user_data_path, log_debug
from core.relic_scoring import POSITIVE_TIERS, NEGATIVE_TIERS



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
        self.default_catalog_version = 0

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
            self.default_catalog_version = int(data.get("default_catalog_version", 0))
            if self.default_catalog_version < 3:
                self._merge_bundled_defaults()
                self.save_presets()

        except Exception as e:
            log_debug(f"[错误] 加载预设失败: {e}")
            self._initialize_default_presets()

    def save_presets(self):
        """保存预设到文件"""
        data = {
            "version": "2.0",
            "default_catalog_version": self.default_catalog_version,
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
            log_debug(f"[错误] 保存预设失败: {e}")

    def _initialize_default_presets(self):
        """初始化默认预设"""
        try:
            with open(get_resource_path('data/default_presets.json'), encoding='utf-8') as f:
                bundled = json.load(f)
            self.normal_general = bundled['normal_general']
            self.deepnight_general = bundled['deepnight_general']
            self.normal_dedicated = bundled['normal_dedicated']
            self.deepnight_whitelist_dedicated = bundled['deepnight_whitelist_dedicated']
            self.deepnight_blacklist = bundled['deepnight_blacklist']
            self.default_catalog_version = 3
            return
        except (OSError, ValueError, KeyError) as exc:
            log_debug(f"[警告] 内置默认预设不可用: {exc}")

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

    def restore_bundled_defaults(self):
        """Atomically replace user presets with bundled defaults."""
        with open(get_resource_path('data/default_presets.json'), encoding='utf-8') as source:
            bundled = json.load(source)
        fields = ('normal_general', 'deepnight_general', 'normal_dedicated',
                  'deepnight_whitelist_dedicated', 'deepnight_blacklist')
        for field in fields:
            if field not in bundled:
                raise ValueError(f'内置默认预设缺少 {field}')
        target = Path(self.presets_file)
        target.parent.mkdir(parents=True, exist_ok=True)
        payload = {field: bundled[field] for field in fields}
        payload.update(version='2.0', default_catalog_version=3)
        temporary = target.with_name(target.name + '.restore.tmp')
        try:
            temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
            temporary.replace(target)
        finally:
            temporary.unlink(missing_ok=True)
        for field in fields:
            setattr(self, field, bundled[field])
        self.default_catalog_version = 3
        self._vocab_cache.clear()

    def _merge_bundled_defaults(self):
        """One-time migration: add missing builds and official scores without replacing edits."""
        try:
            with open(get_resource_path('data/default_presets.json'), encoding='utf-8') as f:
                bundled = json.load(f)
        except (OSError, ValueError) as exc:
            log_debug(f"[警告] 无法迁移内置预设: {exc}")
            return
        self.normal_general = self.normal_general or bundled['normal_general']
        self.deepnight_general = self.deepnight_general or bundled['deepnight_general']
        self.deepnight_blacklist = self.deepnight_blacklist or bundled['deepnight_blacklist']
        for mode, field in (('normal', 'normal_dedicated'),
                            ('deepnight', 'deepnight_whitelist_dedicated')):
            current = getattr(self, field)
            for pid, preset in bundled[field].items():
                if pid not in current:
                    current[pid] = preset
                elif mode == 'normal':
                    if 'official_scores' not in current[pid]:
                        current[pid]['official_scores'] = preset.get('official_scores', {}).copy()
                    for affix in ('出击时，武器战技改为落雷',
                                  '【追踪者】发动技艺时，轻攻击能使出缠绕火焰的追加攻击（仅限大剑）'):
                        if affix in preset.get('affixes', []) and affix not in current[pid].get('affixes', []):
                            current[pid].setdefault('affixes', []).append(affix)
                            current[pid].setdefault('affix_tiers', {})[affix] = preset['affix_tiers'][affix]
                if pid in {f'build_{build_id}_{mode}' for build_id in ('R01', 'R02', 'R07')}:
                    affix = '血量偏低时，能提升减伤率'
                    if affix not in current[pid].get('affixes', []):
                        current[pid].setdefault('affixes', []).append(affix)
                        current[pid].setdefault('affix_tiers', {})[affix] = 'secondary'
        # 旧整合流派会把互斥的武器池或法祷分支一起计分。保留用户修改，
        # 但默认停用旧预设，由拆分后的独立预设接替。
        merged_ids = {
            'C27', 'C28', 'C41', 'C42', 'C13', 'C14', 'D12', 'D14',
            'R14', 'V09', 'V10', 'V14', 'H03', 'H07', 'E13', 'E15',
            'S12', 'U10', 'W7', 'G3', 'D15', 'R15', 'H11', 'S13',
        }
        for build_id in merged_ids:
            for field, suffix in (('normal_dedicated', 'normal'),
                                  ('deepnight_whitelist_dedicated', 'deepnight')):
                old = getattr(self, field).get(f'build_{build_id}_{suffix}')
                if old:
                    old['is_active'] = False
        self.default_catalog_version = 3

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
                log_debug(f"[警告] 词条库文件不存在: {filepath}")
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

    @staticmethod
    def _checked_tiers(affixes, tiers, inherited=()):
        if tiers is None:
            return None
        allowed = set(affixes) | set(inherited)
        if not isinstance(tiers, dict) or any(
                name not in allowed or tier not in POSITIVE_TIERS + NEGATIVE_TIERS
                for name, tier in tiers.items()):
            raise ValueError("词条等级配置无效")
        return {**{name: tiers.get(name, "secondary") for name in affixes},
                **{name: tier for name, tier in tiers.items() if name in inherited}}

    @staticmethod
    def _checked_negative_tiers(tiers):
        if tiers is None:
            return None
        if not isinstance(tiers, dict) or any(
                not isinstance(name, str) or tier not in POSITIVE_TIERS + NEGATIVE_TIERS
                for name, tier in tiers.items()):
            raise ValueError("负面词条等级配置无效")
        return tiers.copy()

    def update_general_preset(self, mode: str, affixes: List[str], affix_tiers=None,
                              negative_tiers=None, official_scores=None):
        """更新通用预设的词条"""
        grades = self._checked_tiers(affixes, affix_tiers)
        if mode == "normal":
            preset = self.normal_general
        elif mode == "deepnight":
            preset = self.deepnight_general
        else:
            raise ValueError("未知遗物模式")
        preset["affixes"] = affixes
        preset["affix_tiers"] = (grades if grades is not None else
                                 {a: t for a, t in preset.get("affix_tiers", {}).items() if a in affixes})
        if mode == "deepnight" and negative_tiers is not None:
            preset["negative_tiers"] = self._checked_negative_tiers(negative_tiers)
        if mode == 'normal' and official_scores is not None:
            preset['official_scores'] = self._checked_official_scores(official_scores)
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

    def create_dedicated_preset(self, mode: str, name: str, affixes: List[str],
                                required_affixes=None, blacklist_exceptions=None,
                                required_affix_groups=None, affix_tiers=None,
                                negative_tiers=None, excluded_affixes=None,
                                official_scores=None) -> str:
        """
        创建专用预设

        Returns:
            预设ID
        """
        # 检查数量限制
        presets = self.get_dedicated_presets(mode)
        if len(presets) >= 500:
            raise ValueError("专用预设数量已达上限（500个）")

        grouped_supplied = required_affix_groups is not None
        if required_affix_groups is None:
            required_affixes = list(required_affixes or [])
            required_affix_groups = [[a] for a in required_affixes]
        else:
            required_affix_groups = self._validate_required_groups(required_affix_groups)
            required_affixes = [a for group in required_affix_groups for a in group]
        allowed_affixes = set(affixes) | self._active_general_affixes(mode)
        if not set(required_affixes) <= allowed_affixes:
            raise ValueError("必须词条必须属于有效词条")
        blacklist_exceptions = list(blacklist_exceptions or []) if mode == "deepnight" else []
        excluded = list(dict.fromkeys(excluded_affixes or []))
        if not set(excluded) <= self._active_general_affixes(mode) or set(excluded) & set(affixes):
            raise ValueError("排除词条必须来自通用预设，且不能同时作为专属词条")
        # 创建预设
        preset_id = str(uuid.uuid4())
        preset_type = PRESET_TYPE_NORMAL_WHITELIST if mode == "normal" else PRESET_TYPE_DEEPNIGHT_WHITELIST

        preset = {
            "id": preset_id,
            "name": name,
            "type": preset_type,
            "affixes": list(affixes),
            "affix_tiers": self._checked_tiers(affixes, affix_tiers,
                                               self._active_general_affixes(mode)) or
                           {a: "secondary" for a in affixes},
            "excluded_affixes": excluded,
            "required_affixes": required_affixes,
            "blacklist_exceptions": blacklist_exceptions,
            "is_general": False,
            "is_active": True
        }
        if grouped_supplied:
            preset["required_affix_groups"] = required_affix_groups
        if mode == "deepnight":
            preset["negative_tiers"] = self._checked_negative_tiers(negative_tiers) or {}

        if mode == "normal":
            preset["official_scores"] = self._checked_official_scores(official_scores)
            self.normal_dedicated[preset_id] = preset
        elif mode == "deepnight":
            self.deepnight_whitelist_dedicated[preset_id] = preset

        self.save_presets()
        return preset_id

    def update_dedicated_preset(self, mode: str, preset_id: str, name: str = None, affixes: List[str] = None,
                                required_affixes=None, blacklist_exceptions=None,
                                required_affix_groups=None, affix_tiers=None,
                                negative_tiers=None, excluded_affixes=None,
                                official_scores=None):
        """更新专用预设"""
        presets = self.get_dedicated_presets(mode)

        if preset_id not in presets:
            raise ValueError(f"预设不存在: {preset_id}")

        preset = presets[preset_id]
        useful = list(affixes) if affixes is not None else preset["affixes"]
        grouped_existing = "required_affix_groups" in preset
        if required_affix_groups is not None:
            groups = self._validate_required_groups(required_affix_groups)
            required = [a for group in groups for a in group]
        elif required_affixes is not None:
            required = list(required_affixes)
            groups = [[a] for a in required]
        elif grouped_existing:
            groups = self._validate_required_groups(preset.get("required_affix_groups"))
            required = [a for group in groups for a in group]
        else:
            required = (list(preset.get("required_affixes", [])) if affixes is None else
                        [a for a in preset.get("required_affixes", []) if a in useful])
            groups = [[a] for a in required]
        allowed_affixes = set(useful) | self._active_general_affixes(mode)
        if (required_affix_groups is not None or required_affixes is not None or
                affixes is not None) and not set(required) <= allowed_affixes:
            raise ValueError("必须词条必须属于有效词条")
        if name is not None:
            preset["name"] = name
        preset["affixes"] = useful
        grades = self._checked_tiers(useful, affix_tiers, self._active_general_affixes(mode))
        preset["affix_tiers"] = (grades if grades is not None else
                                 {a: t for a, t in preset.get("affix_tiers", {}).items()
                                  if a in set(useful) | self._active_general_affixes(mode)})
        preset["required_affixes"] = required
        if (required_affix_groups is not None or grouped_existing or
                "required_affix_groups" in preset):
            preset["required_affix_groups"] = groups
        if blacklist_exceptions is not None:
            preset["blacklist_exceptions"] = list(blacklist_exceptions) if mode == "deepnight" else []
        if negative_tiers is not None and mode == "deepnight":
            preset["negative_tiers"] = self._checked_negative_tiers(negative_tiers)
        if mode == 'normal' and official_scores is not None:
            preset['official_scores'] = self._checked_official_scores(official_scores)
        if excluded_affixes is not None:
            excluded = list(dict.fromkeys(excluded_affixes))
            if not set(excluded) <= self._active_general_affixes(mode) or set(excluded) & set(useful):
                raise ValueError("排除词条必须来自通用预设，且不能同时作为专属词条")
            preset["excluded_affixes"] = excluded

        self.save_presets()

    @staticmethod
    def _checked_official_scores(scores):
        if scores is None:
            return {}
        if not isinstance(scores, dict) or any(
                not str(key).isdigit() or isinstance(value, bool) or
                not isinstance(value, int) or not -999 <= value <= 999
                for key, value in scores.items()):
            raise ValueError('官方遗物分数无效')
        return {str(key): value for key, value in scores.items()}

    @staticmethod
    def _validate_required_groups(groups):
        if not isinstance(groups, list):
            raise ValueError("必须词条组格式无效")
        result = []
        for group in groups:
            if not isinstance(group, list) or not group:
                raise ValueError("必须词条组不能为空")
            if not all(isinstance(entry, str) and entry for entry in group):
                raise ValueError("必须词条组包含无效词条")
            result.append(list(dict.fromkeys(group)))
        return result

    def _active_general_affixes(self, mode: str) -> set:
        general = self.get_general_preset(mode)
        if not general or not general.get("is_active", True):
            return set()
        affixes = general.get("affixes", [])
        return set(affixes) if isinstance(affixes, list) else set()

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

    def move_preset(self, mode: str, preset_id: str, direction: str):
        """
        移动预设位置

        Args:
            mode: 预设模式 ("normal" 或 "deepnight")
            preset_id: 预设ID
            direction: 移动方向 ("up" 或 "down")
        """
        presets = self.get_dedicated_presets(mode)
        preset_ids = list(presets.keys())

        if preset_id not in preset_ids:
            return

        current_index = preset_ids.index(preset_id)

        if direction == "up" and current_index > 0:
            # 交换位置
            preset_ids[current_index], preset_ids[current_index - 1] = preset_ids[current_index - 1], preset_ids[current_index]
        elif direction == "down" and current_index < len(preset_ids) - 1:
            # 交换位置
            preset_ids[current_index], preset_ids[current_index + 1] = preset_ids[current_index + 1], preset_ids[current_index]
        else:
            return

        # 重建预设字典以保持新的顺序
        new_presets = {}
        for pid in preset_ids:
            new_presets[pid] = presets[pid]

        if mode == "normal":
            self.normal_dedicated = new_presets
        elif mode == "deepnight":
            self.deepnight_whitelist_dedicated = new_presets

        self.save_presets()

    # ==================== 黑名单预设操作 ====================

    def get_blacklist_preset(self) -> Optional[Dict]:
        """获取黑名单预设"""
        return self.deepnight_blacklist

    def update_blacklist_preset(self, affixes: List[str]):
        """更新黑名单预设的词条"""
        self.deepnight_blacklist["affixes"] = affixes
        self.save_presets()
