# --- START OF FILE grab_tools.py ---
import mss
import cv2
import numpy as np
import keyboard
import time
import os
import ctypes

# 开启 DPI 感知
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except:
    ctypes.windll.user32.SetProcessDPIAware()


def grab_template(name, width=40, height=40):
    """
    截取鼠标当前位置周围的小图片
    """
    # 需要安装 pyautogui: pip install pyautogui
    import pyautogui
    x, y = pyautogui.position()

    # 计算截图区域 (以鼠标为中心)
    left = int(x - width // 2)
    top = int(y - height // 2)

    with mss.mss() as sct:
        monitor = {"left": left, "top": top, "width": width, "height": height}
        img = np.array(sct.grab(monitor))
        img = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)

        if not os.path.exists("data"):
            os.makedirs("data")

        filename = f"data/tpl_{name}.png"
        cv2.imwrite(filename, img)
        print(f"✅ 已保存: {filename} (坐标: {x},{y} | 大小: {width}x{height})")


print("=== 素材抓取工具 ===")
print("请将鼠标【精准悬停】在你要截取的图标中心")
print("1. 悬停在【光标左上角边框】 -> 按 F5 (建议抓 60x60)")
print("2. 悬停在【装备图标(小酒杯)】 -> 按 F6 (建议抓 30x30)")
print("3. 悬停在【收藏图标(小书签)】 -> 按 F7 (建议抓 30x30)")
print("按 ESC 退出")

while True:
    try:
        if keyboard.is_pressed('f5'):
            grab_template("cursor", width=100, height=20)
            time.sleep(0.5)

        if keyboard.is_pressed('f6'):
            grab_template("equip", width=25, height=25)
            time.sleep(0.5)

        if keyboard.is_pressed('f7'):
            grab_template("lock", width=25, height=25)
            time.sleep(0.5)

        if keyboard.is_pressed('esc'):
            break

        time.sleep(0.1)
    except Exception as e:
        print(f"错误: {e}")