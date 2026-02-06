# --- START OF FILE main.py ---
import sys
import os
import ctypes

# 高分屏适配
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except:
    ctypes.windll.user32.SetProcessDPIAware()

# 确保能导入当前目录下的模块
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from ui.main_window import MainWindow

if __name__ == "__main__":
    app = MainWindow()
    app.mainloop()