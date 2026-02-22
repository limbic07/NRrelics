"""主窗口 - Fluent Design 简洁框架"""

from qfluentwidgets import FluentWindow, NavigationItemPosition, FluentIcon, setTheme, Theme
from PySide6.QtCore import QSize, Signal
from .config import NAVIGATION_CONFIG, WINDOW_CONFIG, THEME_CONFIG
from ui.components.log_manager import LogManager
from core.preset_manager import PresetManager


class MainWindow(FluentWindow):
    """主窗口 - Fluent Design"""

    # 预设变更信号
    presets_changed = Signal()

    def __init__(self):
        super().__init__()
        self.setWindowTitle("NRrelic Bot v2.0.2")

        # 应用窗口配置
        self.resize(WINDOW_CONFIG["width"], WINDOW_CONFIG["height"])
        self.setMinimumSize(WINDOW_CONFIG["min_width"], WINDOW_CONFIG["min_height"])

        # 设置主题
        theme = Theme.LIGHT if THEME_CONFIG["theme"] == "light" else Theme.DARK
        setTheme(theme)

        # 创建中央日志管理器
        self.log_manager = LogManager()

        # 创建共享的预设管理器
        self.preset_manager = PresetManager()

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
        from .pages import ShopPage, RepoPage, SavePage, SettingsPage, AboutPage

        # 商店筛选（传入共享的preset_manager）
        self.shop_page = ShopPage(log_manager=self.log_manager, preset_manager=self.preset_manager)
        self.addSubInterface(
            self.shop_page,
            FluentIcon.SHOPPING_CART,
            "商店筛选",
            NavigationItemPosition.TOP
        )

        # 仓库清理（传入共享的preset_manager）
        self.repo_page = RepoPage(log_manager=self.log_manager, preset_manager=self.preset_manager)
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

        # 关于
        self.about_page = AboutPage()
        self.addSubInterface(
            self.about_page,
            FluentIcon.INFO,
            "关于",
            NavigationItemPosition.BOTTOM
        )

        # 连接Steam路径变更信号
        self.settings_page.steam_path_changed.connect(self.save_page.update_steam_path)

        # 连接关于页面彩蛋信号 → 设置页面显示开发者设置
        self.about_page.developer_mode_activated.connect(self.settings_page.show_developer_settings)

        # 连接设置变更信号 → 商店页面更新设置
        self.settings_page.settings_changed.connect(self.shop_page.update_settings)

        # 连接预设变更信号：当任一页面修改预设时，通知另一页面刷新
        self.shop_page.presets_modified.connect(self._on_presets_changed)
        self.repo_page.presets_modified.connect(self._on_presets_changed)

    def _on_presets_changed(self):
        """预设变更时，通知所有页面刷新"""
        # 重新加载预设
        self.preset_manager.load_presets()
        # 通知两个页面刷新UI
        if hasattr(self.shop_page, 'refresh_presets_ui'):
            self.shop_page.refresh_presets_ui()
        if hasattr(self.repo_page, 'refresh_presets_ui'):
            self.repo_page.refresh_presets_ui()

    def init_ocr_dependencies(self, engine):
        """初始化 OCR 依赖（异步加载完成后调用）"""
        if self.repo_page:
            self.repo_page.set_ocr_engine(engine)
        if self.shop_page:
            self.shop_page.set_ocr_engine(engine)
