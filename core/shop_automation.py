"""
商店自动化模块
处理商人界面导航、遗物购买、词条识别和筛选
"""

import time
import cv2
import numpy as np
import pydirectinput
import pyautogui
from datetime import datetime
from typing import Optional

from core.preset_manager import PresetManager


class ShopAutomation:
    """商店自动化"""

    # ROI坐标（基于1080p）
    BASE_WIDTH = 1920
    BASE_HEIGHT = 1080

    # 商人名称检测区域
    MERCHANT_NAME_REGION = (135, 40, 330, 80)

    # 遗物图标检测区域（需要比模板大，留出匹配余量）
    RELIC_ICON_REGION = (90, 840, 190, 940)

    # 遗物购买坐标（基于模式）
    RELIC_PURCHASE_COORDS = {
        ("new", "normal"): (145, 890),
        ("old", "normal"): (260, 890),
        ("new", "deepnight"): (375, 890),
        ("old", "deepnight"): (490, 890)
    }

    # 商人界面入口坐标
    MERCHANT_MENU_COORD = (170, 590)

    # 模板匹配阈值
    TEMPLATE_MATCH_THRESHOLD = 0.7

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

        # 加载遗物模板
        self.relic_template = cv2.imread("data/template_relic.jpg")
        if self.relic_template is not None:
            self.relic_template_gray = cv2.cvtColor(self.relic_template, cv2.COLOR_BGR2GRAY)
        else:
            self.relic_template_gray = None
            print("[警告] 遗物模板图片不存在: data/template_relic.jpg")

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
        self.is_running = True
        self.stats = {"total_purchased": 0, "qualified": 0, "unqualified": 0, "sold": 0}
        self.qualified_relics.clear()

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
                print(f"[{level}] {message}")

        try:
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

            # 1. 检测并进入商人界面
            if not self._enter_merchant_interface(log):
                return

            # 2. 首次寻找遗物
            if not self._find_relic(log):
                log("首次寻找遗物失败", "ERROR")
                return

            # 3. 循环购买
            first_purchase = True
            while self.is_running:
                # SL模式：检查合格遗物数量是否达标
                if self.sl_mode_enabled and self.sl_qualified_target > 0:
                    if self.stats["qualified"] >= self.sl_qualified_target:
                        log(f"已达到目标合格遗物数量 ({self.stats['qualified']}/{self.sl_qualified_target})", "SUCCESS")
                        break

                    # 购买前检测暗痕，不足则执行存档恢复
                    current_currency = self._detect_currency(log)
                    if current_currency >= 0 and current_currency < 10000:
                        log(f"暗痕不足 ({current_currency} < 10000)，合格遗物 {self.stats['qualified']}/{self.sl_qualified_target}，执行存档恢复...", "WARNING")
                        if not self._execute_sl_operation(log):
                            log("存档恢复操作失败，停止购买", "ERROR")
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
                            break
                        if not self._find_relic(log):
                            log("SL后无法找到遗物", "ERROR")
                            break
                        first_purchase = True
                        continue
                else:
                    # 原有停止条件：检测暗痕数量
                    if stop_currency > 0:
                        current_currency = self._detect_currency(log)
                        if current_currency >= 0 and current_currency < stop_currency:
                            log(f"暗痕不足（当前{current_currency} < 停止值{stop_currency}），停止购买", "WARNING")
                            break

                # 4. 执行购买
                if first_purchase:
                    # 首次购买：点击遗物坐标
                    if not self._execute_first_purchase(mode, version, log):
                        break
                    first_purchase = False
                else:
                    # 后续购买：直接按F购买
                    if not self._execute_subsequent_purchase(log):
                        break

                # 5. 处理购买的10个遗物
                self._process_purchased_relics(
                    mode, require_double, general_preset, dedicated_presets,
                    blacklist_preset, log, stats_callback
                )

                # 6. 确认操作（按f）
                pydirectinput.press('f')
                time.sleep(0.5)
                log("已确认操作", "INFO")

        except Exception as e:
            log(f"购买过程出错: {e}", "ERROR")
        finally:
            self.is_running = False

    def stop(self):
        """停止购买"""
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
                return True

        # 不在商人界面，尝试进入
        log("不在商人界面，尝试进入...", "INFO")
        pydirectinput.press('m')
        time.sleep(0.5)

        self._click_scaled_coord(self.MERCHANT_MENU_COORD)
        time.sleep(1.0)

        # 验证是否进入
        merchant_region = self.repo_filter._capture_region(self.MERCHANT_NAME_REGION)
        result = self.ocr_engine.recognize_raw(merchant_region)
        if result["success"] and result["entries"]:
            text = "".join(result["entries"])
            if "小壶商人巴萨" in text or "商人" in text:
                log("已进入商人界面", "INFO")
                return True

        log("无法进入商人界面", "ERROR")
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

    def _capture_shop_line_rois(self) -> list:
        """
        截取商店界面6行单行ROI区域（用于单行OCR识别）

        Returns:
            6个单行图像的列表，每个图像是numpy数组
        """
        window_image = self.repo_filter._capture_game_window()
        if window_image is None:
            return [np.zeros((100, 100, 3), dtype=np.uint8) for _ in self.SHOP_LINE_ROI_COORDS]

        line_images = []
        for y_start, y_end in self.SHOP_LINE_ROI_COORDS:
            region = (self.SHOP_LINE_ROI_X_START, y_start, self.SHOP_LINE_ROI_X_END, y_end)
            x1, y1, x2, y2 = self.repo_filter._scale_region(region)
            line_images.append(window_image[y1:y2, x1:x2])

        return line_images

    def _find_relic(self, log) -> bool:
        """滚动寻找遗物"""
        max_scroll_attempts = 20
        for i in range(max_scroll_attempts):
            if not self.is_running:
                return False

            pydirectinput.press('up')
            time.sleep(0.2)

            # 捕获遗物图标区域并模板匹配
            relic_icon_region = self.repo_filter._capture_region(self.RELIC_ICON_REGION)
            if relic_icon_region is not None and self._match_relic_template(relic_icon_region):
                log(f"找到遗物（滚动{i+1}次）", "INFO")
                return True

        log("未找到遗物", "WARNING")
        return False

    def _execute_first_purchase(self, mode: str, version: str, log) -> bool:
        """首次购买：移动鼠标到遗物位置 → 按F购买 → F2切换十连 → F确认 → F跳过动画"""
        purchase_coord = self.RELIC_PURCHASE_COORDS.get((version, mode))
        if purchase_coord is None:
            log(f"未找到购买坐标: version={version}, mode={mode}", "ERROR")
            return False

        # 移动鼠标到遗物位置
        x = int(purchase_coord[0] * self.repo_filter.scale_x)
        y = int(purchase_coord[1] * self.repo_filter.scale_y)
        offset_x, offset_y = self._get_window_offset()
        screen_x = offset_x + x
        screen_y = offset_y + y
        pyautogui.moveTo(screen_x, screen_y)
        time.sleep(0.1)

        # 按F购买
        pydirectinput.press('f')
        time.sleep(0.3)  # 等待购买界面打开
        pydirectinput.press('f2')
        pydirectinput.press('f')
        pydirectinput.press('f')

        self.stats["total_purchased"] += 10
        log(f"十连购买成功，总购买: {self.stats['total_purchased']}", "INFO")
        return True

    def _execute_subsequent_purchase(self, log) -> bool:
        """后续购买：直接按F购买 → F2切换十连 → F确认 → F跳过动画"""
        pydirectinput.press('f')
        time.sleep(0.3)  # 等待购买界面打开
        pydirectinput.press('f2')
        pydirectinput.press('f')
        pydirectinput.press('f')

        self.stats["total_purchased"] += 10
        log(f"十连购买成功，总购买: {self.stats['total_purchased']}", "INFO")
        return True

    def _match_relic_template(self, region_image) -> bool:
        """模板匹配检测遗物图标"""
        if self.relic_template_gray is None or region_image is None or region_image.size == 0:
            print(f"[模板匹配] 模板或区域为空")
            return False

        # 使用 repo_filter 的缩放因子
        scaled_template = cv2.resize(
            self.relic_template_gray, None,
            fx=self.repo_filter.scale_x,
            fy=self.repo_filter.scale_y,
            interpolation=cv2.INTER_LINEAR
        )

        print(f"[模板匹配] 模板原始尺寸: {self.relic_template_gray.shape}, 缩放后: {scaled_template.shape}, 区域尺寸: {region_image.shape}, 缩放因子: ({self.repo_filter.scale_x:.4f}, {self.repo_filter.scale_y:.4f})")

        # 检查模板尺寸是否合法
        if (scaled_template.shape[0] > region_image.shape[0] or
            scaled_template.shape[1] > region_image.shape[1]):
            print(f"[模板匹配] 模板尺寸大于区域，跳过")
            return False

        # 转灰度匹配
        if len(region_image.shape) == 3:
            region_gray = cv2.cvtColor(region_image, cv2.COLOR_BGR2GRAY)
        else:
            region_gray = region_image

        result = cv2.matchTemplate(region_gray, scaled_template, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, _ = cv2.minMaxLoc(result)

        print(f"[模板匹配] 匹配度: {max_val:.4f}, 阈值: {self.TEMPLATE_MATCH_THRESHOLD}")

        # 保存调试图像（仅第一次）
        cv2.imwrite("debug_shop_region.png", region_image)
        cv2.imwrite("debug_shop_template_scaled.png", scaled_template)

        return max_val >= self.TEMPLATE_MATCH_THRESHOLD

    def _process_purchased_relics(self, mode, require_double, general_preset,
                                   dedicated_presets, blacklist_preset, log, stats_callback):
        """处理购买的10个遗物（参考仓库清理流程）"""
        for i in range(10):
            if not self.is_running:
                break

            log(f"处理第 {i+1}/10 个遗物", "INFO")

            # 1. OCR识别（使用商店界面专用的6行单行ROI）
            line_images = self._capture_shop_line_rois()
            ocr_result = self.ocr_engine.recognize_with_classification_from_lines(line_images, mode)

            if not ocr_result["success"]:
                log("OCR识别失败，跳过", "ERROR")
                pydirectinput.press('right')
                continue

            # 输出词条信息
            for affix in ocr_result["affixes"]:
                affix_type = "正面" if affix["is_positive"] else "负面"
                log(f"  [{affix_type}] {affix['cleaned_text']}", "INFO")

            # 2. 词条匹配（与仓库清理逻辑一致）
            is_qualified = self._match_affixes(
                ocr_result, general_preset, dedicated_presets,
                blacklist_preset, require_double
            )

            # 3. 执行操作
            if is_qualified:
                self.stats["qualified"] += 1
                log(f"合格遗物，保留", "SUCCESS")

                # 记录合格遗物
                relic_info = {
                    "index": self.stats["total_purchased"] - 10 + i + 1,
                    "affixes": ocr_result["affixes"]
                }
                self.qualified_relics.append(relic_info)

                # 按右方向键跳过（保留）
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

    def _match_affixes(self, ocr_result, general_preset, dedicated_presets,
                       blacklist_preset, require_double) -> bool:
        """
        词条匹配（与仓库清理逻辑一致）
        """
        pos_affixes = [a for a in ocr_result["affixes"] if a["is_positive"]]
        neg_affixes = [a for a in ocr_result["affixes"] if not a["is_positive"]]

        # 单个正面词条 → 不合格
        if len(pos_affixes) <= 1:
            return False

        # 黑名单匹配（深夜模式）
        if blacklist_preset and blacklist_preset.get("is_active", True):
            blacklist_set = set(blacklist_preset.get("affixes", []))
            for neg in neg_affixes:
                if neg["cleaned_text"] in blacklist_set:
                    return False

        # 白名单匹配
        required_matches = 2 if require_double else 3

        general_vocabs = set()
        if general_preset and general_preset.get("is_active", True):
            general_vocabs = set(general_preset.get("affixes", []))

        # 通用 + 每个专用预设
        if dedicated_presets:
            for preset in dedicated_presets.values() if isinstance(dedicated_presets, dict) else dedicated_presets:
                if not preset.get("is_active", True):
                    continue
                combined_vocabs = general_vocabs | set(preset.get("affixes", []))
                count = sum(1 for a in pos_affixes if a["cleaned_text"] in combined_vocabs)
                if count >= required_matches:
                    return True

        # 只检查通用预设
        if general_vocabs:
            count = sum(1 for a in pos_affixes if a["cleaned_text"] in general_vocabs)
            if count >= required_matches:
                return True

        return False

    def _close_purchase_interface(self, log):
        """关闭购买界面"""
        pydirectinput.press('q')
        time.sleep(0.5)
        log("关闭购买界面", "INFO")

    def _execute_sl_operation(self, log) -> bool:
        """
        执行存档恢复操作：退出到标题画面 → 恢复存档 → 重新进入游戏

        Returns:
            True=成功，False=失败
        """
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
