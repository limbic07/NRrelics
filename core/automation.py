"""自动化操作模块"""

import pyautogui
import pydirectinput
import time
import cv2
import numpy as np
import pygetwindow as gw
import win32gui
import win32con
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
    FILTER_TITLE_REGION = (180, 55, 240, 99)  # 筛选标题区域（用于验证是否在筛选界面）
    AFFIX_REGION = (1105, 800, 1805, 1000)  # 词条识别区域 (x1, y1, x2, y2)
    COUNT_REGION = (1620, 730, 1675, 760)  # 遗物数量显示区域
    FIRST_RELIC_POS = (975, 255)  # 第一个遗物的位置（用于移动光标）

    # 勾选框基准坐标（基于1920x1080）
    # "遗物"勾选框
    NORMAL_CHECKBOX = (70, 865, 95, 890)
    # "深层的遗物"勾选框
    DEEPNIGHT_CHECKBOX = (70, 915, 95, 940)

    # 六行单行ROI区域配置（用于单行OCR识别）
    # X轴范围
    LINE_ROI_X_START = 1107
    LINE_ROI_X_END = 1700

    # Y轴范围：这 6 行文本其实分为 3 组，组与组之间有轻微的缝隙
    LINE_ROI_COORDS = [
        # 第一组
        (810, 833),   # 第 1 行
        (833, 858),   # 第 2 行

        # 第二组
        (870, 893),   # 第 3 行
        (893, 917),   # 第 4 行

        # 第三组
        (930, 954),   # 第 5 行
        (954, 978)    # 第 6 行
    ]

    # 调试目录
    DEBUG_DIR = "debug_ocr"

    def __init__(self, ocr_engine=None, settings=None):
        """
        初始化仓库筛选控制器

        Args:
            ocr_engine: OCR引擎实例，用于文字识别
            settings: 设置字典（不再使用game_resolution字段）
        """
        self.ocr_engine = ocr_engine
        self.settings = settings or {}
        self.game_window = self._find_game_window()
        self.scale_x, self.scale_y = self._calculate_scale_factors()

        # 创建调试目录
        if not os.path.exists(self.DEBUG_DIR):
            os.makedirs(self.DEBUG_DIR)

    def refresh_window_info(self):
        """
        刷新游戏窗口位置和分辨率信息

        在开始清理前调用，确保窗口位置和缩放因子是最新的
        """
        self.game_window = self._find_game_window()
        self.scale_x, self.scale_y = self._calculate_scale_factors()

    def _find_game_window(self) -> Optional[gw.Win32Window]:
        """
        查找包含NIGHTREIGN的游戏窗口（仅用于获取窗口位置）

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

    def _calculate_scale_factors(self) -> Tuple[float, float]:
        """计算当前分辨率相对于基准分辨率的缩放因子（动态检测窗口客户区分辨率）"""
        # 获取窗口客户区信息
        client_rect = self._get_client_rect_screen_coords()

        if client_rect:
            # 使用客户区的宽度和高度
            _, _, window_width, window_height = client_rect
        else:
            # 如果无法获取客户区信息，使用默认分辨率
            print("[警告] 无法获取窗口客户区信息，使用默认分辨率 1920x1080")
            window_width = 1920
            window_height = 1080

        scale_x = window_width / self.BASE_WIDTH
        scale_y = window_height / self.BASE_HEIGHT

        # 输出缩放因子信息
        print("=" * 60)
        print("[分辨率缩放信息]")
        print(f"  基准分辨率: {self.BASE_WIDTH}x{self.BASE_HEIGHT}")
        print(f"  检测到的游戏窗口客户区分辨率: {window_width}x{window_height}")
        print(f"  缩放因子 X: {scale_x:.4f} ({window_width}/{self.BASE_WIDTH})")
        print(f"  缩放因子 Y: {scale_y:.4f} ({window_height}/{self.BASE_HEIGHT})")
        print("=" * 60)

        return scale_x, scale_y

    def _scale_region(self, region: Tuple[int, int, int, int]) -> Tuple[int, int, int, int]:
        """根据缩放因子调整区域坐标（分别使用X和Y缩放因子）"""
        x1, y1, x2, y2 = region
        return (
            int(x1 * self.scale_x),
            int(y1 * self.scale_y),
            int(x2 * self.scale_x),
            int(y2 * self.scale_y)
        )

    def _get_client_rect_screen_coords(self) -> Optional[Tuple[int, int, int, int]]:
        """
        获取窗口客户区的屏幕坐标（排除标题栏和边框）

        Returns:
            (left, top, width, height) 或 None
        """
        if not self.game_window:
            return None

        try:
            # 通过窗口标题查找窗口句柄
            hwnd = win32gui.FindWindow(None, self.game_window.title)
            if not hwnd:
                print("[警告] 无法获取窗口句柄")
                return None

            # 获取客户区矩形（相对于窗口）
            client_rect = win32gui.GetClientRect(hwnd)
            # client_rect = (left, top, right, bottom)，对于客户区，left和top通常是0

            # 将客户区左上角转换为屏幕坐标
            client_left, client_top = win32gui.ClientToScreen(hwnd, (client_rect[0], client_rect[1]))

            # 计算客户区宽度和高度
            client_width = client_rect[2] - client_rect[0]
            client_height = client_rect[3] - client_rect[1]

            print(f"[调试] 客户区屏幕坐标: left={client_left}, top={client_top}, width={client_width}, height={client_height}")

            return (client_left, client_top, client_width, client_height)

        except Exception as e:
            print(f"[警告] 获取客户区坐标失败: {e}")
            return None

    def _capture_game_window(self) -> Optional[np.ndarray]:
        """
        截取整个游戏窗口图像（仅客户区，排除标题栏和边框）

        Returns:
            BGR格式的numpy数组，如果失败则返回None
        """
        try:
            if self.game_window:
                # 尝试获取客户区坐标
                client_coords = self._get_client_rect_screen_coords()

                if client_coords:
                    # 使用客户区坐标截图
                    left, top, width, height = client_coords
                    screenshot = pyautogui.screenshot(region=(left, top, width, height))
                else:
                    # 回退到使用整个窗口（包括边框）
                    print("[警告] 无法获取客户区，使用整个窗口截图")
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

    def _capture_region(self, region: Tuple[int, int, int, int]) -> np.ndarray:
        """
        截取指定区域的图像（从游戏窗口中切割）

        Args:
            region: 基于游戏分辨率的区域坐标 (x1, y1, x2, y2)

        Returns:
            BGR格式的numpy数组
        """
        # 先截取整个游戏窗口
        window_image = self._capture_game_window()
        if window_image is None:
            # 如果截取失败，返回空图像
            return np.zeros((100, 100, 3), dtype=np.uint8)

        # 缩放区域坐标
        x1, y1, x2, y2 = self._scale_region(region)

        # 从窗口图像中切割ROI（使用numpy数组切片）
        # 注意：numpy数组的索引是 [y, x]
        roi = window_image[y1:y2, x1:x2]

        return roi

    def capture_line_rois(self) -> list:
        """
        截取6行单行ROI区域（用于单行OCR识别）

        Returns:
            6个单行图像的列表，每个图像是numpy数组
        """
        line_images = []
        for y_start, y_end in self.LINE_ROI_COORDS:
            # 构建完整的ROI坐标 (x1, y1, x2, y2)
            region = (self.LINE_ROI_X_START, y_start, self.LINE_ROI_X_END, y_end)
            # 使用 _capture_region() 方法获取单行ROI（自动处理缩放）
            line_roi = self._capture_region(region)
            line_images.append(line_roi)

        return line_images

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
            print("[警告] OCR引擎未初始化，无法验证界面")
            return False

        # 截取左上角区域
        image = self._capture_region(self.RITUAL_REGION)

        # 保存调试图片
        self._save_debug_image(image, "ritual_region")

        # OCR识别（不进行纠错）
        result = self.ocr_engine.recognize_raw(image)
        if not result['success']:
            return False

        # 检查是否包含"遗物仪式"
        text = ''.join(result['entries'])
        return '遗物仪式' in text or '遗物' in text

    def detect_relic_count(self) -> int:
        """
        检测筛选后的遗物数量

        Returns:
            int: 检测到的遗物数量，失败返回 0
        """
        if self.ocr_engine is None:
            print("[警告] OCR引擎未初始化，无法检测遗物数量")
            return 0

        # 截取数量显示区域
        image = self._capture_region(self.COUNT_REGION)

        # 保存调试图片
        self._save_debug_image(image, "count_region")

        # OCR识别（单行数字）
        result = self.ocr_engine.recognize_raw(image)
        if not result['success']:
            print("[警告] 遗物数量识别失败")
            return 0

        # 提取数字
        text = ''.join(result['entries']).strip()
        print(f"[调试] 识别到的文本: '{text}'")

        # 尝试解析数字
        try:
            # 移除非数字字符
            import re
            numbers = re.findall(r'\d+', text)
            if numbers:
                count = int(numbers[0])
                print(f"[信息] 检测到遗物数量: {count}")
                return count
            else:
                print("[警告] 未能从文本中提取数字")
                return 0
        except Exception as e:
            print(f"[错误] 解析遗物数量失败: {e}")
            return 0

    def verify_sell_interface(self) -> bool:
        """
        验证是否在卖出界面

        Returns:
            True: 在卖出界面
            False: 不在卖出界面
        """
        if self.ocr_engine is None:
            print("[警告] OCR引擎未初始化，无法验证界面")
            return False

        # 截取卖出区域
        image = self._capture_region(self.SELL_REGION)

        # 保存调试图片
        self._save_debug_image(image, "sell_region")

        # OCR识别（不进行纠错）
        result = self.ocr_engine.recognize_raw(image)
        if not result['success']:
            return False

        # 检查是否包含"卖出"
        text = ''.join(result['entries'])
        return '卖出' in text

    def navigate_to_sell_interface(self, max_attempts: int = 10) -> bool:
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

    def verify_filter_interface(self, max_retry: int = 2) -> bool:
        """
        验证是否在筛选界面（而不是排序界面）

        按4后可能进入排序界面而不是筛选界面，需要通过OCR检测标题区域是否有"筛选"字样
        如果不是筛选界面，按F1切换到筛选界面

        Args:
            max_retry: 最大重试次数

        Returns:
            True: 在筛选界面
            False: 验证失败
        """
        if self.ocr_engine is None:
            print("[警告] OCR引擎未初始化，无法验证筛选界面")
            return False

        for retry in range(max_retry):
            # 截取筛选标题区域
            image = self._capture_region(self.FILTER_TITLE_REGION)
            self._save_debug_image(image, "filter_title_region")

            # OCR识别
            result = self.ocr_engine.recognize_raw(image)
            if result['success']:
                text = ''.join(result['entries'])
                print(f"[调试] 筛选标题区域识别到: '{text}'")

                # 检查是否包含"筛选"
                if '筛选' in text:
                    print("[信息] 已确认在筛选界面")
                    return True

            # 不在筛选界面，按F1切换
            print(f"[警告] 未检测到筛选界面，按F1切换 (尝试 {retry + 1}/{max_retry})")
            AutomationController.press_key('f1', duration=0.3)
            time.sleep(0.5)

        print("[错误] 无法进入筛选界面")
        return False

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
        self._save_debug_image(normal_image, "normal_checkbox")
        normal_checked = self._is_checkbox_checked(normal_image)

        # 检测"深层的遗物"勾选框
        deepnight_region = self._scale_region(self.DEEPNIGHT_CHECKBOX)
        deepnight_image = self._capture_single_region(deepnight_region)
        self._save_debug_image(deepnight_image, "deepnight_checkbox")
        deepnight_checked = self._is_checkbox_checked(deepnight_image)

        print(f"[调试] 勾选框状态: 遗物={normal_checked}, 深层的遗物={deepnight_checked}")

        return normal_checked, deepnight_checked

    def _capture_single_region(self, region: Tuple[int, int, int, int]) -> np.ndarray:
        """
        截取指定区域的图像（接受已缩放的区域，从游戏窗口中切割）

        Args:
            region: 已缩放的区域坐标 (x1, y1, x2, y2)

        Returns:
            BGR格式的numpy数组
        """
        # 先截取整个游戏窗口
        window_image = self._capture_game_window()
        if window_image is None:
            # 如果截取失败，返回空图像
            return np.zeros((100, 100, 3), dtype=np.uint8)

        x1, y1, x2, y2 = region

        # 从窗口图像中切割ROI（使用numpy数组切片）
        roi = window_image[y1:y2, x1:x2]

        return roi

    def _is_checkbox_checked(self, checkbox_region: np.ndarray) -> bool:
        """
        判断勾选框区域是否被勾选

        Args:
            checkbox_region: 勾选框区域的BGR图像

        Returns:
            True: 已勾选
            False: 未勾选
        """
        h, w = checkbox_region.shape[:2]

        # 使用相对比例排除边框，只检测框内部中心区域
        # 边框约占24%（6/25），使用相对比例确保在不同分辨率下都能正确识别
        margin_ratio = 0.24
        margin_h = int(h * margin_ratio)
        margin_w = int(w * margin_ratio)
        inner_region = checkbox_region[margin_h:h-margin_h, margin_w:w-margin_w]

        if inner_region.size == 0:
            print("[警告] 勾选框内部区域为空，返回未勾选")
            return False

        # 转换为灰度图
        gray = cv2.cvtColor(inner_region, cv2.COLOR_BGR2GRAY)

        # 计算中心区域平均灰度值
        mean_val = cv2.mean(gray)[0]

        # 输出调试信息
        print(f"[调试] 勾选框尺寸: {w}x{h}, 内部区域尺寸: {inner_region.shape[1]}x{inner_region.shape[0]}, 平均灰度值: {mean_val:.2f}")

        # 框内有√：平均灰度值较高（约109）
        # 框内是空的：平均灰度值较低（约58）
        # 使用动态阈值：(109 + 58) / 2 = 83.5，取85为阈值
        threshold = 85
        is_checked = mean_val > threshold

        print(f"[调试] 判断结果: {'已勾选' if is_checked else '未勾选'} (阈值={threshold})")

        return is_checked

    def click_checkbox(self, is_normal: bool):
        """
        点击勾选框（使用精确坐标）

        Args:
            is_normal: True表示点击"遗物"，False表示点击"深层的遗物"
        """
        # 获取精确的勾选框坐标并缩放
        if is_normal:
            region = self._scale_region(self.NORMAL_CHECKBOX)
            checkbox_name = "遗物"
        else:
            region = self._scale_region(self.DEEPNIGHT_CHECKBOX)
            checkbox_name = "深层的遗物"

        # 计算中心点（相对于游戏内容）
        x1, y1, x2, y2 = region
        click_x = (x1 + x2) // 2
        click_y = (y1 + y2) // 2

        # 窗口化模式：使用客户区坐标转换为屏幕坐标
        if self.game_window:
            client_coords = self._get_client_rect_screen_coords()
            if client_coords:
                client_left, client_top, _, _ = client_coords
                click_x += client_left
                click_y += client_top
                print(f"[调试] 客户区偏移: left={client_left}, top={client_top}")
            else:
                # 回退到使用窗口坐标
                click_x += self.game_window.left
                click_y += self.game_window.top
                print(f"[调试] 窗口偏移: left={self.game_window.left}, top={self.game_window.top}")

        print(f"[调试] 点击 {checkbox_name} 勾选框: 屏幕坐标=({click_x}, {click_y})")

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

    def move_to_first_relic(self):
        """
        将光标移动到第一个遗物位置

        在筛选完成后调用，确保光标在第一个遗物上，以便后续的状态检测
        """
        # 缩放坐标
        base_x, base_y = self.FIRST_RELIC_POS
        scaled_x = int(base_x * self.scale_x)
        scaled_y = int(base_y * self.scale_y)

        # 计算屏幕坐标（加上窗口偏移）
        try:
            # 尝试使用客户区坐标
            client_left, client_top, _, _ = self._get_client_rect_screen_coords()
            screen_x = client_left + scaled_x
            screen_y = client_top + scaled_y
        except Exception:
            # 回退到使用窗口坐标
            if self.game_window:
                screen_x = self.game_window.left + scaled_x
                screen_y = self.game_window.top + scaled_y
            else:
                print("[错误] 无法获取游戏窗口位置")
                return

        print(f"[信息] 移动光标到第一个遗物位置: 屏幕坐标=({screen_x}, {screen_y})")
        AutomationController.move_mouse(screen_x, screen_y)
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
        # 0. 刷新游戏窗口信息（确保位置和尺寸是最新的）
        self.refresh_window_info()

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

        # 3.5. 验证筛选界面（确保不是排序界面）
        if not self.verify_filter_interface():
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

        # 7. 移动光标到第一个遗物
        self.move_to_first_relic()

        return True

