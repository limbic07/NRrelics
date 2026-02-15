"""
商店自动化模块
处理商人界面导航、遗物购买、词条识别和筛选
"""

import time
import cv2
import numpy as np
from datetime import datetime


class ShopAutomation:
    """商店自动化"""

    # ROI坐标（基于1080p）
    BASE_WIDTH = 1920
    BASE_HEIGHT = 1080

    # 商人名称检测区域
    MERCHANT_NAME_REGION = (135, 40, 330, 80)

    # 遗物图标检测区域
    RELIC_ICON_REGION = (95, 845, 185, 930)

    # 遗物购买坐标（基于模式）
    RELIC_PURCHASE_COORDS = {
        ("new", "normal"): (145, 890),
        ("old", "normal"): (260, 890),
        ("new", "deepnight"): (375, 890),
        ("old", "deepnight"): (490, 890)
    }

    # 词条识别区域（与仓库清理相同）
    AFFIX_REGION = (1105, 800, 1805, 1000)

    # 商人界面入口坐标
    MERCHANT_MENU_COORD = (170, 590)

    def __init__(self, ocr_engine, preset_manager, repo_filter, settings: dict):
        """
        初始化商店自动化

        Args:
            ocr_engine: OCR引擎实例
            preset_manager: 预设管理器实例
            repo_filter: 仓库过滤器实例（用于窗口捕获和坐标缩放）
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
        if self.relic_template is None:
            raise FileNotFoundError("遗物模板图片不存在: data/template_relic.jpg")

    def start_shopping(self, mode: str, version: str, stop_currency: int,
                      require_double: bool, log_callback=None, stats_callback=None):
        """
        开始购买流程

        Args:
            mode: 模式 ("normal" 或 "deepnight")
            version: 版本 ("new" 或 "old")
            stop_currency: 停止购买的暗痕数量
            require_double: 是否需要双有效（True=双有效，False=三有效）
            log_callback: 日志回调函数
            stats_callback: 统计回调函数
        """
        self.is_running = True
        self.qualified_relics.clear()

        try:
            # 1. 检测并进入商人界面
            if not self._enter_merchant_interface(log_callback):
                if log_callback:
                    log_callback("无法进入商人界面", "ERROR")
                return

            # 2. 循环购买
            while self.is_running:
                # 检查暗痕数量（TODO: 实现暗痕检测）
                # 暂时使用购买次数作为停止条件
                if stop_currency > 0 and self.stats["total_purchased"] >= stop_currency:
                    if log_callback:
                        log_callback(f"已达到停止条件（购买{self.stats['total_purchased']}次）", "INFO")
                    break

                # 3. 寻找并购买遗物
                if not self._find_and_purchase_relic(mode, version, log_callback):
                    if log_callback:
                        log_callback("未找到遗物或购买失败", "ERROR")
                    break

                # 4. 处理购买的遗物（10个）
                self._process_purchased_relics(mode, require_double, log_callback, stats_callback)

                # 5. 关闭购买界面，准备下一轮
                self._close_purchase_interface(log_callback)

                time.sleep(0.5)

        except Exception as e:
            if log_callback:
                log_callback(f"购买过程出错: {e}", "ERROR")
        finally:
            self.is_running = False

    def stop(self):
        """停止购买"""
        self.is_running = False

    def _enter_merchant_interface(self, log_callback=None) -> bool:
        """
        检测并进入商人界面

        Returns:
            bool: 是否成功进入
        """
        # 捕获游戏窗口
        full_image = self.repo_filter.capture_game_window()
        if full_image is None:
            if log_callback:
                log_callback("无法捕获游戏窗口", "ERROR")
            return False

        # 检测商人名称
        merchant_region = self.repo_filter._capture_region(self.MERCHANT_NAME_REGION)
        if merchant_region is None:
            if log_callback:
                log_callback("无法捕获商人名称区域", "ERROR")
            return False

        # OCR识别
        result = self.ocr_engine.ocr.ocr(merchant_region, cls=False)
        if result and result[0]:
            text = "".join([line[1][0] for line in result[0]])
            if "小壶商人巴萨" in text:
                if log_callback:
                    log_callback("已在商人界面", "INFO")
                return True

        # 不在商人界面，尝试进入
        if log_callback:
            log_callback("不在商人界面，尝试进入...", "INFO")

        # 按m打开菜单
        import pydirectinput
        pydirectinput.press('m')
        time.sleep(0.5)

        # 点击商人入口
        scaled_coord = self._scale_coord(self.MERCHANT_MENU_COORD)
        window = self.repo_filter.window
        if window:
            click_x = window.left + scaled_coord[0]
            click_y = window.top + scaled_coord[1]
            import pyautogui
            pyautogui.click(click_x, click_y)
            time.sleep(1.0)

            if log_callback:
                log_callback("已进入商人界面", "INFO")
            return True

        return False

    def _find_and_purchase_relic(self, mode: str, version: str, log_callback=None) -> bool:
        """
        寻找并购买遗物

        Args:
            mode: 模式
            version: 版本
            log_callback: 日志回调

        Returns:
            bool: 是否成功购买
        """
        import pydirectinput
        import pyautogui

        # 滚动查找遗物
        max_scroll_attempts = 20
        for i in range(max_scroll_attempts):
            if not self.is_running:
                return False

            # 按上方向键滚动
            pydirectinput.press('up')
            time.sleep(0.2)

            # 捕获遗物图标区域
            relic_icon_region = self.repo_filter._capture_region(self.RELIC_ICON_REGION)
            if relic_icon_region is None:
                continue

            # 模板匹配
            if self._match_relic_template(relic_icon_region):
                if log_callback:
                    log_callback(f"找到遗物（滚动{i+1}次）", "INFO")

                # 点击购买
                purchase_coord = self.RELIC_PURCHASE_COORDS.get((version, mode))
                if purchase_coord:
                    scaled_coord = self._scale_coord(purchase_coord)
                    window = self.repo_filter.window
                    if window:
                        click_x = window.left + scaled_coord[0]
                        click_y = window.top + scaled_coord[1]
                        pyautogui.click(click_x, click_y)
                        time.sleep(0.5)

                        # 确认购买（假设需要按f确认）
                        pydirectinput.press('f')
                        time.sleep(1.0)

                        self.stats["total_purchased"] += 10  # 十连购买
                        if log_callback:
                            log_callback(f"购买成功（十连），总购买: {self.stats['total_purchased']}", "INFO")
                        return True

        if log_callback:
            log_callback("未找到遗物", "WARNING")
        return False

    def _match_relic_template(self, region_image) -> bool:
        """
        模板匹配检测遗物图标

        Args:
            region_image: 区域图像

        Returns:
            bool: 是否匹配
        """
        # 缩放模板到当前分辨率
        game_resolution = self.settings.get("game_resolution", [1920, 1080])
        scale_x = game_resolution[0] / self.BASE_WIDTH
        scale_y = game_resolution[1] / self.BASE_HEIGHT

        scaled_template = cv2.resize(
            self.relic_template,
            None,
            fx=scale_x,
            fy=scale_y,
            interpolation=cv2.INTER_LINEAR
        )

        # 模板匹配
        result = cv2.matchTemplate(region_image, scaled_template, cv2.TM_CCOEFF_NORMED)
        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)

        # 匹配阈值
        threshold = 0.7
        return max_val >= threshold

    def _process_purchased_relics(self, mode: str, require_double: bool,
                                  log_callback=None, stats_callback=None):
        """
        处理购买的遗物（10个）

        Args:
            mode: 模式
            require_double: 是否双有效
            log_callback: 日志回调
            stats_callback: 统计回调
        """
        import pydirectinput

        # 处理10个遗物
        for i in range(10):
            if not self.is_running:
                break

            if log_callback:
                log_callback(f"处理第 {i+1}/10 个遗物", "INFO")

            # 1. OCR识别词条
            affix_image = self.repo_filter._capture_region(self.AFFIX_REGION)
            if affix_image is None:
                if log_callback:
                    log_callback("无法捕获词条区域", "ERROR")
                pydirectinput.press('right')
                time.sleep(0.3)
                continue

            # 识别词条
            affixes = self.ocr_engine.recognize_with_classification(affix_image, mode)
            if not affixes:
                if log_callback:
                    log_callback("OCR识别失败", "ERROR")
                pydirectinput.press('right')
                time.sleep(0.3)
                continue

            # 2. 匹配预设
            is_qualified = self._match_affixes(affixes, mode, require_double, log_callback)

            # 3. 执行操作
            if is_qualified:
                self.stats["qualified"] += 1
                # 保留合格遗物
                relic_info = {
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "affixes": [{"text": a["text"], "is_positive": a["is_positive"]} for a in affixes]
                }
                self.qualified_relics.append(relic_info)

                if log_callback:
                    affix_texts = [a["text"] for a in affixes]
                    log_callback(f"合格遗物: {', '.join(affix_texts)}", "SUCCESS")
            else:
                self.stats["unqualified"] += 1
                # 出售不合格遗物
                pydirectinput.press('f')
                time.sleep(0.2)
                self.stats["sold"] += 1

                if log_callback:
                    affix_texts = [a["text"] for a in affixes]
                    log_callback(f"不合格遗物已售出: {', '.join(affix_texts)}", "INFO")

            # 更新统计
            if stats_callback:
                stats_callback(self.stats.copy())

            # 移动到下一个遗物
            pydirectinput.press('right')
            time.sleep(0.3)

    def _match_affixes(self, affixes: list, mode: str, require_double: bool, log_callback=None) -> bool:
        """
        匹配词条（与仓库清理逻辑相同）

        Args:
            affixes: 词条列表
            mode: 模式
            require_double: 是否双有效
            log_callback: 日志回调

        Returns:
            bool: 是否合格
        """
        # 单个正面词条 → 不合格
        positive_affixes = [a for a in affixes if a.get("is_positive", True)]
        if len(positive_affixes) == 1:
            return False

        # 深夜模式：黑名单检查
        if mode == "deepnight":
            blacklist = self.preset_manager.get_blacklist_preset()
            if blacklist and blacklist.get("is_active", True):
                blacklist_affixes = set(blacklist.get("affixes", []))
                for affix in affixes:
                    if affix["text"] in blacklist_affixes:
                        return False

        # 白名单匹配
        general_preset = self.preset_manager.get_general_preset(mode)
        dedicated_presets = self.preset_manager.get_dedicated_presets(mode)

        # 通用预设词条
        general_affixes = set(general_preset.get("affixes", [])) if general_preset and general_preset.get("is_active", True) else set()

        # 遍历每个专用预设
        for preset in dedicated_presets.values():
            if not preset.get("is_active", True):
                continue

            # 合并通用+专用
            combined_affixes = general_affixes | set(preset.get("affixes", []))

            # 匹配检查
            matched_count = sum(1 for a in affixes if a["text"] in combined_affixes)

            # 双有效：至少2个匹配，三有效：至少3个匹配
            required_matches = 2 if require_double else 3
            if matched_count >= required_matches:
                return True

        # 只检查通用预设
        if general_affixes:
            matched_count = sum(1 for a in affixes if a["text"] in general_affixes)
            required_matches = 2 if require_double else 3
            if matched_count >= required_matches:
                return True

        return False

    def _close_purchase_interface(self, log_callback=None):
        """关闭购买界面"""
        import pydirectinput
        pydirectinput.press('q')
        time.sleep(0.5)

        if log_callback:
            log_callback("关闭购买界面", "INFO")

    def _scale_coord(self, coord: tuple) -> tuple:
        """
        缩放坐标到当前分辨率

        Args:
            coord: 基准坐标 (x, y)

        Returns:
            tuple: 缩放后的坐标
        """
        game_resolution = self.settings.get("game_resolution", [1920, 1080])
        scale_x = game_resolution[0] / self.BASE_WIDTH
        scale_y = game_resolution[1] / self.BASE_HEIGHT

        return (int(coord[0] * scale_x), int(coord[1] * scale_y))
