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

from core.preset_manager import PresetManager
from core.ocr_engine import OCREngine
from core.relic_detector import RelicDetector, RELIC_STATE_LIGHT, RELIC_STATE_DARK_F, RELIC_STATE_DARK_FE, RELIC_STATE_DARK_E, RELIC_STATE_DARK_O
from core.automation import RepositoryFilter
from core.utils import log_debug

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

    def __init__(self, preset_manager: PresetManager, ocr_engine: OCREngine, relic_detector: RelicDetector, settings: dict = None):
        """
        初始化清理控制器

        Args:
            preset_manager: 预设管理器
            ocr_engine: OCR引擎
            relic_detector: 遗物检测器
            settings: 设置字典
        """
        self.preset_manager = preset_manager
        self.ocr_engine = ocr_engine
        self.relic_detector = relic_detector
        self.settings = settings or {}

        # 仓库筛选器（传入OCR引擎和设置）
        self.repository_filter = RepositoryFilter(ocr_engine, settings)

        # 游戏窗口
        self.game_window = None

        # 清理状态
        self.is_running = False
        self.is_paused = False
        self.pending_sell_count = 0  # 待售出数量（已选中但未完成售出）
        self.normal_stop = False  # 是否正常停止（达到最大数量或正常完成）

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
        self.normal_stop = False  # 重置正常停止标志
        self._reset_stats()
        self.qualified_relics = []

        # 日志函数
        def log(message: str, level: str = "INFO"):
            if log_callback:
                log_callback(message, level)
            else:
                log_debug(f"[{level}] {message}")

        try:
            # 0. 检测游戏窗口
            log("正在检测游戏窗口...", "INFO")
            self.game_window = self._find_game_window()
            if not self.game_window:
                log("未找到游戏窗口", "ERROR")

            # 1. 等待3秒，给用户时间切换到游戏界面
            log("等待3秒，请切换到游戏遗物仪式界面...", "INFO")
            for _ in range(30):  # 30 * 0.1 = 3秒，可中断
                if not self.is_running:
                    return
                time.sleep(0.1)

            # 2. 应用筛选
            if not self.is_running:
                return
            log("正在应用遗物筛选...", "INFO")
            if not self.repository_filter.apply_filter(mode):
                log("遗物筛选失败", "ERROR")
                log("可能原因：", "ERROR")
                log("  1. 未在遗物仪式界面", "INFO")
                log("  2. 游戏窗口未找到或无法获取客户区信息", "INFO")
                self.is_running = False  # 标记为停止状态
                return
            log("遗物筛选成功", "SUCCESS")
            for _ in range(10):  # 10 * 0.1 = 1秒，可中断
                if not self.is_running:
                    return
                time.sleep(0.1)

            # 2.5. 自动检测遗物数量（如果 max_relics == 0）
            if not self.is_running:
                return
            if max_relics == 0:
                log("正在自动检测遗物数量...", "INFO")
                detected_count = self.repository_filter.detect_relic_count()
                if detected_count > 0:
                    max_relics = detected_count
                    log(f"检测到遗物数量: {max_relics}", "SUCCESS")
                else:
                    log("自动检测失败，使用默认值 100", "WARNING")
                    max_relics = 100

            # 3. 获取预设
            if not self.is_running:
                return
            general_preset = self.preset_manager.get_general_preset(mode)
            dedicated_presets = self.preset_manager.get_active_dedicated_presets(mode)
            blacklist_preset = self.preset_manager.get_blacklist_preset() if mode == "deepnight" else None

            log(f"通用预设: {len(general_preset['affixes'])}条词条", "INFO")
            log(f"专用预设: {len(dedicated_presets)}个", "INFO")

            # 用于检测卡住的变量
            last_relic_hash = None  # 上一个遗物的特征哈希

            # 4. 主循环
            while self.is_running:
                if self.is_paused:
                    time.sleep(0.1)
                    continue

                t_relic_start = time.time()

                # 检查数量限制
                if max_relics > 0 and self.stats["total_detected"] >= max_relics:
                    log(f"已达到最大检测数量: {max_relics}", "SUCCESS")
                    self.normal_stop = True  # 正常停止
                    break

                # 截图（使用 RepositoryFilter 的截图方法，确保截取客户区）
                t_start = time.time()
                image = self.repository_filter._capture_game_window()
                t_capture = time.time() - t_start
                if image is None:
                    log("截图失败，跳过", "ERROR")
                    pydirectinput.press('right')
                    continue

                # 状态检测
                t_start = time.time()
                relic_state = self.relic_detector.detect_state(image, 1.0, self.repository_filter.scale_x, self.repository_filter.scale_y)
                t_detect = time.time() - t_start
                self.stats["total_detected"] += 1

                state_name = RELIC_STATE_NAMES.get(relic_state, relic_state)
                log(f"[{self.stats['total_detected']}] 遗物状态: {state_name} (截图:{t_capture:.3f}s 检测:{t_detect:.3f}s)", "INFO")

                # 跳过决策
                should_skip = self._should_skip_relic(relic_state, cleaning_mode, allow_operate_favorited)

                if should_skip:
                    log("跳过该遗物", "INFO")
                    self.stats["skipped"] += 1
                    pydirectinput.press('right')
                    continue

                # OCR识别（使用6行单行ROI）
                t_start = time.time()
                line_images = self.repository_filter.capture_line_rois()
                t_roi = time.time() - t_start

                # 对6行图像分别进行单行识别
                t_start = time.time()
                all_text = []
                for line_image in line_images:
                    text, _ = self.ocr_engine.recognize_single_line(line_image)
                    if text:
                        all_text.append(text)

                # 拼接所有文本
                combined_text = '\n'.join(all_text)

                # 使用 recognize_with_classification 处理合并后的文本
                # 注意：这里传入的是文本而不是图像，需要修改方法
                ocr_result = self.ocr_engine.recognize_with_classification_from_lines(line_images, mode)
                t_ocr = time.time() - t_start
                log(f"识别词条完成 (截取ROI:{t_roi:.3f}s OCR:{t_ocr:.3f}s)", "INFO")

                if not ocr_result["success"]:
                    # 检查是否是手动停止导致的识别失败
                    if self.is_running:
                        # 正常运行中的识别失败，输出错误信息
                        log("OCR识别失败（重试3次后仍未识别到任何词条），停止清理", "ERROR")
                        log("可能原因：不在遗物界面或界面显示异常", "ERROR")
                        self.is_running = False  # 标记为意外停止
                    else:
                        # 手动停止导致的识别失败，不输出错误
                        log("检测到停止信号，结束清理", "INFO")
                    break

                # 计算当前遗物特征（词条文本哈希）
                affix_texts = [affix["cleaned_text"] for affix in ocr_result["affixes"]]
                current_relic_hash = hash(tuple(sorted(affix_texts)))

                # 检测是否卡住（连续两次识别到相同遗物）
                if last_relic_hash is not None and current_relic_hash == last_relic_hash:
                    log("检测到重复遗物，再次尝试按F售出...", "WARNING")
                    pydirectinput.press('f')

                    # 超时等待，给游戏时间响应
                    for _ in range(10):  # 1秒
                        if not self.is_running:
                            return
                        time.sleep(0.1)

                    # 重新OCR识别确认
                    line_images_retry = self.repository_filter.capture_line_rois()
                    ocr_result_retry = self.ocr_engine.recognize_with_classification_from_lines(line_images_retry, mode)

                    if ocr_result_retry["success"]:
                        affix_texts_retry = [affix["cleaned_text"] for affix in ocr_result_retry["affixes"]]
                        retry_hash = hash(tuple(sorted(affix_texts_retry)))

                        if retry_hash == current_relic_hash:
                            # 按F后仍然是同一个遗物，确认是官方遗物
                            log("确认为官方遗物（无法售出），按右方向键跳过", "WARNING")
                            self.stats["total_detected"] -= 1
                            pydirectinput.press('right')
                            last_relic_hash = None
                            continue
                        else:
                            # 按F成功，界面已跳转到新遗物
                            log("售出成功，界面已跳转到新遗物", "INFO")
                            self.stats["total_detected"] -= 1
                            last_relic_hash = None
                            continue
                    else:
                        # 重试OCR失败，跳过
                        log("重新识别失败，跳过", "ERROR")
                        self.stats["total_detected"] -= 1
                        pydirectinput.press('right')
                        last_relic_hash = None
                        continue

                # 更新上一个遗物哈希
                last_relic_hash = current_relic_hash

                log(f"识别到 {ocr_result['positive_count']} 条正面词条, {ocr_result['negative_count']} 条负面词条", "INFO")

                # 输出完整词条信息
                for affix in ocr_result["affixes"]:
                    affix_type = "正面" if affix["is_positive"] else "负面"
                    log(f"  [{affix_type}] {affix['cleaned_text']} (相似度: {affix.get('similarity', 0):.2f})", "INFO")

                # 词条匹配
                t_start = time.time()
                match_result = self._match_affixes(
                    ocr_result,
                    general_preset,
                    dedicated_presets,
                    blacklist_preset,
                    require_double
                )
                t_match = time.time() - t_start

                if match_result["qualified"]:
                    log(f"合格遗物 ({match_result['reason']}) (匹配:{t_match:.3f}s)", "SUCCESS")
                    self.stats["qualified"] += 1
                else:
                    log(f"不合格遗物 ({match_result['reason']})", "INFO")
                    self.stats["unqualified"] += 1

                # 操作执行
                t_start = time.time()
                need_move_right = self._execute_action(relic_state, match_result["qualified"], cleaning_mode, log)
                t_action = time.time() - t_start

                # 根据清理模式和操作结果，记录遗物
                # 注意：售出模式下，只有在最后确认售出后才会记录，这里不记录
                if cleaning_mode == "favorite":
                    # 收藏模式：只记录合格的（被收藏的）遗物（仅LIGHT状态会被实际收藏）
                    if match_result["qualified"] and relic_state == RELIC_STATE_LIGHT:
                        qualified_relic_info = {
                            "index": self.stats["total_detected"],
                            "affixes": ocr_result["affixes"]
                        }
                        self.qualified_relics.append(qualified_relic_info)
                elif cleaning_mode == "sell":
                    # 售出模式：暂存待售出的遗物信息，等确认售出后再记录
                    if not match_result["qualified"] and relic_state in [RELIC_STATE_LIGHT, RELIC_STATE_DARK_F]:
                        pending_relic_info = {
                            "index": self.stats["total_detected"],
                            "affixes": ocr_result["affixes"]
                        }
                        # 暂存到待售出列表
                        if not hasattr(self, 'pending_sell_relics'):
                            self.pending_sell_relics = []
                        self.pending_sell_relics.append(pending_relic_info)

                # 移动到下一遗物（如果需要）
                if need_move_right:
                    pydirectinput.press('right')

                t_relic_total = time.time() - t_relic_start
                log(f"[耗时] 总计:{t_relic_total:.3f}s | 截图:{t_capture:.3f}s 检测:{t_detect:.3f}s ROI:{t_roi:.3f}s OCR:{t_ocr:.3f}s 匹配:{t_match:.3f}s 操作:{t_action:.3f}s", "DEBUG")

            # 清理完成
            if self.is_running:
                # 正常完成
                log("清理完成", "SUCCESS")
                self._print_stats(log)
            else:
                # 手动停止
                log("清理已停止", "INFO")
                self._print_stats(log)

            # 自动完成售出操作（仅在正常停止时执行）
            if self.normal_stop and cleaning_mode == "sell" and self.pending_sell_count > 0:
                log(f"执行售出操作 ({self.pending_sell_count}个遗物)...", "INFO")
                pydirectinput.press('3')  # 打开售出界面
                time.sleep(0.5)
                pydirectinput.press('f')  # 确认售出
                time.sleep(0.5)
                log("售出完成", "SUCCESS")

                # 确认售出后，将待售出的遗物转移到已售出列表
                if hasattr(self, 'pending_sell_relics') and self.pending_sell_relics:
                    self.qualified_relics.extend(self.pending_sell_relics)
                    log(f"已记录 {len(self.pending_sell_relics)} 个售出遗物到仪表盘", "INFO")
                    self.pending_sell_relics = []

                self.pending_sell_count = 0

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
        # 重置待售出遗物列表
        self.pending_sell_relics = []

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
            log_debug(f"[警告] 查找游戏窗口失败: {e}")
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
                return False  # 自由状态，可售出
            elif relic_state == RELIC_STATE_DARK_F:
                return not allow_favorited  # 仅收藏，根据设置决定
            elif relic_state == RELIC_STATE_DARK_E:
                return True  # 已装备，无法售出
            elif relic_state == RELIC_STATE_DARK_FE:
                return True  # 已装备且收藏，无法售出（装备的遗物无法售出）
            else:  # O (官方遗物)
                return True

        elif cleaning_mode == "favorite":
            if relic_state == RELIC_STATE_LIGHT:
                return False  # 自由状态，可收藏
            elif relic_state == RELIC_STATE_DARK_F:
                return not allow_favorited  # 已收藏，根据设置决定是否可取消
            elif relic_state == RELIC_STATE_DARK_FE:
                return not allow_favorited  # 已装备且收藏，根据设置决定是否可取消
            else:  # E, O
                return False  # 已装备或官方遗物，可收藏

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
            blacklist_set = set(blacklist_preset["affixes"])
            for neg in neg_affixes:
                if neg["cleaned_text"] in blacklist_set:
                    neg_matched_count += 1
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

            # 如果有专用预设，尝试通用+专用的组合
            if dedicated_presets:
                for preset in dedicated_presets:
                    combined_vocabs = general_vocabs | set(preset["affixes"])
                    count, details = self._count_positive_matches(pos_affixes, combined_vocabs)

                    if count > best_match["count"]:
                        best_match = {
                            "count": count,
                            "preset": f"{general_preset['name']}+{preset['name']}",
                            "details": details
                        }
            else:
                # 如果没有专用预设，只使用通用预设
                count, details = self._count_positive_matches(pos_affixes, general_vocabs)
                best_match = {
                    "count": count,
                    "preset": general_preset['name'],
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
            if affix["cleaned_text"] in vocab_set:
                count += 1
                details.append({
                    "affix": affix["cleaned_text"],
                    "matched_vocab": affix["cleaned_text"],
                    "similarity": 1.0
                })

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
                    return False  # 按f后会自动跳转，不需要按右方向键
                elif relic_state == RELIC_STATE_DARK_F:
                    log("取消收藏后标记售出", "INFO")
                    pydirectinput.press('2')  # 取消收藏
                    pydirectinput.press('f')  # 标记售出
                    self.stats["unfavorited"] += 1
                    self.stats["sold"] += 1
                    self.pending_sell_count += 1
                    return False  # 按f后会自动跳转，不需要按右方向键

        elif cleaning_mode == "favorite":
            if is_qualified:
                # 合格遗物收藏
                if relic_state == RELIC_STATE_LIGHT:
                    log("收藏遗物", "INFO")
                    pydirectinput.press('2')
                    self.stats["favorited"] += 1
                elif relic_state == RELIC_STATE_DARK_F:
                    log("已收藏，跳过", "INFO")
            else:
                # 不合格遗物取消收藏
                if relic_state == RELIC_STATE_DARK_F:
                    log("取消收藏", "INFO")
                    pydirectinput.press('2')
                    self.stats["unfavorited"] += 1

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
