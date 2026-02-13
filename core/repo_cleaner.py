"""
仓库清理逻辑控制器
负责主清理流程、跳过决策、词条匹配和操作执行
"""

import time
import cv2
import numpy as np
import pyautogui
import pydirectinput
import pygetwindow as gw
from typing import Dict, List, Optional
from rapidfuzz import fuzz

from core.preset_manager import PresetManager
from core.ocr_engine import OCREngine
from core.relic_detector import RelicDetector, RELIC_STATE_LIGHT, RELIC_STATE_DARK_F, RELIC_STATE_DARK_FE, RELIC_STATE_DARK_E, RELIC_STATE_DARK_O
from core.automation import RepositoryFilter

# 遗物状态中文名称映射
RELIC_STATE_NAMES = {
    RELIC_STATE_LIGHT: "自由售出",
    RELIC_STATE_DARK_E: "已装备",
    RELIC_STATE_DARK_F: "已收藏",
    RELIC_STATE_DARK_FE: "已装备且收藏",
    RELIC_STATE_DARK_O: "官方遗物"
}


class RepoCleaner:
    """仓库清理控制器"""

    def __init__(self, preset_manager: PresetManager, ocr_engine: OCREngine, relic_detector: RelicDetector):
        """
        初始化清理控制器

        Args:
            preset_manager: 预设管理器
            ocr_engine: OCR引擎
            relic_detector: 遗物检测器
        """
        self.preset_manager = preset_manager
        self.ocr_engine = ocr_engine
        self.relic_detector = relic_detector

        # 仓库筛选器（传入OCR引擎用于界面验证）
        self.repository_filter = RepositoryFilter(ocr_engine)

        # 游戏窗口
        self.game_window = None

        # 清理状态
        self.is_running = False
        self.is_paused = False
        self.pending_sell_count = 0  # 待售出数量（已选中但未完成售出）

        # 统计信息
        self.stats = {
            "total_detected": 0,
            "qualified": 0,
            "unqualified": 0,
            "skipped": 0,
            "sold": 0,
            "favorited": 0,
            "unfavorited": 0
        }

        # 合格遗物记录
        self.qualified_relics = []

    def start_cleaning(self, mode: str, cleaning_mode: str, max_relics: int,
                      allow_operate_favorited: bool, require_double: bool,
                      log_callback=None):
        """
        开始清理

        Args:
            mode: 模式 ("normal" 或 "deepnight")
            cleaning_mode: 清理模式 ("sell" 或 "favorite")
            max_relics: 最大检测数量 (0=无限)
            allow_operate_favorited: 是否允许对被收藏遗物操作
            require_double: 双有效模式 (True=2条匹配, False=3条匹配)
            log_callback: 日志回调函数
        """
        self.is_running = True
        self.is_paused = False
        self.pending_sell_count = 0
        self._reset_stats()
        self.qualified_relics = []

        # 日志函数
        def log(message: str, level: str = "INFO"):
            if log_callback:
                log_callback(message, level)
            else:
                print(f"[{level}] {message}")

        try:
            # 0. 检测游戏窗口
            log("正在检测游戏窗口...", "INFO")
            self.game_window = self._find_game_window()
            if not self.game_window:
                log("未找到游戏窗口", "ERROR")
            else:
                log(f"找到游戏窗口: {self.game_window.title} ({self.game_window.width}x{self.game_window.height})", "SUCCESS")

            # 1. 等待3秒，给用户时间切换到游戏界面
            log("等待3秒，请切换到游戏界面...", "INFO")
            time.sleep(3.0)

            # 2. 应用筛选
            log("正在应用遗物筛选...", "INFO")
            if not self.repository_filter.apply_filter(mode):
                log("遗物筛选失败，请确保在遗物仪式界面", "ERROR")
                return
            log("遗物筛选成功", "SUCCESS")
            time.sleep(1.0)

            # 3. 获取预设
            general_preset = self.preset_manager.get_general_preset(mode)
            dedicated_presets = self.preset_manager.get_active_dedicated_presets(mode)
            blacklist_preset = self.preset_manager.get_blacklist_preset() if mode == "deepnight" else None

            log(f"通用预设: {len(general_preset['affixes'])}条词条", "INFO")
            log(f"专用预设: {len(dedicated_presets)}个", "INFO")

            # 4. 主循环
            while self.is_running:
                if self.is_paused:
                    time.sleep(0.1)
                    continue

                # 检查数量限制
                if max_relics > 0 and self.stats["total_detected"] >= max_relics:
                    log(f"已达到最大检测数量: {max_relics}", "SUCCESS")
                    break

                # 截图（只截取游戏窗口）
                image = self._capture_game_window()
                if image is None:
                    log("截图失败，跳过", "ERROR")
                    pydirectinput.press('right')
                    time.sleep(0.5)
                    continue

                # 状态检测
                relic_state = self.relic_detector.detect_state(image)
                self.stats["total_detected"] += 1

                state_name = RELIC_STATE_NAMES.get(relic_state, relic_state)
                log(f"[{self.stats['total_detected']}] 遗物状态: {state_name}", "INFO")

                # 跳过决策
                should_skip = self._should_skip_relic(relic_state, cleaning_mode, allow_operate_favorited)

                if should_skip:
                    log("跳过该遗物", "INFO")
                    self.stats["skipped"] += 1
                    pydirectinput.press('right')
                    time.sleep(0.5)
                    continue

                # OCR识别
                log("识别词条中...", "INFO")
                ocr_result = self.ocr_engine.recognize_with_classification(image, mode)

                if not ocr_result["success"]:
                    log("OCR识别失败（重试3次后仍未识别到任何词条），停止清理", "ERROR")
                    log("可能原因：不在遗物界面或界面显示异常", "ERROR")
                    break

                log(f"识别到 {ocr_result['positive_count']} 条正面词条, {ocr_result['negative_count']} 条负面词条", "INFO")

                # 输出完整词条信息
                for affix in ocr_result["affixes"]:
                    affix_type = "正面" if affix["is_positive"] else "负面"
                    log(f"  [{affix_type}] {affix['cleaned_text']} (相似度: {affix.get('similarity', 0):.2f})", "INFO")

                # 词条匹配
                match_result = self._match_affixes(
                    ocr_result,
                    general_preset,
                    dedicated_presets,
                    blacklist_preset,
                    require_double
                )

                if match_result["qualified"]:
                    log(f"合格遗物 ({match_result['reason']})", "SUCCESS")
                    self.stats["qualified"] += 1

                    # 保存合格遗物词条
                    qualified_relic_info = {
                        "index": self.stats["total_detected"],
                        "state": relic_state,
                        "affixes": ocr_result["affixes"],
                        "match_result": match_result
                    }
                    self.qualified_relics.append(qualified_relic_info)
                else:
                    log(f"不合格遗物 ({match_result['reason']})", "INFO")
                    self.stats["unqualified"] += 1

                # 操作执行
                need_move_right = self._execute_action(relic_state, match_result["qualified"], cleaning_mode, log)

                # 移动到下一遗物（如果需要）
                if need_move_right:
                    pydirectinput.press('right')
                    time.sleep(0.5)

            # 清理完成
            log("清理完成", "SUCCESS")
            self._print_stats(log)

        except Exception as e:
            log(f"清理过程出错: {e}", "ERROR")
        finally:
            # 检查是否手动停止且有待售出的遗物
            if not self.is_running and self.pending_sell_count > 0:
                log("=" * 50, "WARNING")
                log("检测到手动停止", "WARNING")
                log(f"游戏内已选中 {self.pending_sell_count} 个遗物待售出", "WARNING")
                log("请手动完成售出操作：", "WARNING")
                log("  1. 按数字键3打开售出界面", "INFO")
                log("  2. 按F键确认售出", "INFO")
                log("=" * 50, "WARNING")

            self.is_running = False
            self.pending_sell_count = 0

    def stop_cleaning(self):
        """停止清理"""
        self.is_running = False

    def pause_cleaning(self):
        """暂停清理"""
        self.is_paused = True

    def resume_cleaning(self):
        """恢复清理"""
        self.is_paused = False

    def _reset_stats(self):
        """重置统计信息"""
        self.stats = {
            "total_detected": 0,
            "qualified": 0,
            "unqualified": 0,
            "skipped": 0,
            "sold": 0,
            "favorited": 0,
            "unfavorited": 0
        }

    def _find_game_window(self) -> Optional[gw.Win32Window]:
        """
        查找包含NIGHTREIGN的游戏窗口

        Returns:
            游戏窗口对象，如果未找到则返回None
        """
        try:
            windows = gw.getAllWindows()
            for window in windows:
                if 'NIGHTREIGN' in window.title.upper():
                    return window
            return None
        except Exception as e:
            print(f"[警告] 查找游戏窗口失败: {e}")
            return None

    def _capture_game_window(self) -> Optional[np.ndarray]:
        """
        截取游戏窗口图像

        Returns:
            BGR格式的numpy数组，如果失败则返回None
        """
        try:
            if self.game_window:
                # 截取游戏窗口区域
                screenshot = pyautogui.screenshot(region=(
                    self.game_window.left,
                    self.game_window.top,
                    self.game_window.width,
                    self.game_window.height
                ))
            else:
                # 回退到全屏截图
                screenshot = pyautogui.screenshot()

            return cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)
        except Exception as e:
            print(f"[错误] 截图失败: {e}")
            return None

    def _should_skip_relic(self, relic_state: str, cleaning_mode: str, allow_favorited: bool) -> bool:
        """
        决定是否跳过该遗物

        Returns:
            True: 跳过
            False: 不跳过，需要处理
        """
        if cleaning_mode == "sell":
            if relic_state == RELIC_STATE_LIGHT:
                return False
            elif relic_state in [RELIC_STATE_DARK_F, RELIC_STATE_DARK_FE]:
                return not allow_favorited
            else:  # E, O
                return True

        elif cleaning_mode == "favorite":
            if relic_state == RELIC_STATE_LIGHT:
                return False
            elif relic_state == RELIC_STATE_DARK_F:
                return True
            elif relic_state == RELIC_STATE_DARK_FE:
                return not allow_favorited
            else:  # E, O
                return False

        return True

    def _match_affixes(self, ocr_result: Dict, general_preset: Dict,
                      dedicated_presets: List[Dict], blacklist_preset: Optional[Dict],
                      require_double: bool) -> Dict:
        """
        匹配词条

        Returns:
            {
                "qualified": bool,
                "reason": str,
                "positive_matches": int,
                "negative_matches": int,
                "details": list
            }
        """
        pos_affixes = [a for a in ocr_result["affixes"] if a["is_positive"]]
        neg_affixes = [a for a in ocr_result["affixes"] if not a["is_positive"]]

        # 1. 单正面词条检查
        if len(pos_affixes) == 1:
            return {
                "qualified": False,
                "reason": "single_positive",
                "positive_matches": 0,
                "negative_matches": 0,
                "details": []
            }

        # 2. 黑名单匹配（深夜模式）
        if blacklist_preset:
            neg_matched_count = 0
            for neg in neg_affixes:
                for vocab in blacklist_preset["affixes"]:
                    similarity = fuzz.ratio(neg["cleaned_text"], vocab) / 100.0
                    if similarity > 0.9:
                        neg_matched_count += 1
                        break
                if neg_matched_count > 0:
                    break

            if neg_matched_count > 0:
                return {
                    "qualified": False,
                    "reason": "blacklist_match",
                    "positive_matches": 0,
                    "negative_matches": neg_matched_count,
                    "details": []
                }

        # 3. 白名单匹配（通用 + 任一一套专用）
        required_matches = 2 if require_double else 3
        best_match = {"count": 0, "preset": None, "details": []}

        # 通用 + 每套专用逐一尝试
        if general_preset:
            general_vocabs = set(general_preset["affixes"])

            for preset in dedicated_presets:
                combined_vocabs = general_vocabs | set(preset["affixes"])
                count, details = self._count_positive_matches(pos_affixes, combined_vocabs)

                if count > best_match["count"]:
                    best_match = {
                        "count": count,
                        "preset": f"{general_preset['name']}+{preset['name']}",
                        "details": details
                    }

        # 4. 合格判断
        qualified = best_match["count"] >= required_matches

        return {
            "qualified": qualified,
            "reason": f"{best_match['preset']}_match" if qualified else "insufficient_matches",
            "positive_matches": best_match["count"],
            "negative_matches": 0,
            "details": best_match["details"]
        }

    def _count_positive_matches(self, pos_affixes: List, vocab_set: set) -> tuple:
        """计算正面词条与词条集合的匹配数"""
        count = 0
        details = []

        for affix in pos_affixes:
            for vocab in vocab_set:
                similarity = fuzz.ratio(affix["cleaned_text"], vocab) / 100.0
                if similarity > 0.9:
                    count += 1
                    details.append({
                        "affix": affix["cleaned_text"],
                        "matched_vocab": vocab,
                        "similarity": similarity
                    })
                    break  # 每条词条只匹配一次

        return count, details

    def _execute_action(self, relic_state: str, is_qualified: bool, cleaning_mode: str, log) -> bool:
        """
        执行操作

        Returns:
            bool: 是否需要按右方向键移动到下一遗物
        """
        if cleaning_mode == "sell":
            if is_qualified:
                # 合格遗物跳过
                log("合格遗物，跳过", "INFO")
                return True  # 需要按右方向键
            else:
                # 不合格遗物售出
                if relic_state == RELIC_STATE_LIGHT:
                    log("标记售出", "INFO")
                    pydirectinput.press('f')
                    self.stats["sold"] += 1
                    self.pending_sell_count += 1
                    time.sleep(0.2)
                    return False  # 按f后会自动跳转，不需要按右方向键
                elif relic_state == RELIC_STATE_DARK_F:
                    log("取消收藏后标记售出", "INFO")
                    pydirectinput.press('2')  # 取消收藏
                    time.sleep(0.3)
                    pydirectinput.press('f')  # 标记售出
                    self.stats["unfavorited"] += 1
                    self.stats["sold"] += 1
                    self.pending_sell_count += 1
                    time.sleep(0.2)
                    return False  # 按f后会自动跳转，不需要按右方向键

        elif cleaning_mode == "favorite":
            if is_qualified:
                # 合格遗物收藏
                if relic_state == RELIC_STATE_LIGHT:
                    log("收藏遗物", "INFO")
                    pydirectinput.press('2')
                    self.stats["favorited"] += 1
                    time.sleep(0.3)
                elif relic_state == RELIC_STATE_DARK_F:
                    log("已收藏，跳过", "INFO")
            else:
                # 不合格遗物取消收藏
                if relic_state == RELIC_STATE_DARK_F:
                    log("取消收藏", "INFO")
                    pydirectinput.press('2')
                    self.stats["unfavorited"] += 1
                    time.sleep(0.3)

        return True  # 默认需要按右方向键

    def _print_stats(self, log):
        """打印统计信息"""
        log("=" * 50, "INFO")
        log("清理统计", "INFO")
        log("=" * 50, "INFO")
        log(f"总检测数: {self.stats['total_detected']}", "INFO")
        log(f"合格: {self.stats['qualified']}", "SUCCESS")
        log(f"不合格: {self.stats['unqualified']}", "INFO")
        log(f"跳过: {self.stats['skipped']}", "INFO")
        log(f"售出: {self.stats['sold']}", "INFO")
        log(f"收藏: {self.stats['favorited']}", "INFO")
        log(f"取消收藏: {self.stats['unfavorited']}", "INFO")
        log("=" * 50, "INFO")
