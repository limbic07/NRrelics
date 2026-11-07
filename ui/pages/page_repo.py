"""
仓库清理页面 - 完整实现
包含预设管理、清理控制、日志显示和统计仪表盘
"""

from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                               QPushButton, QComboBox, QTabWidget,
                               QScrollArea, QFrame, QSplitter, QGroupBox, QCheckBox, QLineEdit,
                               QTreeWidget, QTreeWidgetItem)
from PySide6.QtCore import Qt, Signal, QThread, QMimeData, QPoint, QTimer
from PySide6.QtGui import QFont, QIntValidator, QDrag, QPixmap
import keyboard
from qfluentwidgets import (CardWidget, PrimaryPushButton, PushButton,
                           ComboBox, MessageBox, InfoBar, InfoBarPosition,
                           isDarkTheme)

from core.preset_manager import PresetManager, PRESET_TYPE_NORMAL_WHITELIST, PRESET_TYPE_DEEPNIGHT_WHITELIST
from core.relic_scoring import normalize_scoring
from ui.components.logger_widget import LoggerWidget
from core.utils import get_user_data_path
import json
import os
from datetime import datetime

# 持久化数据文件路径
SOLD_RELICS_FILE = get_user_data_path("data/repo_sold_relics.json")
FAVORITED_RELICS_FILE = get_user_data_path("data/repo_favorited_relics.json")


class DragDropContainer(QWidget):
    """支持拖放排序的容器"""
    reorder_requested = Signal(str, str)  # (source_id, target_id)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(8)

    def add_card(self, card, index=None):
        """添加卡片"""
        if card.is_general:
            # 通用预设不支持拖放
            self.layout.addWidget(card)
            return

        card.setAcceptDrops(True)

        # 使用闭包保存卡片引用
        def make_mouse_press(c):
            def handler(event):
                if event.button() == Qt.LeftButton:
                    c._drag_start_pos = event.pos()
                CardWidget.mousePressEvent(c, event)
            return handler

        def make_mouse_move(c):
            def handler(event):
                if (hasattr(c, '_drag_start_pos') and
                    event.buttons() == Qt.LeftButton):
                    distance = (event.pos() - c._drag_start_pos).manhattanLength()
                    if distance > 20:
                        mime_data = QMimeData()
                        mime_data.setText(c.preset_data["id"])
                        drag = QDrag(c)
                        drag.setMimeData(mime_data)
                        drag.exec(Qt.MoveAction)
                CardWidget.mouseMoveEvent(c, event)
            return handler

        def make_drag_enter(c):
            def handler(event):
                if event.mimeData().hasText():
                    event.acceptProposedAction()
                else:
                    event.ignore()
            return handler

        def make_drop(c):
            def handler(event):
                if event.mimeData().hasText():
                    source_id = event.mimeData().text()
                    target_id = c.preset_data["id"]
                    if source_id != target_id:
                        self.reorder_requested.emit(source_id, target_id)
                    event.acceptProposedAction()
                else:
                    event.ignore()
            return handler

        card.mousePressEvent = make_mouse_press(card)
        card.mouseMoveEvent = make_mouse_move(card)
        card.dragEnterEvent = make_drag_enter(card)
        card.dropEvent = make_drop(card)

        if index is None:
            self.layout.addWidget(card)
        else:
            self.layout.insertWidget(index, card)

    def replace_card(self, preset_id, card):
        for index in range(self.layout.count()):
            old = self.layout.itemAt(index).widget()
            if old and old.preset_data.get('id') == preset_id:
                self.layout.removeWidget(old)
                old.deleteLater()
                self.add_card(card, index)
                return True
        return False

    def remove_card(self, preset_id):
        for index in range(self.layout.count()):
            card = self.layout.itemAt(index).widget()
            if card and card.preset_data.get('id') == preset_id:
                self.layout.removeWidget(card)
                card.deleteLater()
                return True
        return False


class CleaningThread(QThread):
    """清理线程"""
    log_signal = Signal(str, str)  # (message, level)
    finished_signal = Signal()
    qualified_relic_signal = Signal(dict)  # 合格遗物信息
    result_signal = Signal(dict)

    def __init__(self, cleaner, mode, cleaning_mode, max_relics, allow_favorited, require_double):
        super().__init__()
        self.cleaner = cleaner
        self.mode = mode
        self.cleaning_mode = cleaning_mode
        self.max_relics = max_relics
        self.allow_favorited = allow_favorited
        self.require_double = require_double

    def run(self):
        """运行清理"""
        try:
            self.cleaner.start_cleaning(
                self.mode,
                self.cleaning_mode,
                self.max_relics,
                self.allow_favorited,
                self.require_double,
                log_callback=self.log_signal.emit,
                result_callback=self.result_signal.emit
            )

            # 清理完成后，发送所有合格遗物信息
            for relic_info in self.cleaner.qualified_relics:
                self.qualified_relic_signal.emit(relic_info)

        except Exception as e:
            self.log_signal.emit(f"清理过程出错: {e}", "ERROR")
        finally:
            self.finished_signal.emit()


