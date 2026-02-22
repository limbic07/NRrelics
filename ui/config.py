"""UI 配置 - 性能优化"""

from PySide6.QtCore import QSize
import sys

# 导航栏配置
NAVIGATION_CONFIG = {
    "icon_size": QSize(32, 32),  # 图标大小
    "acrylic_enabled": True,      # 启用毛玻璃效果
    "animation_enabled": False,   # 禁用动画
}

# 窗口配置
WINDOW_CONFIG = {
    "width": 1200,
    "height": 750,
    "min_width": 1000,
    "min_height": 600,
}

# 检测系统深色模式
def _detect_system_theme():
    """检测 Windows 系统是否启用深色模式"""
    if sys.platform == "win32":
        try:
            import winreg
            registry_path = r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
            registry_key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, registry_path)
            value, _ = winreg.QueryValueEx(registry_key, "AppsUseLightTheme")
            winreg.CloseKey(registry_key)
            # value = 0 表示深色模式，value = 1 表示浅色模式
            return "dark" if value == 0 else "light"
        except Exception:
            return "light"
    return "light"

# 主题配置
THEME_CONFIG = {
    "theme": _detect_system_theme(),  # 自动检测系统主题
}

