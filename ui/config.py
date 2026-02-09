"""UI 配置 - 性能优化"""

from PySide6.QtCore import QSize

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

# 主题配置
THEME_CONFIG = {
    "theme": "light",  # light 或 dark
}

