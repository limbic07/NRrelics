"""
商店自动化模块
处理商人界面导航、遗物购买、词条识别和筛选
"""

import time
import numpy as np
import pydirectinput
import pyautogui
import keyboard
from datetime import datetime
from typing import Optional

from core.relic_matcher import match_relic, log_match
from core.relic_recorder import RelicRecorder
from core.relic_inventory import RelicInventory
from core.relic_color import recognize_color
from core.relic_scoring import normalize_scoring
from uuid import uuid4
from core.ocr_diagnostics import create_capture_session  # OCR 自动采集调试代码
from core.preset_manager import PresetManager
from core.utils import DEBUG_ENABLED, debug_timer, affix_recorder, log_debug



class ShopAutomation:
    """商店自动化"""

    # ROI坐标（基于1080p）
    BASE_WIDTH = 1920
    BASE_HEIGHT = 1080

    # 商人名称检测区域
    MERCHANT_NAME_REGION = (135, 40, 330, 80)

    # 遗物价格检测区域（基于1080p，用于OCR识别价格是否为600）
    RELIC_PRICE_REGION = (155, 942, 195, 964)

    # 遗物购买坐标（基于模式）
    RELIC_PURCHASE_COORDS = {
        ("new", "normal"): (145, 890),
        ("old", "normal"): (260, 890),
        ("new", "deepnight"): (375, 890),
        ("old", "deepnight"): (490, 890)
    }

    # 商人界面入口坐标
    MERCHANT_MENU_COORD = (170, 590)

    # 暗痕（货币）检测区域（基于1080p）
    CURRENCY_REGION = (480, 100, 595, 135)

    # 商店界面词条ROI（6行单行识别，基于1080p）
    SHOP_LINE_ROI_X_START = 666
    SHOP_LINE_ROI_X_END = 1300
    SHOP_LINE_ROI_COORDS = [
        # 第一组
        (612, 634),   # 第 1 行
        (634, 658),   # 第 2 行

        # 第二组
        (676, 700),   # 第 3 行
        (700, 722),   # 第 4 行

        # 第三组
        (740, 764),   # 第 5 行
        (764, 786),   # 第 6 行
    ]

    def __init__(self, ocr_engine, preset_manager, repo_filter, settings: dict):
        """
        初始化商店自动化

        Args:
            ocr_engine: OCR引擎实例
            preset_manager: 预设管理器实例
            repo_filter: RepositoryFilter实例（用于窗口捕获和坐标缩放）
            settings: 设置字典
        """
        self.ocr_engine = ocr_engine
        self.preset_manager = preset_manager
        self.repo_filter = repo_filter
        self.settings = settings
        self.recorder = RelicRecorder()
        self.inventory = RelicInventory()
        self.scan_id = uuid4().hex
        self.ocr_debug_session = None  # OCR 自动采集调试代码
        self.stop_reason = None

        # 运行状态
        self.is_running = False

        # 统计数据
        self.stats = {
            "total_purchased": 0,
            "qualified": 0,
            "unqualified": 0,
            "sold": 0
        }

        # 合格遗物列表
        self.qualified_relics = []

    def start_shopping(self, mode: str, version: str, stop_currency: int,
                      require_double: bool, log_callback=None, stats_callback=None,
                      sl_mode_enabled=False, sl_qualified_target=0,
                      save_manager=None, steam_id="", backup_path=""):
        """
        开始购买流程

        Args:
            mode: 模式 ("normal" 或 "deepnight")
            version: 版本 ("new" 或 "old")
            stop_currency: 停止购买次数
            require_double: 是否需要双有效（True=双有效，False=三有效）
            log_callback: 日志回调函数
            stats_callback: 统计回调函数
            sl_mode_enabled: 是否启用合格遗物数量停止模式
            sl_qualified_target: 目标合格遗物数量
            save_manager: SaveManager实例（SL模式需要）
            steam_id: Steam用户ID（SL模式需要）
            backup_path: 存档备份路径（SL模式需要）
        """
        self.stop_reason = None
        self.repo_filter.settings = self.settings
        self.is_running = True
        self.stats = {"total_purchased": 0, "qualified": 0, "unqualified": 0, "sold": 0}
        self.qualified_relics.clear()
        self.scan_id = uuid4().hex

        # SL模式相关
        self.sl_mode_enabled = sl_mode_enabled
        self.sl_qualified_target = sl_qualified_target
        self.save_manager = save_manager
        self.steam_id = steam_id
        self.backup_path = backup_path

        def log(message, level="INFO"):
            if log_callback:
                log_callback(message, level)
            else:
                log_debug(f"[{level}] {message}")

        # 注册按0停止的快捷键
        def on_zero_pressed():
            self.stop()
            log("收到停止信号，正在停止购买...", "WARNING")

        try:
            # ===== OCR 自动采集调试代码：每次购买建立独立会话；删除时移除此块及下方标记块 =====
            self.ocr_debug_session = create_capture_session(self.settings, "shop", mode, log)
            # ===== OCR 自动采集调试代码结束 =====
            keyboard.add_hotkey('0', on_zero_pressed)
            # 刷新窗口信息
            self.repo_filter.refresh_window_info()

            # 加载预设
            general_preset, dedicated_presets, blacklist_preset = self._load_presets(mode)

            # 等待3秒，给用户时间切换到游戏界面
            log("等待3秒，请切换到游戏商人界面...", "INFO")
            for _ in range(30):
                if not self.is_running:
                    return
                time.sleep(0.1)

            if not self.repo_filter.validate_game_resolution(log):
                self.stop_reason = "error"
                return

            # 1. 检测并进入商人界面
            if not self._enter_merchant_interface(log):
                self.stop_reason = self.stop_reason or "error"
                return

            # 2. 首次寻找遗物
            if not self._find_relic(log):
                log("首次寻找遗物失败", "ERROR")
                self.stop_reason = self.stop_reason or "error"
                return

            # 3. 循环购买
            first_purchase = True
            while self.is_running:
                # SL模式：检查合格遗物数量是否达标
                if self.sl_mode_enabled and self.sl_qualified_target > 0:
                    if self.stats["qualified"] >= self.sl_qualified_target:
                        log(f"已达到目标合格遗物数量 ({self.stats['qualified']}/{self.sl_qualified_target})", "SUCCESS")
                        self.stop_reason = "completed"
                        break

                    # 购买前检测暗痕，不足则执行存档恢复
                    current_currency = self._detect_currency(log)
                    if current_currency >= 0 and current_currency < 10000:
                        log(f"暗痕不足 ({current_currency} < 10000)，合格遗物 {self.stats['qualified']}/{self.sl_qualified_target}，执行存档恢复...", "WARNING")
                        if not self._execute_sl_operation(log):
                            log("存档恢复操作失败，停止购买", "ERROR")
                            self.stop_reason = self.stop_reason or "error"
                            break
                        # SL后重置购买统计（保留合格遗物数）
                        self.stats["total_purchased"] = 0
                        self.stats["unqualified"] = 0
                        self.stats["sold"] = 0
                        if stats_callback:
                            stats_callback(self.stats.copy())
                        # 重新进入商人界面
                        if not self._enter_merchant_interface(log):
                            log("SL后无法进入商人界面", "ERROR")
                            self.stop_reason = self.stop_reason or "error"
                            break
                        if not self._find_relic(log):
                            log("SL后无法找到遗物", "ERROR")
                            self.stop_reason = self.stop_reason or "error"
                            break
                        first_purchase = True
                        continue
                else:
                    # 原有停止条件：检测暗痕数量
                    if stop_currency > 0:
                        current_currency = self._detect_currency(log)
                        if current_currency >= 0 and current_currency < stop_currency:
                            log(f"暗痕不足（当前{current_currency} < 停止值{stop_currency}），停止购买", "WARNING")
                            self.stop_reason = "completed"
                            break

                # 4. 执行购买
                if first_purchase:
                    # 首次购买：点击遗物坐标
                    if not self._execute_first_purchase(mode, version, log):
                        self.stop_reason = self.stop_reason or "error"
                        break
                    first_purchase = False
                else:
                    # 后续购买：直接按F购买
                    if not self._execute_subsequent_purchase(log):
                        self.stop_reason = self.stop_reason or "error"
                        break

                # 5. 处理购买的10个遗物
                self._process_purchased_relics(
                    mode, require_double, general_preset, dedicated_presets,
                    blacklist_preset, log, stats_callback
                )

                # 6. 确认操作（按f）- 检查是否仍在运行
                if not self.is_running:
                    break
                pydirectinput.press('f')
                log("已确认操作", "INFO")

        except Exception as e:
            if self.stop_reason != "perfect_relic":
                self.stop_reason = "error"
            log(f"购买过程出错: {e}", "ERROR")
        finally:
            if self.stop_reason is None:
                self.stop_reason = "manual" if not self.is_running else "error"
            self.is_running = False
            try:
                keyboard.remove_hotkey('0')
            except:
                pass

            # 保存调试数据
            if DEBUG_ENABLED:
                # 保存词条记录
                affix_file = affix_recorder.save_to_file()

                # 输出耗时统计到终端
                summary = debug_timer.get_summary()
                if summary:
                    log_debug(summary)

                # 清空调试数据，为下一次运行做准备
                debug_timer.clear()
                affix_recorder.clear()

    def stop(self):
        """停止购买"""
        if self.stop_reason is None:
            self.stop_reason = "manual"
        self.is_running = False

    def _load_presets(self, mode: str):
        """加载预设"""
        general_preset = self.preset_manager.get_general_preset(mode)
        dedicated_presets = self.preset_manager.get_dedicated_presets(mode)
        blacklist_preset = None
        if mode == "deepnight":
            blacklist_preset = self.preset_manager.get_blacklist_preset()
        return general_preset, dedicated_presets, blacklist_preset

    def _get_window_offset(self):
        """获取游戏窗口客户区的屏幕坐标偏移"""
        client_rect = self.repo_filter._get_client_rect_screen_coords()
        if client_rect:
            return client_rect[0], client_rect[1]
        return 0, 0

    def _click_scaled_coord(self, base_coord):
        """点击缩放后的坐标（自动加上窗口偏移）"""
        x = int(base_coord[0] * self.repo_filter.scale_x)
        y = int(base_coord[1] * self.repo_filter.scale_y)
        offset_x, offset_y = self._get_window_offset()
        screen_x = offset_x + x
        screen_y = offset_y + y
        pyautogui.moveTo(screen_x, screen_y)
        time.sleep(0.1)
        pydirectinput.press('f')

    def _enter_merchant_interface(self, log) -> bool:
        """检测并进入商人界面"""
        if DEBUG_ENABLED:
            debug_timer.start("进入商人界面")

        # 截图检测商人名称
        image = self.repo_filter._capture_game_window()
        if image is None:
            log("无法捕获游戏窗口", "ERROR")
            return False

        # OCR识别商人名称区域
        merchant_region = self.repo_filter._capture_region(self.MERCHANT_NAME_REGION)
        result = self.ocr_engine.recognize_raw(merchant_region)
        if result["success"] and result["entries"]:
            text = "".join(result["entries"])
            if "小壶商人巴萨" in text or "商人" in text:
                log("已在商人界面", "INFO")
                if DEBUG_ENABLED:
                    elapsed = debug_timer.end("进入商人界面")
                    debug_timer.record("进入商人界面", elapsed)
                return True

        # 不在商人界面，尝试进入
        log("不在商人界面，尝试进入...", "INFO")
        pydirectinput.press('m')
        for _ in range(10):
            if not self.is_running:
                return False
            time.sleep(0.1)

        self._click_scaled_coord(self.MERCHANT_MENU_COORD)
        for _ in range(10):
            if not self.is_running:
                return False
            time.sleep(0.1)

        # 验证是否进入
        merchant_region = self.repo_filter._capture_region(self.MERCHANT_NAME_REGION)
        result = self.ocr_engine.recognize_raw(merchant_region)
        if result["success"] and result["entries"]:
            text = "".join(result["entries"])
            if "小壶商人巴萨" in text or "商人" in text:
                log("已进入商人界面", "INFO")
                if DEBUG_ENABLED:
                    elapsed = debug_timer.end("进入商人界面")
                    debug_timer.record("进入商人界面", elapsed)
                return True

        log("无法进入商人界面", "ERROR")
        if DEBUG_ENABLED:
            debug_timer.end("进入商人界面")
        return False

    def _detect_currency(self, log) -> int:
        """
        检测当前暗痕数量

        Returns:
            暗痕数量，识别失败返回-1
        """
        currency_region = self.repo_filter._capture_region(self.CURRENCY_REGION)
        if currency_region is None:
            log("无法捕获暗痕区域", "WARNING")
            return -1

        result = self.ocr_engine.recognize_raw(currency_region)
        if not result["success"] or not result["entries"]:
            log("暗痕识别失败", "WARNING")
            return -1

        # 提取数字
        text = "".join(result["entries"])
        # 移除非数字字符
        digits = "".join(c for c in text if c.isdigit())

        if not digits:
            log(f"暗痕文本无数字: {text}", "WARNING")
            return -1

        try:
            currency = int(digits)
            log(f"当前暗痕: {currency}", "INFO")
            return currency
        except ValueError:
            log(f"暗痕转换失败: {digits}", "WARNING")
            return -1

    def _capture_shop_line_rois(self, with_screen: bool = False) -> list:
        """
        截取商店界面6行单行ROI区域（用于单行OCR识别）

        Returns:
            6个单行图像的列表，每个图像是numpy数组
        """
        window_image = self.repo_filter._capture_game_window()
        if window_image is None:
            empty = [np.zeros((100, 100, 3), dtype=np.uint8) for _ in self.SHOP_LINE_ROI_COORDS]
            return (empty, None) if with_screen else empty

        line_images = []
        for y_start, y_end in self.SHOP_LINE_ROI_COORDS:
            region = (self.SHOP_LINE_ROI_X_START, y_start, self.SHOP_LINE_ROI_X_END, y_end)
            x1, y1, x2, y2 = self.repo_filter._scale_region(region)
            line_images.append(window_image[y1:y2, x1:x2])

        # ===== OCR 自动采集调试代码：返回与六行 ROI 同一次拍摄的完整截图 =====
        return (line_images, window_image) if with_screen else line_images
        # ===== OCR 自动采集调试代码结束 =====

    def _find_relic(self, log) -> bool:
        """滚动寻找遗物（通过OCR识别价格是否为600）"""
        if DEBUG_ENABLED:
            debug_timer.start("寻找遗物")

        max_scroll_attempts = 40
        for i in range(max_scroll_attempts):
            if not self.is_running:
                if DEBUG_ENABLED:
                    debug_timer.end("寻找遗物")
                return False

            pydirectinput.press('up')
            time.sleep(0.1)

            # 捕获价格区域并OCR识别
            price_region = self.repo_filter._capture_region(self.RELIC_PRICE_REGION)
            if price_region is not None and self._check_relic_price(price_region):
                log(f"找到遗物（滚动{i+1}次）", "INFO")
                if DEBUG_ENABLED:
                    elapsed = debug_timer.end("寻找遗物")
                    debug_timer.record("寻找遗物", elapsed)
                return True

        log("未找到遗物", "WARNING")
        if DEBUG_ENABLED:
            elapsed = debug_timer.end("寻找遗物")
            debug_timer.record("寻找遗物", elapsed)
        return False

    def _check_relic_price(self, region_image) -> bool:
        """通过OCR识别价格是否为600"""
        if region_image is None or region_image.size == 0:
            log_debug(f"[价格识别] 区域为空")
            return False

        result = self.ocr_engine.recognize_raw(region_image)
        if not result["success"] or not result["entries"]:
            log_debug(f"[价格识别] OCR识别失败")
            return False

        # 提取数字
        text = "".join(result["entries"])
        digits = "".join(c for c in text if c.isdigit())

        log_debug(f"[价格识别] 识别文本: {text}, 提取数字: {digits}")

        # 判断是否为600
        if digits == "600":
            log_debug(f"[价格识别] 价格匹配: 600")
            return True

        return False

    def _execute_first_purchase(self, mode: str, version: str, log) -> bool:
        """首次购买：移动鼠标到遗物位置 → 按F购买 → F2切换十连 → F确认 → F跳过动画"""
        if DEBUG_ENABLED:
            debug_timer.start("首次购买")

        purchase_coord = self.RELIC_PURCHASE_COORDS.get((version, mode))
        if purchase_coord is None:
            log(f"未找到购买坐标: version={version}, mode={mode}", "ERROR")
            if DEBUG_ENABLED:
                debug_timer.end("首次购买")
            return False

        # 移动鼠标到遗物位置
        x = int(purchase_coord[0] * self.repo_filter.scale_x)
        y = int(purchase_coord[1] * self.repo_filter.scale_y)
        offset_x, offset_y = self._get_window_offset()
        screen_x = offset_x + x
        screen_y = offset_y + y
        pyautogui.moveTo(screen_x, screen_y)
        time.sleep(0.1)

        # 检查是否仍在运行
        if not self.is_running:
            if DEBUG_ENABLED:
                debug_timer.end("首次购买")
            return False

        # 按F购买
        pydirectinput.press('f')
        pydirectinput.press('f2')
        pydirectinput.press('f')
        pydirectinput.press('f')

        self.stats["total_purchased"] += 10
        log(f"十连购买成功，总购买: {self.stats['total_purchased']}", "INFO")
        if DEBUG_ENABLED:
            elapsed = debug_timer.end("首次购买")
            debug_timer.record("首次购买", elapsed)
        return True

    def _execute_subsequent_purchase(self, log) -> bool:
        """后续购买：直接按F购买 → F2切换十连 → F确认 → F跳过动画"""
        if DEBUG_ENABLED:
            debug_timer.start("后续购买")

        # 检查是否仍在运行
        if not self.is_running:
            if DEBUG_ENABLED:
                debug_timer.end("后续购买")
            return False

        pydirectinput.press('f')
        pydirectinput.press('f2')
        pydirectinput.press('f')
        pydirectinput.press('f')

        self.stats["total_purchased"] += 10
        log(f"十连购买成功，总购买: {self.stats['total_purchased']}", "INFO")
        if DEBUG_ENABLED:
            elapsed = debug_timer.end("后续购买")
            debug_timer.record("后续购买", elapsed)
        return True


    def _process_purchased_relics(self, mode, require_double, general_preset,
                                   dedicated_presets, blacklist_preset, log, stats_callback):
        """处理购买的10个遗物（参考仓库清理流程）"""
        if DEBUG_ENABLED:
            debug_timer.start("处理10个遗物总耗时")

        for i in range(10):
            if not self.is_running:
                break

            log(f"处理第 {i+1}/10 个遗物", "INFO")

            # 1. 截图
            if DEBUG_ENABLED:
                debug_timer.start(f"relic_{i+1}_capture")

            # ===== OCR 自动采集调试代码：采集与 OCR 使用完全相同的一次截图 =====
            line_images, ocr_screen = self._capture_shop_line_rois(with_screen=True)
            ocr_trace = {} if self.ocr_debug_session else None
            # ===== OCR 自动采集调试代码结束 =====

            if DEBUG_ENABLED:
                capture_time = debug_timer.end(f"relic_{i+1}_capture")
                debug_timer.record(f"第{i+1}个遗物-截图", capture_time)

            # 2. OCR识别（使用商店界面专用的6行单行ROI）
            if DEBUG_ENABLED:
                debug_timer.start(f"relic_{i+1}_ocr")

            ocr_result = self.ocr_engine.recognize_with_classification_from_lines(
                line_images, mode, trace=ocr_trace)

            if DEBUG_ENABLED:
                ocr_time = debug_timer.end(f"relic_{i+1}_ocr")
                debug_timer.record(f"第{i+1}个遗物-OCR总耗时", ocr_time)

                # 从OCR结果中提取细粒度的时间数据（如果有的话）
                # 这些时间已经在OCR引擎中记录过了

            if not self.is_running:
                # ===== OCR 自动采集调试代码：停止发生在 OCR 期间时也保存本次样本 =====
                if self.ocr_debug_session:
                    self.ocr_debug_session.record(
                        ocr_screen, line_images, ocr_result, ocr_trace, None,
                        self.ocr_engine, self.stats["total_purchased"] - 10 + i + 1,
                        {"batch_position": i + 1, "batch_end": self.stats["total_purchased"],
                         "stopped_before_matching": True})
                # ===== OCR 自动采集调试代码结束 =====
                return
            if not ocr_result["success"]:
                # ===== OCR 自动采集调试代码：失败样本也保留 =====
                if self.ocr_debug_session:
                    self.ocr_debug_session.record(
                        ocr_screen, line_images, ocr_result, ocr_trace, None,
                        self.ocr_engine, self.stats["total_purchased"] - 10 + i + 1,
                        {"batch_position": i + 1, "batch_end": self.stats["total_purchased"]})
                # ===== OCR 自动采集调试代码结束 =====
                log("OCR识别失败，跳过", "ERROR")
                pydirectinput.press('right')
                continue

            # 记录词条到调试工具
            if DEBUG_ENABLED:
                # 记录纠错成功的词条
                for affix in ocr_result["affixes"]:
                    affix_recorder.record_success(affix['cleaned_text'], affix["is_positive"])

                # 记录纠错失败的词条（包含原始OCR文本）
                for failed_affix in ocr_result.get("correction_failed_affixes", []):
                    is_positive = self.ocr_engine._is_positive_affix(failed_affix["text"], mode)
                    # 获取原始OCR文本（仅在DEBUG_ENABLED时）
                    raw_text = failed_affix.get("raw_text") if DEBUG_ENABLED else None
                    affix_recorder.record_failed(failed_affix["text"], is_positive, raw_text)

            # 输出词条信息
            for affix in ocr_result["affixes"]:
                affix_type = "正面" if affix["is_positive"] else "负面"
                log(f"  [{affix_type}] {affix['cleaned_text']}", "INFO")

            # 3. 词条匹配（与仓库清理逻辑一致）
            if DEBUG_ENABLED:
                debug_timer.start(f"relic_{i+1}_match")

            match_result = self._match_affixes(
                ocr_result, general_preset, dedicated_presets,
                blacklist_preset, require_double, mode
            )

            # ===== OCR 自动采集调试代码：在任何售出/保留按键前写入完整证据和实际匹配结果 =====
            if self.ocr_debug_session:
                self.ocr_debug_session.record(
                    ocr_screen, line_images, ocr_result, ocr_trace, match_result,
                    self.ocr_engine, self.stats["total_purchased"] - 10 + i + 1,
                    {"batch_position": i + 1, "batch_end": self.stats["total_purchased"],
                     "required_effective_count": 2 if require_double else 3})
            # ===== OCR 自动采集调试代码结束 =====

            if DEBUG_ENABLED:
                match_time = debug_timer.end(f"relic_{i+1}_match")
                debug_timer.record(f"第{i+1}个遗物-词条匹配", match_time)

            if not self.is_running:
                break

            # 4. 执行操作
            if match_result.qualified:
                self.stats["qualified"] += 1
                log(f"合格遗物，保留", "SUCCESS")

                # 记录合格遗物
                relic_info = {
                    "index": self.stats["total_purchased"] - 10 + i + 1,
                    "affixes": ocr_result["affixes"]
                }
                self.qualified_relics.append(relic_info)
                self._record_kept_relic(mode, relic_info['index'], ocr_result,
                                        match_result, ocr_screen, log)
                try:
                    if not self.recorder.record("shop", mode, relic_info["index"], ocr_result, match_result):
                        log(f"匹配记录写入失败，仍保留遗物: {self.recorder.last_error}", "WARNING")
                except Exception as exc:
                    log(f"匹配记录写入失败，仍保留遗物: {exc}", "WARNING")
                log_match(match_result, relic_info["index"], log)
                if match_result.perfect and self.settings.get("shop_stop_on_perfect_relic", False):
                    self.stop_reason = "perfect_relic"
                    self.is_running = False
                    if stats_callback:
                        stats_callback(self.stats.copy())
                    return
                if not self.is_running:
                    return

                # 按右方向键跳过（保留）
                pydirectinput.press('right')
            elif not match_result.destructive_action_allowed:
                log_match(match_result, self.stats["total_purchased"] - 10 + i + 1, log)
                pydirectinput.press('right')
            else:
                self.stats["unqualified"] += 1
                self.stats["sold"] += 1
                log(f"不合格遗物，出售", "INFO")

                # 按3出售
                pydirectinput.press('3')

            # 更新统计
            if stats_callback:
                stats_callback(self.stats.copy())

        if DEBUG_ENABLED:
            total_time = debug_timer.end("处理10个遗物总耗时")
            debug_timer.record("处理10个遗物总耗时", total_time)

    def _record_kept_relic(self, mode, ordinal, observation, match, screen, log):
        """购买结果已显示且决定不售出后，保存本件实物及评分。"""
        try:
            color, confidence = recognize_color(screen, layout='shop')
            candidate = match.best_match
            scoring = normalize_scoring(self.settings.get('scoring'))['enabled']
            confirmed = bool(match.destructive_action_allowed)
            result = {
                'mode': mode, 'color': color, 'color_confidence': confidence,
                'affixes': observation.get('affixes', []),
                'scoring_enabled': scoring,
                'score': candidate.score if scoring else None,
                'score_details': candidate.score_details if scoring else [],
                'effective_count': candidate.effective_count,
                'preset_id': candidate.preset_id, 'preset_name': candidate.preset_name,
                'decision': ('无法确认' if not confirmed else
                             '备选' if scoring and candidate.score_grade == 'backup' else '保留'),
                'action': '保留未动', 'action_confirmed': True,
                'owned_verified': confirmed,
                'reason': '' if confirmed else 'OCR或预设无法确认',
            }
            self.inventory.record(self.scan_id, ordinal, result, self.settings)
            log(f"#{ordinal}｜{color}｜{'已录入库存' if confirmed else '已记录，待核实'}", 'INFO')
        except Exception as exc:
            log(f"遗物数据库写入失败：{exc}", 'WARNING')

    def _match_affixes(self, ocr_result, general_preset, dedicated_presets,
                       blacklist_preset, require_double, mode="normal"):
        return match_relic(ocr_result, general_preset, dedicated_presets, blacklist_preset,
                           threshold=2 if require_double else 3, general_fallback="always",
                           scoring_config=self.settings.get("scoring"), mode=mode)


    def _execute_sl_operation(self, log) -> bool:
        """
        执行存档恢复操作：退出到标题画面 → 恢复存档 → 重新进入游戏

        Returns:
            True=成功，False=失败
        """
        if self.stop_reason == "perfect_relic" or not self.is_running:
            return False

        if not self.save_manager or not self.steam_id or not self.backup_path:
            log("存档恢复参数缺失", "ERROR")
            return False

        log("开始退出到标题画面...", "INFO")

        # 1. 退出商人界面
        pydirectinput.press('q')
        time.sleep(0.5)

        # 2. 打开菜单
        pydirectinput.press('escape')
        time.sleep(0.5)

        # 3. 导航到返回首页
        pydirectinput.press('f1')
        time.sleep(0.3)
        pydirectinput.press('up')
        time.sleep(0.3)
        pydirectinput.press('f')  # 切换页面
        time.sleep(0.3)
        pydirectinput.press('f')
        time.sleep(0.3)
        pydirectinput.press('left')
        time.sleep(0.3)
        pydirectinput.press('f')  # 确认返回首页

        # 4. 等待返回首页画面
        log("等待返回首页画面...", "INFO")
        for _ in range(50):
            if not self.is_running:
                return False
            time.sleep(0.1)

        # 5. 恢复存档
        log("恢复存档...", "INFO")
        success, msg = self.save_manager.restore_save(self.steam_id, self.backup_path)
        if not success:
            log(f"存档恢复失败: {msg}", "ERROR")
            return False
        log("存档恢复成功", "SUCCESS")

        # 6. 不断按f并检测是否进入游戏界面
        # 检测区域：(1780, 1000, 1870, 1025) 基于1080p，出现数字则判定已进入游戏
        GAME_DETECT_REGION = (1780, 1000, 1870, 1025)
        log("读取存档并等待进入游戏...", "INFO")

        import re as _re
        max_attempts = 120  # 最多尝试120次（约60秒）
        entered_game = False

        for attempt in range(max_attempts):
            if not self.is_running:
                return False

            pydirectinput.press('f')
            time.sleep(0.5)

            # 截取检测区域并OCR
            try:
                detect_image = self.repo_filter._capture_region(GAME_DETECT_REGION)
                if detect_image is not None and detect_image.size > 0:
                    result = self.ocr_engine.recognize_raw(detect_image)
                    if result.get("success") and result.get("entries"):
                        text = result["entries"][0]
                        if _re.search(r'\d', text) and '.' not in text:
                            log(f"检测到游戏界面（识别到: {text}）", "SUCCESS")
                            entered_game = True
                            break
            except Exception as e:
                pass  # 截图或OCR失败时继续尝试

        if not entered_game:
            log("等待进入游戏超时", "ERROR")
            return False

        # 7. 等待游戏界面稳定
        for _ in range(20):
            if not self.is_running:
                return False
            time.sleep(0.1)

        log("已重新进入游戏，继续购买", "SUCCESS")
        return True
