"""自动化操作模块"""

import pyautogui
import pydirectinput
import time


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
