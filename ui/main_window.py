"""主窗口 - Fluent Design 简洁框架"""
from ctypes.wintypes import MSG
import pywintypes
import win32con
import win32gui

from qfluentwidgets import FluentWindow, NavigationItemPosition, FluentIcon, setTheme, Theme
from PySide6.QtCore import QSize, Signal, QTimer
from .config import NAVIGATION_CONFIG, WINDOW_CONFIG, THEME_CONFIG
from ui.components.log_manager import LogManager
from core.preset_manager import PresetManager


class MainWindow(FluentWindow):
    """主窗口 - Fluent Design"""

    # 预设变更信号
    presets_changed = Signal()

    def __init__(self):
        super().__init__()
        self.setWindowTitle("NRrelic Bot v3.1.1")

        # 应用窗口配置
        self.resize(WINDOW_CONFIG["width"], WINDOW_CONFIG["height"])
        self.setMinimumSize(WINDOW_CONFIG["min_width"], WINDOW_CONFIG["min_height"])

        # 设置主题
        theme = Theme.LIGHT if THEME_CONFIG["theme"] == "light" else Theme.DARK
        setTheme(theme)
        # Native Qt dialogs and tables must use the same palette as Fluent widgets.
        from PySide6.QtWidgets import QApplication
        from PySide6.QtGui import QPalette, QColor
        app = QApplication.instance()
        palette = app.style().standardPalette()
        if theme == Theme.DARK:
            colors = {"Window": "#202020", "WindowText": "#eeeeee",
                      "Base": "#2b2b2b", "AlternateBase": "#323232",
                      "Text": "#eeeeee", "Button": "#333333", "ButtonText": "#eeeeee",
                      "Mid": "#555555", "Highlight": "#285361", "HighlightedText": "#ffffff",
                      "ToolTipBase": "#333333", "ToolTipText": "#eeeeee",
                      "Link": "#66c5dd", "PlaceholderText": "#aaaaaa"}
            for role, color in colors.items():
                palette.setColor(getattr(QPalette.ColorRole, role), QColor(color))
            for role in (QPalette.Text, QPalette.ButtonText, QPalette.WindowText):
                palette.setColor(QPalette.Disabled, role, QColor("#999999"))
        else:
            # Windows standardPalette may use a beige system background rather
            # than the light Fluent surface used by the rest of the application.
            colors = {"Window": "#f5f5f5", "WindowText": "#202020",
                      "Base": "#ffffff", "AlternateBase": "#f5f5f5",
                      "Text": "#202020", "Button": "#fafafa", "ButtonText": "#202020",
                      "Mid": "#d8d8d8", "Highlight": "#dceffc", "HighlightedText": "#202020",
                      "ToolTipBase": "#ffffff", "ToolTipText": "#202020",
                      "Link": "#176b8b", "PlaceholderText": "#777777"}
            for role, color in colors.items():
                palette.setColor(getattr(QPalette.ColorRole, role), QColor(color))
            for role in (QPalette.Text, QPalette.ButtonText, QPalette.WindowText):
                palette.setColor(QPalette.Disabled, role, QColor("#888888"))
        app.setPalette(palette)
        app.setStyleSheet(app.styleSheet() + "\nQDialog, QMessageBox { color: palette(window-text); background: palette(window); }\n"
                          "QTableWidget, QTreeWidget, QListWidget, QTextBrowser { color: palette(text); background: palette(base); }\n"
                          "QHeaderView::section { color: palette(button-text); background: palette(button); }\n")

        # 通过 Fluent 的开关禁用云母，避免背景仍透明、showEvent 再次启用系统背景。
        self.setMicaEffectEnabled(False)

        # 创建中央日志管理器
        self.log_manager = LogManager()

        # 创建共享的预设管理器
        self.preset_manager = PresetManager()

        # 优化导航栏
        self._optimize_navigation()

        # 初始化页面
        self._repo_hotkeys = set()
        self._init_pages()

    def _sync_repo_hotkeys(self):
        # 以所选页面而非可见性决定 F10 目标，最小化或切回游戏后仍可接收。
        needed = self.stackedWidget.currentWidget() is self.repo_page or self.repo_page.stop_btn.isEnabled()
        hwnd = int(self.winId())
        for key in (win32con.VK_F10, win32con.VK_F11):
            if needed and key not in self._repo_hotkeys:
                try:
                    win32gui.RegisterHotKey(hwnd, key, 0x4000, key)  # MOD_NOREPEAT
                    self._repo_hotkeys.add(key)
                except pywintypes.error:
                    label = "F10" if key == win32con.VK_F10 else "F11"
                    self.repo_page._on_log(f"{label} 全局快捷键注册失败，请使用仓库清理页按钮。", "WARNING")
            elif not needed and key in self._repo_hotkeys:
                win32gui.UnregisterHotKey(hwnd, key)
                self._repo_hotkeys.remove(key)

    def nativeEvent(self, event_type, message):
        msg = MSG.from_address(int(message))
        if msg.message == win32con.WM_HOTKEY and msg.wParam in getattr(self, "_repo_hotkeys", ()):
            if msg.wParam == win32con.VK_F10:
                self.repo_page._on_start_shortcut()
            elif self.repo_page.stop_btn.isEnabled():
                self.repo_page._stop_cleaning()
            return True, 0
        return super().nativeEvent(event_type, message)

    def _optimize_navigation(self):
        """优化导航栏配置"""
        # 禁用毛玻璃效果，防止跟随系统主题变化
        self.navigationInterface.setAcrylicEnabled(False)

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

        from .pages.page_relics import RelicPage
        self.relic_page = RelicPage(self.preset_manager, 'inventory')
        self.addSubInterface(self.relic_page, FluentIcon.TILES, "遗物管理",
                             NavigationItemPosition.TOP)
        self.loadout_page = RelicPage(self.preset_manager, 'optimizer')
        self.addSubInterface(self.loadout_page, FluentIcon.ROBOT, "配装优化",
                             NavigationItemPosition.TOP)

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
        self.save_page.steam_path_selected.connect(self.settings_page.set_steam_path)

        # 连接设置变更信号 → 商店页面更新设置
        self.settings_page.settings_changed.connect(self.shop_page.update_settings)
        self.settings_page.settings_changed.connect(
            self.repo_page.refresh_scoring_display)

        # 连接预设变更信号：当任一页面修改预设时，通知另一页面刷新
        from ui.pages.page_repo import sync_preset_activation
        self.shop_page.preset_activation_changed.connect(
            lambda mode: sync_preset_activation(self.repo_page, mode))
        self.repo_page.preset_activation_changed.connect(
            lambda mode: sync_preset_activation(self.shop_page, mode))
        self.shop_page.presets_modified.connect(self._on_presets_changed)
        self.repo_page.presets_modified.connect(self._on_presets_changed)
        self.shop_page.preset_updated.connect(
            lambda mode, pid: self._on_one_preset_updated(self.repo_page, mode, pid))
        self.repo_page.preset_updated.connect(
            lambda mode, pid: self._on_one_preset_updated(self.shop_page, mode, pid))
        self.shop_page.preset_list_changed.connect(
            lambda mode, pid, action: self._on_preset_list_changed(
                self.repo_page, mode, pid, action))
        self.repo_page.preset_list_changed.connect(
            lambda mode, pid, action: self._on_preset_list_changed(
                self.shop_page, mode, pid, action))

        # 旧配置可能仍指向失效的 C 盘默认目录；将实际检测到的路径同步给所有页面。
        configured_path = self.settings_page.get_settings().get("steam_path", "")
        detected_path = self.save_page.save_manager.steam_path
        if detected_path and not self.save_page.save_manager.is_valid_steam_path(configured_path):
            self.settings_page.set_steam_path(detected_path)

        self.stackedWidget.currentChanged.connect(self._sync_repo_hotkeys)
        self.repo_page.cleaning_finished.connect(self._sync_repo_hotkeys)
        self._sync_repo_hotkeys()

    def _on_presets_changed(self):
        """预设变更时，通知所有页面刷新"""
        # Both pages share the manager; the emitting page already refreshed itself.
        source = self.sender()
        for page in (self.shop_page, self.repo_page):
            if page is not source:
                page.refresh_presets_ui()

    def _on_one_preset_updated(self, page, mode, preset_id):
        from ui.pages.page_repo import refresh_one_preset_card
        from core.relic_scoring import normalize_scoring
        settings = (page.settings if page is self.shop_page else page._load_settings())
        refresh_one_preset_card(page, mode, preset_id,
                                normalize_scoring(settings.get('scoring'))['enabled'])

    def _on_preset_list_changed(self, page, mode, preset_id, action):
        from ui.pages.page_repo import add_one_preset_card, remove_one_preset_card
        from core.relic_scoring import normalize_scoring
        if action == 'create':
            settings = page.settings if page is self.shop_page else page._load_settings()
            add_one_preset_card(page, mode, preset_id,
                                normalize_scoring(settings.get('scoring'))['enabled'])
        elif action == 'delete':
            remove_one_preset_card(page, mode, preset_id)

    def init_ocr_dependencies(self, engine):
        """初始化 OCR 依赖（异步加载完成后调用）"""
        if self.repo_page:
            self.repo_page.set_ocr_engine(engine)
        if self.shop_page:
            self.shop_page.set_ocr_engine(engine)

    def closeEvent(self, event):
        repo = getattr(self, "repo_page", None)
        if repo and repo.cleaning_thread and repo.cleaning_thread.isRunning():
            event.ignore()
            repo._stop_cleaning()
            QTimer.singleShot(250, self.close)
            return
        page = getattr(self, 'loadout_page', None)
        if page is not None and page.worker is not None:
            event.ignore()
            page._stop_deep_search()
            QTimer.singleShot(250, self.close)
            return
        if page is not None:
            page.release_results()
        for key in self._repo_hotkeys:
            win32gui.UnregisterHotKey(int(self.winId()), key)
        self._repo_hotkeys.clear()
        super().closeEvent(event)
