"""自动化操作模块"""

import pyautogui
import pydirectinput
import time
import cv2
import numpy as np
import pygetwindow as gw
import os
from typing import Tuple, Optional
from datetime import datetime


class AutomationController:
    """键鼠操作控制器"""

    @staticmethod
    def press_key(key: str, duration: float = 0.1):
        """按下按键"""
        pydirectinput.press(key)
        time.sleep(duration)

    @staticmethod
    def move_mouse(x: int, y: int):
        """移动鼠标"""
        pyautogui.moveTo(x, y)

    @staticmethod
    def click(x: int, y: int, button: str = 'left'):
        """点击鼠标"""
        pyautogui.click(x, y, button=button)

    @staticmethod
    def screenshot():
        """截图"""
        return pyautogui.screenshot()


class RepositoryFilter:
    """仓库筛选控制器"""

    # 基准分辨率 (1080p)
    BASE_WIDTH = 1920
    BASE_HEIGHT = 1080

    # 基准坐标（1080p）
    RITUAL_REGION = (130, 30, 280, 90)  # 遗物仪式区域
    SELL_REGION = (580, 130, 640, 160)  # 卖出区域
    FILTER_REGION = (50, 850, 250, 960)  # 筛选勾选区域

    # 勾选框基准坐标（基于1920x1080）
    # "遗物"勾选框
    NORMAL_CHECKBOX = (70, 865, 95, 890)
    # "深层的遗物"勾选框
    DEEPNIGHT_CHECKBOX = (70, 915, 95, 940)

    # 调试目录
    DEBUG_DIR = "debug_ocr"

    def __init__(self, ocr_engine=None):
        """
        初始化仓库筛选控制器

        Args:
            ocr_engine: OCR引擎实例，用于文字识别
        """
        self.ocr_engine = ocr_engine
        self.game_window = self._find_game_window()
        self.scale_factor = self._calculate_scale_factor()

        # 创建调试目录
        if not os.path.exists(self.DEBUG_DIR):
            os.makedirs(self.DEBUG_DIR)
            print(f"[调试] 创建调试目录: {self.DEBUG_DIR}")

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
                    print(f"[成功] 找到游戏窗口: {window.title}")
                    print(f"  窗口尺寸: {window.width}x{window.height}")
                    return window

            print("[警告] 未找到包含NIGHTREIGN的窗口，将使用屏幕分辨率")
            return None
        except Exception as e:
            print(f"[警告] 查找游戏窗口失败: {e}")
            return None

    def _calculate_scale_factor(self) -> float:
        """计算当前分辨率相对于基准分辨率的缩放因子"""
        if self.game_window:
            # 使用游戏窗口尺寸
            window_width = self.game_window.width
            window_height = self.game_window.height
            print(f"[信息] 使用游戏窗口尺寸: {window_width}x{window_height}")
        else:
            # 回退到屏幕分辨率
            window_width, window_height = pyautogui.size()
            print(f"[信息] 使用屏幕分辨率: {window_width}x{window_height}")

        scale_x = window_width / self.BASE_WIDTH
        scale_y = window_height / self.BASE_HEIGHT
        scale_factor = min(scale_x, scale_y)

        print(f"[信息] 缩放因子: {scale_factor:.3f}")
        return scale_factor

    def _scale_region(self, region: Tuple[int, int, int, int]) -> Tuple[int, int, int, int]:
        """根据缩放因子调整区域坐标"""
        x1, y1, x2, y2 = region
        return (
            int(x1 * self.scale_factor),
            int(y1 * self.scale_factor),
            int(x2 * self.scale_factor),
            int(y2 * self.scale_factor)
        )

    def _capture_region(self, region: Tuple[int, int, int, int]) -> np.ndarray:
        """截取指定区域的图像"""
        x1, y1, x2, y2 = self._scale_region(region)
        screenshot = pyautogui.screenshot(region=(x1, y1, x2 - x1, y2 - y1))
        return cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)

    def _save_debug_image(self, image: np.ndarray, name: str):
        """保存调试图像"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
        filename = f"{name}_{timestamp}.png"
        filepath = os.path.join(self.DEBUG_DIR, filename)
        cv2.imwrite(filepath, image)
        print(f"  [调试] 保存图像: {filepath}")

    def verify_ritual_interface(self) -> bool:
        """
        验证是否在遗物仪式界面

        Returns:
            True: 在遗物仪式界面
            False: 不在遗物仪式界面
        """
        if self.ocr_engine is None:
            return True

        # 截取左上角区域
        image = self._capture_region(self.RITUAL_REGION)

        # OCR识别（不进行纠错）
        result = self.ocr_engine.recognize_raw(image)
        if not result['success']:
            return False

        # 检查是否包含"遗物仪式"
        text = ''.join(result['entries'])
        return '遗物仪式' in text or '遗物' in text

    def verify_sell_interface(self) -> bool:
        """
        验证是否在卖出界面

        Returns:
            True: 在卖出界面
            False: 不在卖出界面
        """
        if self.ocr_engine is None:
            return True

        # 截取卖出区域
        image = self._capture_region(self.SELL_REGION)

        # OCR识别（不进行纠错）
        result = self.ocr_engine.recognize_raw(image)
        if not result['success']:
            return False

        # 检查是否包含"卖出"
        text = ''.join(result['entries'])
        return '卖出' in text

    def navigate_to_sell_interface(self, max_attempts: int = 5) -> bool:
        """
        导航到卖出界面（按F2切换）

        Args:
            max_attempts: 最大尝试次数

        Returns:
            True: 成功导航到卖出界面
            False: 导航失败
        """
        for attempt in range(max_attempts):
            if self.verify_sell_interface():
                return True

            AutomationController.press_key('f2', duration=0.5)
            time.sleep(0.3)

        return False

    def enter_filter_interface(self) -> bool:
        """
        进入筛选界面（按4）

        Returns:
            True: 成功进入筛选界面
            False: 进入失败
        """
        AutomationController.press_key('4', duration=0.3)
        time.sleep(0.5)
        return True

    def reset_filter(self) -> bool:
        """
        重置筛选（按1）

        Returns:
            True: 成功重置筛选
            False: 重置失败
        """
        AutomationController.press_key('1', duration=0.3)
        return True

    def detect_checkbox_state(self) -> Tuple[bool, bool]:
        """
        检测左下角筛选区域的勾选状态（使用精确区域匹配）

        Returns:
            (normal_checked, deepnight_checked)
            - normal_checked: "遗物"是否打勾
            - deepnight_checked: "深层的遗物"是否打勾
        """
        # 检测"遗物"勾选框
        normal_region = self._scale_region(self.NORMAL_CHECKBOX)
        normal_image = self._capture_single_region(normal_region)
        normal_checked = self._is_checkbox_checked(normal_image)

        # 检测"深层的遗物"勾选框
        deepnight_region = self._scale_region(self.DEEPNIGHT_CHECKBOX)
        deepnight_image = self._capture_single_region(deepnight_region)
        deepnight_checked = self._is_checkbox_checked(deepnight_image)

        return normal_checked, deepnight_checked

    def _capture_single_region(self, region: Tuple[int, int, int, int]) -> np.ndarray:
        """截取指定区域的图像（不接受缩放后的区域）"""
        x1, y1, x2, y2 = region
        screenshot = pyautogui.screenshot(region=(x1, y1, x2 - x1, y2 - y1))
        return cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)

    def _is_checkbox_checked(self, checkbox_region: np.ndarray) -> bool:
        """
        判断勾选框区域是否被勾选

        Args:
            checkbox_region: 勾选框区域的BGR图像 (25x25)

        Returns:
            True: 已勾选
            False: 未勾选
        """
        h, w = checkbox_region.shape[:2]

        # 排除边框，只检测框内部中心区域
        margin = 6
        inner_region = checkbox_region[margin:h-margin, margin:w-margin]

        # 转换为灰度图
        gray = cv2.cvtColor(inner_region, cv2.COLOR_BGR2GRAY)

        # 计算中心区域平均灰度值
        mean_val = cv2.mean(gray)[0]

        # 框内有√：平均灰度值较高（约109）
        # 框内是空的：平均灰度值较低（约58）
        return mean_val > 90

    def click_checkbox(self, is_normal: bool):
        """
        点击勾选框（使用精确坐标）

        Args:
            is_normal: True表示点击"遗物"，False表示点击"深层的遗物"
        """
        # 获取精确的勾选框坐标并缩放
        if is_normal:
            region = self._scale_region(self.NORMAL_CHECKBOX)
        else:
            region = self._scale_region(self.DEEPNIGHT_CHECKBOX)

        # 计算中心点
        x1, y1, x2, y2 = region
        click_x = (x1 + x2) // 2
        click_y = (y1 + y2) // 2

        AutomationController.click(click_x, click_y)
        time.sleep(0.5)

    def adjust_filter_mode(self, mode: str) -> bool:
        """
        调整筛选模式

        Args:
            mode: "normal" 或 "deepnight"

        Returns:
            True: 调整成功
            False: 调整失败
        """
        print(f"\n[筛选模式] {mode}")

        if mode == "normal":
            # 普通模式：遗物打勾，深层的遗物不打勾
            target_normal = True
            target_deepnight = False
        elif mode == "deepnight":
            # 深夜模式：遗物不打勾，深层的遗物打勾
            target_normal = False
            target_deepnight = True
        else:
            return False

        # 调整遗物勾选状态
        normal_checked, deepnight_checked = self.detect_checkbox_state()

        if normal_checked != target_normal:
            self.click_checkbox(is_normal=True)

        # 调整深层的遗物勾选状态
        if deepnight_checked != target_deepnight:
            self.click_checkbox(is_normal=False)

        # 验证调整结果
        normal_checked, deepnight_checked = self.detect_checkbox_state()
        success = (normal_checked == target_normal and deepnight_checked == target_deepnight)

        if success:
            print("[结果] 筛选成功")
        else:
            print("[结果] 筛选失败")

        return success

    def exit_filter_interface(self):
        """退出筛选界面（按q）"""
        AutomationController.press_key('q', duration=0.3)
        time.sleep(0.3)

    def apply_filter(self, mode: str) -> bool:
        """
        完整的筛选流程

        Args:
            mode: "normal" 或 "deepnight"

        Returns:
            True: 筛选成功
            False: 筛选失败
        """
        # 1. 验证遗物仪式界面
        if not self.verify_ritual_interface():
            return False

        # 2. 验证或导航到卖出界面
        if not self.verify_sell_interface():
            if not self.navigate_to_sell_interface():
                return False

        # 3. 进入筛选界面
        if not self.enter_filter_interface():
            return False

        # 4. 重置筛选
        if not self.reset_filter():
            return False

        # 5. 调整筛选模式
        if not self.adjust_filter_mode(mode):
            self.exit_filter_interface()
            return False

        # 6. 退出筛选界面
        self.exit_filter_interface()

        return True

