"""主窗口 - Fluent Design 简洁框架"""

from qfluentwidgets import FluentWindow, NavigationItemPosition, FluentIcon, setTheme, Theme
from PySide6.QtCore import QSize
from .config import NAVIGATION_CONFIG, WINDOW_CONFIG, THEME_CONFIG


class MainWindow(FluentWindow):
    """主窗口 - Fluent Design"""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("NRrelic Bot v2.0.0")

        # 应用窗口配置
        self.resize(WINDOW_CONFIG["width"], WINDOW_CONFIG["height"])
        self.setMinimumSize(WINDOW_CONFIG["min_width"], WINDOW_CONFIG["min_height"])

        # 设置主题
        theme = Theme.LIGHT if THEME_CONFIG["theme"] == "light" else Theme.DARK
        setTheme(theme)

        # 优化导航栏
        self._optimize_navigation()

        # 初始化页面
        self._init_pages()

    def _optimize_navigation(self):
        """优化导航栏配置"""
        # 启用毛玻璃效果
        self.navigationInterface.setAcrylicEnabled(NAVIGATION_CONFIG["acrylic_enabled"])

    def _init_pages(self):
        """初始化页面"""
        from .pages import ShopPage, RepoPage, SavePage, SettingsPage

        # 商店筛选
        self.shop_page = ShopPage()
        self.addSubInterface(
            self.shop_page,
            FluentIcon.SHOPPING_CART,
            "商店筛选",
            NavigationItemPosition.TOP
        )

        # 仓库清理
        self.repo_page = RepoPage()
        self.addSubInterface(
            self.repo_page,
            FluentIcon.FOLDER,
            "仓库清理",
            NavigationItemPosition.TOP
        )

        # 存档管理
        self.save_page = SavePage()
        self.addSubInterface(
            self.save_page,
            FluentIcon.SAVE,
            "存档管理",
            NavigationItemPosition.TOP
        )

        # 设置
        self.settings_page = SettingsPage()
        self.addSubInterface(
            self.settings_page,
            FluentIcon.SETTING,
            "设置",
            NavigationItemPosition.BOTTOM
        )