class PresetCard(CardWidget):
    """预设卡片（带词条展开功能）"""
    edit_clicked = Signal(str)  # preset_id
    delete_clicked = Signal(str)  # preset_id
    toggle_clicked = Signal(str)  # preset_id

    def __init__(self, preset_data: dict, is_general: bool = False, parent=None,
                 inherited_affixes=None, score_enabled=False):
        super().__init__(parent)
        self.preset_data = preset_data
        self.is_general = is_general
        self.inherited_affixes = set(inherited_affixes or [])
        self.score_enabled = score_enabled
        self.is_expanded = False

        self._init_ui()

    def _required_groups(self):
        if self.score_enabled:
            return []
        from core.relic_matcher import _required_groups
        groups, _, valid = _required_groups(self.preset_data)
        if not valid:
            return ["无效必须词条组，请编辑修正"]
        return [
            [member + "（通用）" if member in self.inherited_affixes else member
             for member in group]
            for group in groups
        ]

    def _graded_affix(self, affix):
        if self.preset_data.get("type") == "deepnight_blacklist":
            return affix
        tier = self.preset_data.get("affix_tiers", {}).get(affix, "secondary")
        label = {"core": "重要", "secondary": "次要", "bonus": "锦上添花"}.get(tier, "次要")
        return f"【{label}】{affix}"

    @staticmethod
    def _group_summary(groups):
        rendered = []
        for group in groups:
            if isinstance(group, list):
                rendered.append("(" + " 或 ".join(str(member) for member in group) + ")")
            else:
                rendered.append("(" + str(group) + ")")
        return "；".join(rendered)

    def _init_ui(self):
        """初始化UI"""
        # 存储需要动态颜色的标签，用于主题切换时刷新
        self._theme_labels = []

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(12, 10, 12, 10)
        main_layout.setSpacing(8)

        # 顶部：预设信息和按钮
        top_layout = QHBoxLayout()
        top_layout.setSpacing(8)

        # 展开/折叠按钮
        self.expand_btn = QPushButton("▶" if not self.is_expanded else "▼")
        self.expand_btn.setFixedSize(20, 20)
        self.expand_btn.clicked.connect(self._toggle_expand)
        top_layout.addWidget(self.expand_btn)

        # 预设信息
        info_layout = QVBoxLayout()
        info_layout.setSpacing(2)

        # 名称
        groups = self._required_groups()
        name_label = QLabel(("★ " if groups else "")
                            + self.preset_data["name"])
        name_font = QFont("", 10)  # 指定字号避免-1错误
        name_font.setBold(True)
        name_label.setFont(name_font)
        name_label.setTextFormat(Qt.PlainText)
        info_layout.addWidget(name_label)

        # 词条数量
        count_text = f"{len(self.preset_data['affixes'])} 条正面词条"
        if self.score_enabled and self.preset_data.get("negative_tiers"):
            count_text += f" · {len(self.preset_data['negative_tiers'])} 条负面调整"
        self._count_label = QLabel(count_text)
        self._count_label.setStyleSheet("color: #888; font-size: 10pt;")
        self._theme_labels.append(self._count_label)
        info_layout.addWidget(self._count_label)
        if groups:
            summary = "必须：" + self._group_summary(groups)
            self._requirements_label = QLabel(summary)
            self._requirements_label.setWordWrap(True)
            self._requirements_label.setTextFormat(Qt.PlainText)
            self._requirements_label.setStyleSheet("color: #b06a00; font-size: 9pt;")
            info_layout.addWidget(self._requirements_label)

        top_layout.addLayout(info_layout)
        top_layout.addStretch()

        # 按钮
        if not self.is_general:
            # 启用/禁用复选框
            self.active_checkbox = QCheckBox("启用")
            self.active_checkbox.setChecked(self.preset_data.get("is_active", True))
            self.active_checkbox.stateChanged.connect(
                lambda: self.toggle_clicked.emit(self.preset_data["id"])
            )
            top_layout.addWidget(self.active_checkbox)

        # 编辑按钮
        edit_btn = PushButton("编辑")
        edit_btn.setFixedWidth(60)
        edit_btn.clicked.connect(lambda: self.edit_clicked.emit(self.preset_data["id"]))
        top_layout.addWidget(edit_btn)

        # 删除按钮（仅专用预设）
        if not self.is_general:
            delete_btn = PushButton("删除")
            delete_btn.setFixedWidth(60)
            delete_btn.clicked.connect(lambda: self.delete_clicked.emit(self.preset_data["id"]))
            top_layout.addWidget(delete_btn)

        main_layout.addLayout(top_layout)

        # 词条列表（可展开）
        self.affixes_widget = QWidget()
        self._affixes_layout = QVBoxLayout(self.affixes_widget)
        self._affixes_layout.setContentsMargins(24, 4, 4, 4)
        self._affixes_layout.setSpacing(2)
        self._affix_labels = []
        self._more_label = None
        self._affixes_populated = False
        self.affixes_widget.setVisible(False)
        main_layout.addWidget(self.affixes_widget)

        # 应用初始主题颜色
        self._apply_theme_colors()

    def _populate_affixes(self):
        """Create the hidden affix labels only when this card is opened."""
        self._affixes_populated = True
        groups = self._required_groups()
        group_by_affix = {}
        for index, group in enumerate(groups, 1):
            if isinstance(group, list):
                for affix in group:
                    if isinstance(affix, str):
                        group_by_affix.setdefault(affix, []).append(index)
        for affix in self.preset_data["affixes"][:20]:
            marker = (
                " ★" + "、".join(f"组{index}" for index in group_by_affix[affix])
                if affix in group_by_affix else ""
            )
            affix_label = QLabel(f"• {self._graded_affix(affix)}{marker}")
            affix_label.setFont(QFont("Segoe UI", 9))
            affix_label.setStyleSheet("color: #555;")
            affix_label.setWordWrap(True)
            self._affix_labels.append(affix_label)
            self._theme_labels.append(affix_label)
            self._affixes_layout.addWidget(affix_label)

        if len(self.preset_data["affixes"]) > 20:
            self._more_label = QLabel(f"... 还有 {len(self.preset_data['affixes']) - 20} 条")
            self._more_label.setFont(QFont("Segoe UI", 9))
            self._more_label.setStyleSheet("color: #999; font-style: italic;")
            self._theme_labels.append(self._more_label)
            self._affixes_layout.addWidget(self._more_label)
        for affix in self.preset_data["affixes"][20:]:
            if affix in group_by_affix:
                marker = " ★" + "、".join(
                    f"组{index}" for index in group_by_affix[affix]
                )
                label = QLabel(f"• {self._graded_affix(affix)}{marker}")
                label.setFont(QFont("Segoe UI", 9))
                label.setStyleSheet("color: #555;")
                label.setWordWrap(True)
                self._affix_labels.append(label)
                self._theme_labels.append(label)
                self._affixes_layout.addWidget(label)

        if self.score_enabled:
            tier_names = {"core": "重要", "secondary": "次要", "bonus": "锦上添花",
                          "unacceptable": "不可接受", "harmful": "很伤",
                          "negligible": "几乎无负面"}
            for affix, tier in self.preset_data.get("negative_tiers", {}).items():
                label = QLabel(f"• 【{tier_names.get(tier, tier)}】{affix}")
                label.setWordWrap(True)
                self._affix_labels.append(label)
                self._theme_labels.append(label)
                self._affixes_layout.addWidget(label)
            for affix in self.preset_data.get("excluded_affixes", []):
                label = QLabel(f"• 【排除通用】{affix}")
                label.setWordWrap(True)
                self._affix_labels.append(label)
                self._theme_labels.append(label)
                self._affixes_layout.addWidget(label)

        self._apply_theme_colors()

    def _apply_theme_colors(self):
        """根据当前主题更新颜色"""
        dark = isDarkTheme()

        # 展开按钮
        btn_hover_bg = "#3d3d3d" if dark else "#f0f0f0"
        btn_color = "#e0e0e0" if dark else "#333"
        self.expand_btn.setStyleSheet(f"""
            QPushButton {{
                border: none;
                background: transparent;
                font-size: 10pt;
                color: {btn_color};
            }}
            QPushButton:hover {{
                background: {btn_hover_bg};
                border-radius: 3px;
            }}
        """)

        # 词条数量标签
        count_color = "#aaaaaa" if dark else "#888"
        self._count_label.setStyleSheet(f"color: {count_color}; font-size: 10pt;")

        # 词条列表项
        affix_color = "#cccccc" if dark else "#555"
        for label in self._affix_labels:
            label.setStyleSheet(f"color: {affix_color};")

        # "...还有 N 条"
        if self._more_label is not None:
            more_color = "#888888" if dark else "#999"
            self._more_label.setStyleSheet(f"color: {more_color}; font-style: italic;")

    def _toggle_expand(self):
        """切换展开/折叠"""
        self.is_expanded = not self.is_expanded
        if self.is_expanded and not self._affixes_populated:
            self._populate_affixes()
        self.expand_btn.setText("▼" if self.is_expanded else "▶")
        self.affixes_widget.setVisible(self.is_expanded)

def refresh_one_preset_card(page, mode, preset_id, score_enabled):
    """Replace only the edited dedicated card in the currently displayed mode."""
    if not getattr(page, '_presets_loaded', False):
        return
    shown_mode = 'normal' if page.mode_combo.currentIndex() == 0 else 'deepnight'
    if shown_mode != mode:
        return
    container = getattr(page, 'preset_container', None)
    preset = page.preset_manager.get_dedicated_presets(mode).get(preset_id)
    if container is None or preset is None:
        page._refresh_presets()
        return
    card = make_dedicated_card(page, mode, preset, score_enabled)
    if not container.replace_card(preset_id, card):
        card.deleteLater()
        page._refresh_presets()


def make_dedicated_card(page, mode, preset, score_enabled):
    general = page.preset_manager.get_general_preset(mode)
    card = PresetCard(
        preset, is_general=False,
        inherited_affixes=general.get('affixes', [])
        if general and general.get('is_active', True) else [],
        score_enabled=score_enabled)
    card.edit_clicked.connect(page._edit_dedicated_preset)
    card.delete_clicked.connect(page._delete_preset)
    card.toggle_clicked.connect(page._toggle_preset)
    return card


def add_one_preset_card(page, mode, preset_id, score_enabled):
    if not getattr(page, '_presets_loaded', False):
        return
    shown_mode = 'normal' if page.mode_combo.currentIndex() == 0 else 'deepnight'
    if shown_mode != mode:
        return
    container = getattr(page, 'preset_container', None)
    preset = page.preset_manager.get_dedicated_presets(mode).get(preset_id)
    if not preset:
        return
    if container is None:
        container = DragDropContainer()
        container.reorder_requested.connect(page._handle_preset_reorder)
        page.preset_container = container
        general = page.preset_manager.get_general_preset(mode)
        page.preset_layout.insertWidget(1 if general else 0, container)
    container.add_card(make_dedicated_card(page, mode, preset, score_enabled))


def remove_one_preset_card(page, mode, preset_id):
    if not getattr(page, '_presets_loaded', False):
        return
    shown_mode = 'normal' if page.mode_combo.currentIndex() == 0 else 'deepnight'
    if shown_mode == mode:
        container = getattr(page, 'preset_container', None)
        if container:
            container.remove_card(preset_id)


class RepoPage(QWidget):
    """仓库清理页面"""

    # 预设修改信号
    presets_modified = Signal()
    preset_updated = Signal(str, str)
    preset_list_changed = Signal(str, str, str)
    scan_requested = Signal()
    clean_requested = Signal()
    stop_requested = Signal()

    def __init__(self, log_manager=None, preset_manager=None):
        super().__init__()
        self.setObjectName("RepoPage")

        # 初始化组件
        self.preset_manager = preset_manager if preset_manager else PresetManager()
        self.ocr_engine = None  # 延迟加载，初始为 None
        self.relic_detector = None  # 延迟加载
        self.repo_cleaner = None  # 延迟加载

        # 清理线程
        self.cleaning_thread = None

        # 当前模式
        self.current_mode = "normal"

        # 加载设置
        self.settings = self._load_settings()

        # 日志管理器
        self.log_manager = log_manager

        # 加载持久化的售出和收藏遗物
        self.sold_relics = self._load_sold_relics()
        self.favorited_relics = self._load_favorited_relics()

        # 标记是否手动停止
        self.is_manual_stop = False

        self._presets_loaded = False
        self._init_ui()
        self.scan_requested.connect(self._start_scanning, Qt.QueuedConnection)
        self.clean_requested.connect(self._start_cleaning, Qt.QueuedConnection)
        self.stop_requested.connect(self._stop_cleaning, Qt.QueuedConnection)

    def showEvent(self, event):
        super().showEvent(event)
        if not self._presets_loaded:
            QTimer.singleShot(50, self._load_presets_when_visible)

    def _load_presets_when_visible(self):
        if self.isVisible() and not self._presets_loaded:
            self._refresh_presets()

    def _init_ui(self):
        """初始化UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 8, 16, 16)
        layout.setSpacing(6)

        # 标题
        title = QLabel("仓库清理")
        title.setStyleSheet("font-size: 24pt; font-weight: bold;")
        layout.addWidget(title)

        # 顶部工具栏（紧凑版）
        toolbar = self._create_toolbar()
        layout.addWidget(toolbar)

        # 主内容区域（分割器）
        splitter = QSplitter(Qt.Horizontal)

        # 左侧：预设面板
        preset_panel = self._create_preset_panel()
        splitter.addWidget(preset_panel)

        # 右侧：日志和仪表盘
        right_panel = self._create_right_panel()
        splitter.addWidget(right_panel)

        # 调整比例：预设面板更大
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 3)

        # 设置初始尺寸（确保2:3比例）
        splitter.setSizes([400, 600])

        layout.addWidget(splitter, 1)

        # 设置快捷键
        self._setup_shortcuts()

    def _create_toolbar(self) -> CardWidget:
        """创建顶部工具栏（紧凑版）"""
        card = CardWidget()
        card.setFixedHeight(60)
        layout = QHBoxLayout(card)
        layout.setContentsMargins(12, 6, 12, 6)
        layout.setSpacing(12)

        # 模式选择
        mode_label = QLabel("模式:")
        layout.addWidget(mode_label)

        self.mode_combo = ComboBox()
        self.mode_combo.addItems(["普通", "深夜"])
        self.mode_combo.setFixedWidth(100)
        self.mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        layout.addWidget(self.mode_combo)

        layout.addSpacing(10)

        # 清理模式
        clean_mode_label = QLabel("清理:")
        layout.addWidget(clean_mode_label)

        self.clean_mode_combo = ComboBox()
        self.clean_mode_combo.addItems(["售出", "收藏"])
        self.clean_mode_combo.setFixedWidth(100)
        self.clean_mode_combo.currentIndexChanged.connect(self._on_clean_mode_changed)
        layout.addWidget(self.clean_mode_combo)

        layout.addSpacing(10)

        # 清理数量
        max_label = QLabel("数量:")
        layout.addWidget(max_label)

        self.max_input = QLineEdit()
        self.max_input.setText("100")
        self.max_input.setFixedWidth(100)
        self.max_input.setFixedHeight(33)  # 匹配ComboBox高度
        # 设置验证器：只允许输入1-2000的整数
        validator = QIntValidator(1, 2000, self)
        self.max_input.setValidator(validator)
        self.max_input.setPlaceholderText("1-2000")
        self.max_input.setVisible(False)  # 默认隐藏输入框
        layout.addWidget(self.max_input)

        # 自动检测复选框
        self.auto_detect_checkbox = QCheckBox("自动检测")
        self.auto_detect_checkbox.setChecked(True)  # 默认启用自动检测
        self.auto_detect_checkbox.stateChanged.connect(self._on_auto_detect_changed)
        layout.addWidget(self.auto_detect_checkbox)

        layout.addStretch()

        # 开始/停止按钮
        self.start_btn = PrimaryPushButton("初始化OCR...")
        self.start_btn.setFixedHeight(36)
        self.start_btn.setFixedWidth(120)
        self.start_btn.setEnabled(False)
        self.start_btn.clicked.connect(self._start_cleaning)
        layout.addWidget(self.start_btn)

        self.scan_btn = PushButton("仓库检索(F9)")
        self.scan_btn.setFixedHeight(36)
        self.scan_btn.setFixedWidth(125)
        self.scan_btn.setEnabled(False)
        self.scan_btn.clicked.connect(self._start_scanning)
        layout.addWidget(self.scan_btn)

        self.stop_btn = PushButton("停止 (F11)")
        self.stop_btn.setFixedHeight(36)
        self.stop_btn.setFixedWidth(80)
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self._stop_cleaning)
        layout.addWidget(self.stop_btn)

        return card

    def _create_preset_panel(self) -> QWidget:
        """创建预设面板"""
        panel = QWidget()
        panel.setMinimumWidth(400)  # 设置最小宽度
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        # 标题（紧凑版）
        title = QLabel("预设管理")
        title.setStyleSheet("font-size: 13pt; font-weight: bold; padding: 4px 0;")
        header = QHBoxLayout()
        header.addWidget(title)
        header.addStretch()
        restore = PushButton('恢复默认预设')
        restore.clicked.connect(self._restore_default_presets)
        header.addWidget(restore)
        layout.addLayout(header)

        # 滚动区域
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        scroll_content = QWidget()
        self.preset_layout = QVBoxLayout(scroll_content)
        self.preset_layout.setSpacing(8)
        self.preset_layout.addWidget(QLabel('正在加载预设…'))

        scroll.setWidget(scroll_content)
        layout.addWidget(scroll)

        return panel

    def _restore_default_presets(self):
        prompt = MessageBox('确认恢复默认预设',
                            '这会将普通、深夜的通用和专用预设全部恢复为程序内置版本。'
                            '确定继续吗？', self)
        if prompt.exec() != MessageBox.Accepted:
            return
        try:
            self.preset_manager.restore_bundled_defaults()
        except Exception as exc:
            MessageBox('恢复失败', str(exc), self).exec()
            return
        self._refresh_presets()
        self.presets_modified.emit()
        InfoBar.success('已恢复默认预设', '普通与深夜预设已恢复为程序内置版本', parent=self)

    def _create_right_panel(self) -> QWidget:
        """创建右侧面板"""
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        # Tab Widget
        tab_widget = QTabWidget()

        # 日志面板
        self.logger = LoggerWidget()
        if self.log_manager:
            self.log_manager.subscribe(self.logger)
        tab_widget.addTab(self.logger, "日志")

        # 仪表盘
        dashboard = self._create_dashboard()
        tab_widget.addTab(dashboard, "仪表盘")

        layout.addWidget(tab_widget)

        return panel

    def _create_dashboard(self) -> QWidget:
        """创建仪表盘（紧凑版）"""
        dashboard = QWidget()
        layout = QVBoxLayout(dashboard)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)

        # 统计卡片
        stats_layout = QHBoxLayout()

        # 存储value_label引用以便更新
        self.stat_value_labels = {}

        total_card, total_value = self._create_stat_card("总检测", "0", "#2196F3")
        self.stat_value_labels["total_detected"] = total_value
        stats_layout.addWidget(total_card)

        qualified_card, qualified_value = self._create_stat_card("合格", "0", "#4CAF50")
        self.stat_value_labels["qualified"] = qualified_value
        stats_layout.addWidget(qualified_card)

        unqualified_card, unqualified_value = self._create_stat_card("不合格", "0", "#FF9800")
        self.stat_value_labels["unqualified"] = unqualified_value
        stats_layout.addWidget(unqualified_card)

        skipped_card, skipped_value = self._create_stat_card("跳过", "0", "#9E9E9E")
        self.stat_value_labels["skipped"] = skipped_value
        stats_layout.addWidget(skipped_card)

        layout.addLayout(stats_layout)

        results_group = QGroupBox('最近筛选结果')
        results_layout = QVBoxLayout(results_group)
        self.result_filter = QComboBox()
        self.result_filter.addItems(['全部', '保留', '备选', '淘汰', '无法确认'])
        self.result_filter.currentTextChanged.connect(self._filter_results)
        results_layout.addWidget(self.result_filter)
        self.results_tree = QTreeWidget()
        self.result_items = {}
        self.results_tree.setHeaderLabels(['遗物', '颜色', '分数', '判定', '操作', '最佳预设'])
        self.results_tree.setMinimumHeight(230)
        results_layout.addWidget(self.results_tree)
        layout.addWidget(results_group)

        # 合格遗物列表（动态标题）
        cleaning_mode = "sell" if self.clean_mode_combo.currentIndex() == 0 else "favorite"
        if cleaning_mode == "sell":
            title_text = "已售出遗物词条"
        else:
            title_text = "已收藏遗物词条"

        self.relics_group = QGroupBox(title_text)
        relics_layout = QVBoxLayout(self.relics_group)
        relics_layout.setContentsMargins(8, 8, 8, 8)
        relics_layout.setSpacing(4)

        # 清空按钮
        clear_btn = PushButton("清空记录")
        clear_btn.clicked.connect(self._clear_relics_records)
        relics_layout.addWidget(clear_btn)

        # 滚动区域
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        scroll_content = QWidget()
        self.relics_layout = QVBoxLayout(scroll_content)
        self.relics_layout.setSpacing(6)
        self.relics_layout.addStretch()

        scroll.setWidget(scroll_content)
        relics_layout.addWidget(scroll)

        layout.addWidget(self.relics_group, 1)

        # 加载持久化的遗物到UI
        self._load_relics_ui()

        return dashboard

    def _create_stat_card(self, title: str, value: str, color: str) -> tuple:
        """创建统计卡片（紧凑版），返回(card, value_label)"""
        card = CardWidget()
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(12, 10, 12, 10)
        card_layout.setSpacing(4)

        title_label = QLabel(title)
        title_label.setStyleSheet(f"color: {color}; font-size: 11pt;")
        card_layout.addWidget(title_label)

        value_label = QLabel(value)
        value_label.setStyleSheet(f"color: {color}; font-size: 20pt; font-weight: bold;")
        card_layout.addWidget(value_label)

        return card, value_label

    def _refresh_presets(self):
        """刷新预设列表"""
        self._presets_loaded = True
        self.preset_container = None
        # 清空现有预设
        while self.preset_layout.count():
            item = self.preset_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        mode = "normal" if self.mode_combo.currentIndex() == 0 else "deepnight"
        score_enabled = normalize_scoring(self._load_settings().get("scoring"))["enabled"]

        # 通用预设
        general_preset = self.preset_manager.get_general_preset(mode)
        if general_preset:
            card = PresetCard(general_preset, is_general=True, score_enabled=score_enabled)
            card.edit_clicked.connect(self._edit_general_preset)
            self.preset_layout.addWidget(card)

        # 创建拖放容器用于专用预设
        dedicated_presets = self.preset_manager.get_dedicated_presets(mode)
        if dedicated_presets:
            drag_drop_container = DragDropContainer()
            self.preset_container = drag_drop_container
            drag_drop_container.reorder_requested.connect(self._handle_preset_reorder)

            for preset in dedicated_presets.values():
                drag_drop_container.add_card(
                    make_dedicated_card(self, mode, preset, score_enabled))

            self.preset_layout.addWidget(drag_drop_container)

        # 添加按钮（紧凑版）
        add_btn = PrimaryPushButton("+ 创建专用预设")
        add_btn.setFixedHeight(32)
        add_btn.clicked.connect(self._create_dedicated_preset)
        self.preset_layout.addWidget(add_btn)

        # 深夜模式：黑名单
        if mode == "deepnight":
            blacklist = self.preset_manager.get_blacklist_preset()
            if blacklist:
                card = PresetCard(blacklist, is_general=True, score_enabled=score_enabled)
                card.edit_clicked.connect(self._edit_blacklist_preset)
                self.preset_layout.addWidget(card)

        self.preset_layout.addStretch()

    def _handle_preset_reorder(self, source_id: str, target_id: str):
        """处理预设拖放排序"""
        mode = "normal" if self.mode_combo.currentIndex() == 0 else "deepnight"
        presets = self.preset_manager.get_dedicated_presets(mode)

        preset_ids = list(presets.keys())
        try:
            source_index = preset_ids.index(source_id)
            target_index = preset_ids.index(target_id)
        except ValueError:
            return

        # 交换位置
        preset_ids[source_index], preset_ids[target_index] = preset_ids[target_index], preset_ids[source_index]

        # 重建预设字典以保持新的顺序
        new_presets = {}
        for pid in preset_ids:
            new_presets[pid] = presets[pid]

        if mode == "normal":
            self.preset_manager.normal_dedicated = new_presets
        elif mode == "deepnight":
            self.preset_manager.deepnight_whitelist_dedicated = new_presets

        self.preset_manager.save_presets()
        self._refresh_presets()

    def refresh_presets_ui(self):
        """外部调用：刷新预设UI（当其他页面修改预设时）"""
        self._refresh_presets()

    def _on_mode_changed(self):
        """模式切换"""
        self.current_mode = "normal" if self.mode_combo.currentIndex() == 0 else "deepnight"
        self._refresh_presets()

    def _on_clean_mode_changed(self):
        """清理模式切换"""
        self._update_relics_display()

    def _edit_general_preset(self, preset_id: str):
        """编辑通用预设"""
        from ui.dialogs.preset_edit_dialog import PresetEditDialog

        mode = "normal" if self.mode_combo.currentIndex() == 0 else "deepnight"
        preset = self.preset_manager.get_general_preset(mode)
        vocab = self.preset_manager.load_vocabulary(
            PRESET_TYPE_NORMAL_WHITELIST if mode == "normal" else PRESET_TYPE_DEEPNIGHT_WHITELIST,
            for_editing=True  # 编辑模式：只加载常规词条
        )

        dialog = PresetEditDialog(vocab, preset, is_general=True, parent=self, mode=mode,
                                  exception_vocabulary=self.preset_manager.load_vocabulary("deepnight_blacklist")
                                  if mode == "deepnight" else [],
                                  default_negative_tiers=normalize_scoring(
                                      self._load_settings().get("scoring"))["negative_tiers"])
        dialog.graded_saved.connect(lambda pid, name, affixes, tiers, negative, excluded, official:
                                    self._save_general_preset(mode, affixes, tiers, negative, official))
        dialog.exec()

    def _save_general_preset(self, mode: str, affixes: list, tiers=None, negative=None, official=None):
        """保存通用预设"""
        self.preset_manager.update_general_preset(mode, affixes, tiers, negative, official)
        self._refresh_presets()
        self.presets_modified.emit()  # 发出预设修改信号
        InfoBar.success("保存成功", "通用预设已更新", parent=self)

    def _create_dedicated_preset(self):
        """创建专用预设"""
        from ui.dialogs.preset_edit_dialog import PresetEditDialog
        from ui.dialogs.preset_character_dialog import PresetCharacterDialog, next_preset_title

        mode = "normal" if self.mode_combo.currentIndex() == 0 else "deepnight"

        # 检查数量限制
        dedicated_presets = self.preset_manager.get_dedicated_presets(mode)
        if len(dedicated_presets) >= 500:
            MessageBox("错误", "专用预设数量已达上限（500个）", self).exec()
            return

        character_dialog = PresetCharacterDialog(self)
        if character_dialog.exec() != PresetCharacterDialog.Accepted:
            return
        character = character_dialog.selected_character()

        vocab = self.preset_manager.load_vocabulary(
            PRESET_TYPE_NORMAL_WHITELIST if mode == "normal" else PRESET_TYPE_DEEPNIGHT_WHITELIST,
            for_editing=True  # 编辑模式：只加载常规词条
        )

        general = self.preset_manager.get_general_preset(mode)
        dialog = PresetEditDialog(
                                  vocab, parent=self, mode=mode,
                                  new_character=character,
                                  suggested_name=next_preset_title(character, dedicated_presets),
                                  inherited_vocabulary=general.get("affixes", [])
                                  if general and general.get("is_active", True) else [],
                                  inherited_tiers=general.get("affix_tiers", {}) if general else {},
                                  inherited_negative_tiers=general.get("negative_tiers", {}) if general else {},
                                  default_negative_tiers=normalize_scoring(
                                      self._load_settings().get("scoring"))["negative_tiers"],
                                  exception_vocabulary=self.preset_manager.load_vocabulary("deepnight_blacklist")
                                  if mode == "deepnight" else [])
        dialog.graded_saved.connect(lambda pid, name, affixes, tiers, negative, excluded, official:
                                    self._save_new_preset(mode, name, affixes, tiers, negative, excluded, official))
        dialog.exec()

    def _save_new_preset(self, mode: str, name: str, affixes: list, tiers=None, negative=None, excluded=None, official=None):
        """保存新预设"""
        try:
            preset_id = self.preset_manager.create_dedicated_preset(mode, name, affixes,
                                                        blacklist_exceptions=[], required_affix_groups=[],
                                                        affix_tiers=tiers, negative_tiers=negative,
                                                        excluded_affixes=excluded,
                                                        official_scores=official if mode == 'normal' else None)
            add_one_preset_card(self, mode, preset_id,
                                normalize_scoring(self._load_settings().get('scoring'))['enabled'])
            self.preset_list_changed.emit(mode, preset_id, 'create')
            InfoBar.success("创建成功", f"预设 '{name}' 已创建", parent=self)
        except Exception as e:
            MessageBox("错误", f"创建预设失败: {e}", self).exec()

    def _edit_dedicated_preset(self, preset_id: str):
        """编辑专用预设"""
        from ui.dialogs.preset_edit_dialog import PresetEditDialog

        mode = "normal" if self.mode_combo.currentIndex() == 0 else "deepnight"
        presets = self.preset_manager.get_dedicated_presets(mode)
        preset = presets.get(preset_id)

        if not preset:
            return

        vocab = self.preset_manager.load_vocabulary(
            PRESET_TYPE_NORMAL_WHITELIST if mode == "normal" else PRESET_TYPE_DEEPNIGHT_WHITELIST,
            for_editing=True  # 编辑模式：只加载常规词条
        )

        general = self.preset_manager.get_general_preset(mode)
        dialog = PresetEditDialog(
                                  vocab, preset, parent=self, mode=mode,
                                  inherited_vocabulary=general.get("affixes", [])
                                  if general and general.get("is_active", True) else [],
                                  inherited_tiers=general.get("affix_tiers", {}) if general else {},
                                  inherited_negative_tiers=general.get("negative_tiers", {}) if general else {},
                                  default_negative_tiers=normalize_scoring(
                                      self._load_settings().get("scoring"))["negative_tiers"],
                                  exception_vocabulary=self.preset_manager.load_vocabulary("deepnight_blacklist")
                                  if mode == "deepnight" else [])
        dialog.graded_saved.connect(lambda pid, name, affixes, tiers, negative, excluded, official:
                                    self._update_preset(mode, preset_id, name, affixes, tiers, negative, excluded, official))
        dialog.exec()

    def _update_preset(self, mode: str, preset_id: str, name: str, affixes: list, tiers=None, negative=None, excluded=None, official=None):
        """更新预设"""
        try:
            self.preset_manager.update_dedicated_preset(
                mode, preset_id, name, affixes,
                blacklist_exceptions=[], required_affix_groups=[], affix_tiers=tiers,
                negative_tiers=negative, excluded_affixes=excluded,
                official_scores=official if mode == 'normal' else None)
        except ValueError as e:
            MessageBox("错误", f"保存预设失败: {e}", self).exec()
            return
        refresh_one_preset_card(self, mode, preset_id,
                                normalize_scoring(self._load_settings().get('scoring'))['enabled'])
        self.preset_updated.emit(mode, preset_id)
        InfoBar.success("保存成功", f"预设 '{name}' 已更新", parent=self)

    def _delete_preset(self, preset_id: str):
        """删除预设"""
        # 显示确认对话框
        msg_box = MessageBox("确认删除", "确定要删除这个预设吗？删除后无法恢复。", self)
        if msg_box.exec() != MessageBox.Accepted:
            return

        mode = "normal" if self.mode_combo.currentIndex() == 0 else "deepnight"
        self.preset_manager.delete_dedicated_preset(mode, preset_id)
        remove_one_preset_card(self, mode, preset_id)
        self.preset_list_changed.emit(mode, preset_id, 'delete')
        InfoBar.success("删除成功", "预设已删除", parent=self)

    def _toggle_preset(self, preset_id: str):
        """切换预设激活状态"""
        mode = "normal" if self.mode_combo.currentIndex() == 0 else "deepnight"
        self.preset_manager.toggle_preset_active(mode, preset_id)

    def _edit_blacklist_preset(self, preset_id: str):
        """编辑黑名单预设"""
        from ui.dialogs.preset_edit_dialog import PresetEditDialog

        preset = self.preset_manager.get_blacklist_preset()
        vocab = self.preset_manager.load_vocabulary("deepnight_blacklist", for_editing=True)

        dialog = PresetEditDialog(vocab, preset, is_general=True, parent=self)
        dialog.preset_saved.connect(lambda pid, name, affixes: self._save_blacklist(affixes))
        dialog.exec()

    def _save_blacklist(self, affixes: list):
        """保存黑名单"""
        self.preset_manager.update_blacklist_preset(affixes)
        self._refresh_presets()
        InfoBar.success("保存成功", "黑名单已更新", parent=self)

    def _on_auto_detect_changed(self):
        """自动检测复选框状态改变"""
        # 使用 isChecked() 更可靠
        if self.auto_detect_checkbox.isChecked():
            # 勾选自动检测，隐藏输入框
            self.max_input.setVisible(False)
        else:
            # 取消勾选，显示输入框
            self.max_input.setVisible(True)

    def _start_scanning(self):
        self._start_cleaning(scan_only=True)

    def _start_cleaning(self, scan_only=False):
        """开始清理"""
        mode = "normal" if self.mode_combo.currentIndex() == 0 else "deepnight"
        cleaning_mode = ("scan" if scan_only else
                         "sell" if self.clean_mode_combo.currentIndex() == 0 else "favorite")
        self.active_cleaning_mode = cleaning_mode

        # 获取数量
        auto_detect = self.auto_detect_checkbox.isChecked()
        if auto_detect:
            # 自动检测模式，设置为 0 表示自动检测
            max_relics = 0
        else:
            # 手动输入模式
            max_relics_text = self.max_input.text().strip()
            max_relics = int(max_relics_text) if max_relics_text else 100

        # 重新加载设置（确保使用最新的设置）
        self.settings = self._load_settings()

        # 更新 repo_cleaner 的设置
        if self.repo_cleaner:
            self.repo_cleaner.settings = self.settings

        # 更新亮度阈值
        if self.relic_detector:
            self.relic_detector.brightness_threshold = self.settings.get("brightness_threshold", 45)

        # 从设置获取参数
        allow_favorited = self.settings.get("allow_operate_favorited", False)
        require_double = self.settings.get("require_double_valid", True)

        # 清空日志和遗物列表
        self.logger.clear()
        if self.log_manager:
            self.log_manager.clear_all()  # 清空所有订阅者的日志
            self.log_manager.log("开始仓库检索..." if scan_only else "开始清理...", "INFO")
        else:
            self.logger.log("开始仓库检索..." if scan_only else "开始清理...", "INFO")
        self._clear_relics_records()
        self.results_tree.clear()
        self.result_items.clear()

        # 重置手动停止标志
        self.is_manual_stop = False

        # 禁用按钮
        self.start_btn.setEnabled(False)
        self.scan_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)

        # 创建并启动线程
        self.cleaning_thread = CleaningThread(
            self.repo_cleaner, mode, cleaning_mode, max_relics, allow_favorited, require_double
        )
        self.cleaning_thread.log_signal.connect(self._on_log)
        self.cleaning_thread.finished_signal.connect(self._on_cleaning_finished)
        self.cleaning_thread.qualified_relic_signal.connect(self._add_qualified_relic)
        self.cleaning_thread.result_signal.connect(self._on_result)
        self.cleaning_thread.start()

    def _on_log(self, message: str, level: str):
        """处理日志信号"""
        if self.log_manager:
            self.log_manager.log(message, level)
        else:
            self.logger.log(message, level)

    def _on_result(self, result: dict):
        old = self.result_items.pop(result['index'], None)
        if old is not None:
            position = self.results_tree.indexOfTopLevelItem(old)
            if position >= 0:
                self.results_tree.takeTopLevelItem(position)
        score = (str(result['score']) if result['score'] is not None
                 else ('未启用评分' if not result['scoring_enabled'] else '无候选分数'))
        item = QTreeWidgetItem([f"#{result['index']}", result['color'], score,
                                result['decision'], result['action'], result['preset_name'] or '无'])
        item.setData(0, Qt.UserRole, result['decision'])
        for affix in result['affix_scores']:
            value = affix['points']
            item.addChild(QTreeWidgetItem([affix['name'], '',
                f'{value:+d}' if value is not None else '未启用评分', '', '', '']))
        if result['reason']:
            item.addChild(QTreeWidgetItem(['原因：' + result['reason']]))
        self.results_tree.insertTopLevelItem(0, item)
        self.result_items[result['index']] = item
        if self.results_tree.topLevelItemCount() > 200:
            removed = self.results_tree.takeTopLevelItem(200)
            for key, value in list(self.result_items.items()):
                if value is removed:
                    del self.result_items[key]
        self._filter_results(self.result_filter.currentText())
        self._update_dashboard(self.repo_cleaner.stats)

    def _filter_results(self, choice):
        for index in range(self.results_tree.topLevelItemCount()):
            item = self.results_tree.topLevelItem(index)
            item.setHidden(choice != '全部' and item.data(0, Qt.UserRole) != choice)

    def _stop_cleaning(self):
        """停止清理"""
        if self.cleaning_thread:
            self.is_manual_stop = True
            self.repo_cleaner.stop_cleaning()
            if self.log_manager:
                self.log_manager.log("正在停止清理...", "WARNING")
            else:
                self.logger.log("正在停止清理...", "WARNING")

    def _on_cleaning_finished(self):
        """清理完成"""
        self.start_btn.setEnabled(True)
        self.scan_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        reason = self.repo_cleaner.stop_reason
        scanning = getattr(self, 'active_cleaning_mode', None) == 'scan'
        messages = {
            "manual": ("检索已手动停止" if scanning else "清理已手动停止", "WARNING"),
            "completed": ("检索已完成" if scanning else "清理已完成", "SUCCESS"),
            "error": ("检索异常停止，请检查日志" if scanning else "清理异常停止，请检查日志", "ERROR"),
        }
        self._on_log(*messages.get(reason, messages["error"]))
        self.is_manual_stop = False

        # 更新统计
        stats = self.repo_cleaner.stats
        self._update_dashboard(stats)

        # 保存售出/收藏遗物到持久化存储
        cleaning_mode = getattr(self, 'active_cleaning_mode', 'sell')
        if cleaning_mode == "sell":
            self._save_sold_relics()
        elif cleaning_mode == "favorite":
            self._save_favorited_relics()

    def _update_dashboard(self, stats: dict):
        """更新仪表盘"""
        # 更新统计卡片的值
        for key, value_label in self.stat_value_labels.items():
            if key in stats:
                value_label.setText(str(stats[key]))

    def _clear_relics_records(self):
        """清空遗物列表"""
        while self.relics_layout.count() > 1:  # 保留最后的stretch
            item = self.relics_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # 同时清空内存中的遗物列表
        self.sold_relics.clear()
        self.favorited_relics.clear()

    def _add_qualified_relic(self, relic_info: dict):
        """添加合格遗物到仪表盘"""
        # 创建遗物卡片
        card = CardWidget()
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(8, 6, 8, 6)
        card_layout.setSpacing(4)

        # 标题（只显示编号）
        title = QLabel(f"#{relic_info['index']}")
        title.setStyleSheet("font-size: 10pt; font-weight: bold; color: #4CAF50;")
        card_layout.addWidget(title)

        # 词条列表
        for affix in relic_info['affixes']:
            affix_type = "正面" if affix["is_positive"] else "负面"
            color = "#4CAF50" if affix["is_positive"] else "#FF5722"
            affix_label = QLabel(f"[{affix_type}] {affix['cleaned_text']}")
            affix_label.setFont(QFont("Segoe UI", 9))
            affix_label.setStyleSheet(f"color: {color};")
            affix_label.setWordWrap(True)
            card_layout.addWidget(affix_label)

        # 插入到stretch之前
        self.relics_layout.insertWidget(self.relics_layout.count() - 1, card)

        # 保存到对应的持久化列表
        cleaning_mode = "sell" if self.clean_mode_combo.currentIndex() == 0 else "favorite"
        relic_record = {
            "timestamp": datetime.now().isoformat(),
            "index": relic_info["index"],
            "affixes": relic_info["affixes"]
        }

        if cleaning_mode == "sell":
            self.sold_relics.append(relic_record)
        else:
            self.favorited_relics.append(relic_record)

    def _load_settings(self) -> dict:
        """加载设置"""
        settings_file = get_user_data_path("data/settings.json")
        if not os.path.exists(settings_file):
            return {

                "allow_operate_favorited": False,
                "require_double_valid": True
            }

        try:
            with open(settings_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return {
                "allow_operate_favorited": False,
                "require_double_valid": True
            }

    def _load_sold_relics(self) -> list:
        """从文件加载售出遗物"""
        if os.path.exists(SOLD_RELICS_FILE):
            try:
                with open(SOLD_RELICS_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                print(f"加载售出遗物失败: {e}")
                return []
        return []

    def _load_favorited_relics(self) -> list:
        """从文件加载收藏遗物"""
        if os.path.exists(FAVORITED_RELICS_FILE):
            try:
                with open(FAVORITED_RELICS_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                print(f"加载收藏遗物失败: {e}")
                return []
        return []

    def _save_sold_relics(self):
        """保存售出遗物到文件"""
        try:
            os.makedirs(os.path.dirname(SOLD_RELICS_FILE), exist_ok=True)
            with open(SOLD_RELICS_FILE, "w", encoding="utf-8") as f:
                json.dump(self.sold_relics, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"保存售出遗物失败: {e}")

    def _save_favorited_relics(self):
        """保存收藏遗物到文件"""
        try:
            os.makedirs(os.path.dirname(FAVORITED_RELICS_FILE), exist_ok=True)
            with open(FAVORITED_RELICS_FILE, "w", encoding="utf-8") as f:
                json.dump(self.favorited_relics, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"保存收藏遗物失败: {e}")

    def _load_relics_ui(self):
        """加载遗物到UI"""
        cleaning_mode = "sell" if self.clean_mode_combo.currentIndex() == 0 else "favorite"
        relics = self.sold_relics if cleaning_mode == "sell" else self.favorited_relics

        for relic_info in relics:
            self._add_relic_ui(relic_info)

    def _add_relic_ui(self, relic_info: dict):
        """添加遗物到UI"""
        card = CardWidget()
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(8, 6, 8, 6)
        card_layout.setSpacing(4)

        # 标题（只显示编号）
        title = QLabel(f"#{relic_info['index']}")
        title.setStyleSheet("font-size: 10pt; font-weight: bold; color: #4CAF50;")
        card_layout.addWidget(title)

        # 时间戳
        timestamp = relic_info.get("timestamp", "")
        if timestamp:
            time_label = QLabel(timestamp)
            time_label.setFont(QFont("Segoe UI", 8))
            time_label.setStyleSheet("color: gray;")
            card_layout.addWidget(time_label)

        # 词条列表
        for affix in relic_info.get("affixes", []):
            affix_type = "正面" if affix["is_positive"] else "负面"
            color = "#4CAF50" if affix["is_positive"] else "#FF5722"
            affix_label = QLabel(f"[{affix_type}] {affix['cleaned_text']}")
            affix_label.setFont(QFont("Segoe UI", 9))
            affix_label.setStyleSheet(f"color: {color};")
            affix_label.setWordWrap(True)
            card_layout.addWidget(affix_label)

        # 插入到stretch之前
        self.relics_layout.insertWidget(self.relics_layout.count() - 1, card)

    def _update_relics_display(self):
        """更新遗物显示（根据清理模式切换）"""
        # 清空现有遗物
        self._clear_relics_records()

        # 更新标题
        cleaning_mode = "sell" if self.clean_mode_combo.currentIndex() == 0 else "favorite"
        if cleaning_mode == "sell":
            self.relics_group.setTitle("已售出遗物词条")
        else:
            self.relics_group.setTitle("已收藏遗物词条")

        # 加载对应模式的遗物
        self._load_relics_ui()

    def set_ocr_engine(self, engine):
        """设置 OCR 引擎（异步加载完成后调用）"""
        # 在这里才真正导入重型模块，此时界面已经显示出来了
        from core.relic_detector import RelicDetector
        from core.repo_cleaner import RepoCleaner

        self.ocr_engine = engine

        # 初始化 relic_detector 和 repo_cleaner
        if self.relic_detector is None:
            self.relic_detector = RelicDetector()

        if self.repo_cleaner is None:
            self.repo_cleaner = RepoCleaner(self.preset_manager, engine, self.relic_detector, self.settings)
        else:
            # 如果已经初始化，只更新引擎
            self.repo_cleaner.ocr_engine = engine

        # 启用开始按钮
        self.start_btn.setEnabled(True)
        self.scan_btn.setEnabled(True)
        self.start_btn.setText("开始清理(F10)")
        # 输出成功日志
        if self.log_manager:
            self.log_manager.log("OCR 引擎异步加载完成", "SUCCESS")
        else:
            self.logger.log("OCR 引擎异步加载完成", "SUCCESS")

    def _setup_shortcuts(self):
        """设置全局快捷键"""
        # F9 只扫描录库；F10 按所选清理模式操作。
        keyboard.add_hotkey('F9', self._on_scan_shortcut, suppress=False)
        keyboard.add_hotkey('F10', self._on_start_shortcut, suppress=False)
        # F11 停止清理
        keyboard.add_hotkey('F11', self._on_stop_shortcut, suppress=False)

    def _on_start_shortcut(self):
        """F10 快捷键触发开始"""
        if self.isVisible() and self.start_btn.isEnabled():
            self.clean_requested.emit()

    def _on_scan_shortcut(self):
        if self.isVisible() and self.scan_btn.isEnabled():
            self.scan_requested.emit()

    def _on_stop_shortcut(self):
        """F11 快捷键触发停止"""
        if self.isVisible() and self.stop_btn.isEnabled():
            self.stop_requested.emit()
