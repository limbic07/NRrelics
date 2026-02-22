"""
仓库清理页面 - 完整实现
包含预设管理、清理控制、日志显示和统计仪表盘
"""

from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                               QPushButton, QComboBox, QTabWidget,
                               QScrollArea, QFrame, QSplitter, QGroupBox, QCheckBox, QLineEdit)
from PySide6.QtCore import Qt, Signal, QThread, QMimeData, QPoint
from PySide6.QtGui import QFont, QIntValidator, QDrag, QPixmap
import keyboard
from qfluentwidgets import (CardWidget, PrimaryPushButton, PushButton,
                           ComboBox, MessageBox, InfoBar, InfoBarPosition)

from core.preset_manager import PresetManager, PRESET_TYPE_NORMAL_WHITELIST, PRESET_TYPE_DEEPNIGHT_WHITELIST
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

    def add_card(self, card):
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

        self.layout.addWidget(card)


class CleaningThread(QThread):
    """清理线程"""
    log_signal = Signal(str, str)  # (message, level)
    finished_signal = Signal()
    qualified_relic_signal = Signal(dict)  # 合格遗物信息

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
                log_callback=self.log_signal.emit
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

    def __init__(self, preset_data: dict, is_general: bool = False, parent=None):
        super().__init__(parent)
        self.preset_data = preset_data
        self.is_general = is_general
        self.is_expanded = False

        self._init_ui()

    def _init_ui(self):
        """初始化UI"""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(12, 10, 12, 10)
        main_layout.setSpacing(8)

        # 顶部：预设信息和按钮
        top_layout = QHBoxLayout()
        top_layout.setSpacing(8)

        # 展开/折叠按钮
        self.expand_btn = QPushButton("▶" if not self.is_expanded else "▼")
        self.expand_btn.setFixedSize(20, 20)
        self.expand_btn.setStyleSheet("""
            QPushButton {
                border: none;
                background: transparent;
                font-size: 10pt;
            }
            QPushButton:hover {
                background: #f0f0f0;
                border-radius: 3px;
            }
        """)
        self.expand_btn.clicked.connect(self._toggle_expand)
        top_layout.addWidget(self.expand_btn)

        # 预设信息
        info_layout = QVBoxLayout()
        info_layout.setSpacing(2)

        # 名称
        name_label = QLabel(self.preset_data["name"])
        name_font = QFont("", 10)  # 指定字号避免-1错误
        name_font.setBold(True)
        name_label.setFont(name_font)
        info_layout.addWidget(name_label)

        # 词条数量
        count_label = QLabel(f"{len(self.preset_data['affixes'])} 条词条")
        count_label.setStyleSheet("color: #888; font-size: 10pt;")
        info_layout.addWidget(count_label)

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
        affixes_layout = QVBoxLayout(self.affixes_widget)
        affixes_layout.setContentsMargins(24, 4, 4, 4)
        affixes_layout.setSpacing(2)

        # 添加词条标签
        for affix in self.preset_data["affixes"][:20]:  # 最多显示20条
            affix_label = QLabel(f"• {affix}")
            affix_label.setFont(QFont("Segoe UI", 9))
            affix_label.setStyleSheet("color: #555;")
            affix_label.setWordWrap(True)
            affixes_layout.addWidget(affix_label)

        if len(self.preset_data["affixes"]) > 20:
            more_label = QLabel(f"... 还有 {len(self.preset_data['affixes']) - 20} 条")
            more_label.setFont(QFont("Segoe UI", 9))
            more_label.setStyleSheet("color: #999; font-style: italic;")
            affixes_layout.addWidget(more_label)

        self.affixes_widget.setVisible(False)
        main_layout.addWidget(self.affixes_widget)

    def _toggle_expand(self):
        """切换展开/折叠"""
        self.is_expanded = not self.is_expanded
        self.expand_btn.setText("▼" if self.is_expanded else "▶")
        self.affixes_widget.setVisible(self.is_expanded)

class RepoPage(QWidget):
    """仓库清理页面"""

    # 预设修改信号
    presets_modified = Signal()

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

        self._init_ui()

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
        layout.addWidget(title)

        # 滚动区域
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        scroll_content = QWidget()
        self.preset_layout = QVBoxLayout(scroll_content)
        self.preset_layout.setSpacing(8)

        scroll.setWidget(scroll_content)
        layout.addWidget(scroll)

        # 刷新预设列表
        self._refresh_presets()

        return panel

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
        # 清空现有预设
        while self.preset_layout.count():
            item = self.preset_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        mode = "normal" if self.mode_combo.currentIndex() == 0 else "deepnight"

        # 通用预设
        general_preset = self.preset_manager.get_general_preset(mode)
        if general_preset:
            card = PresetCard(general_preset, is_general=True)
            card.edit_clicked.connect(self._edit_general_preset)
            self.preset_layout.addWidget(card)

        # 创建拖放容器用于专用预设
        dedicated_presets = self.preset_manager.get_dedicated_presets(mode)
        if dedicated_presets:
            drag_drop_container = DragDropContainer()
            drag_drop_container.reorder_requested.connect(self._handle_preset_reorder)

            for preset in dedicated_presets.values():
                card = PresetCard(preset, is_general=False)
                card.edit_clicked.connect(self._edit_dedicated_preset)
                card.delete_clicked.connect(self._delete_preset)
                card.toggle_clicked.connect(self._toggle_preset)
                drag_drop_container.add_card(card)

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
                card = PresetCard(blacklist, is_general=True)
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

        dialog = PresetEditDialog(vocab, preset, is_general=True, parent=self)
        dialog.preset_saved.connect(lambda pid, name, affixes: self._save_general_preset(mode, affixes))
        dialog.exec()

    def _save_general_preset(self, mode: str, affixes: list):
        """保存通用预设"""
        self.preset_manager.update_general_preset(mode, affixes)
        self._refresh_presets()
        self.presets_modified.emit()  # 发出预设修改信号
        InfoBar.success("保存成功", "通用预设已更新", parent=self)

    def _create_dedicated_preset(self):
        """创建专用预设"""
        from ui.dialogs.preset_edit_dialog import PresetEditDialog

        mode = "normal" if self.mode_combo.currentIndex() == 0 else "deepnight"

        # 检查数量限制
        dedicated_presets = self.preset_manager.get_dedicated_presets(mode)
        if len(dedicated_presets) >= 20:
            MessageBox("错误", "专用预设数量已达上限（20个）", self).exec()
            return

        vocab = self.preset_manager.load_vocabulary(
            PRESET_TYPE_NORMAL_WHITELIST if mode == "normal" else PRESET_TYPE_DEEPNIGHT_WHITELIST,
            for_editing=True  # 编辑模式：只加载常规词条
        )

        dialog = PresetEditDialog(vocab, parent=self)
        dialog.preset_saved.connect(lambda pid, name, affixes: self._save_new_preset(mode, name, affixes))
        dialog.exec()

    def _save_new_preset(self, mode: str, name: str, affixes: list):
        """保存新预设"""
        try:
            self.preset_manager.create_dedicated_preset(mode, name, affixes)
            self._refresh_presets()
            self.presets_modified.emit()  # 发出预设修改信号
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

        dialog = PresetEditDialog(vocab, preset, parent=self)
        dialog.preset_saved.connect(lambda pid, name, affixes: self._update_preset(mode, preset_id, name, affixes))
        dialog.exec()

    def _update_preset(self, mode: str, preset_id: str, name: str, affixes: list):
        """更新预设"""
        self.preset_manager.update_dedicated_preset(mode, preset_id, name, affixes)
        self._refresh_presets()
        self.presets_modified.emit()  # 发出预设修改信号
        InfoBar.success("保存成功", f"预设 '{name}' 已更新", parent=self)

    def _delete_preset(self, preset_id: str):
        """删除预设"""
        # 显示确认对话框
        msg_box = MessageBox("确认删除", "确定要删除这个预设吗？删除后无法恢复。", self)
        if msg_box.exec() != MessageBox.Accepted:
            return

        mode = "normal" if self.mode_combo.currentIndex() == 0 else "deepnight"
        self.preset_manager.delete_dedicated_preset(mode, preset_id)
        self._refresh_presets()
        self.presets_modified.emit()  # 发出预设修改信号
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

    def _start_cleaning(self):
        """开始清理"""
        mode = "normal" if self.mode_combo.currentIndex() == 0 else "deepnight"
        cleaning_mode = "sell" if self.clean_mode_combo.currentIndex() == 0 else "favorite"

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
            self.log_manager.log("开始清理...", "INFO")
        else:
            self.logger.log("开始清理...", "INFO")
        self._clear_relics_records()

        # 重置手动停止标志
        self.is_manual_stop = False

        # 禁用按钮
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)

        # 创建并启动线程
        self.cleaning_thread = CleaningThread(
            self.repo_cleaner, mode, cleaning_mode, max_relics, allow_favorited, require_double
        )
        self.cleaning_thread.log_signal.connect(self._on_log)
        self.cleaning_thread.finished_signal.connect(self._on_cleaning_finished)
        self.cleaning_thread.qualified_relic_signal.connect(self._add_qualified_relic)
        self.cleaning_thread.start()

    def _on_log(self, message: str, level: str):
        """处理日志信号"""
        if self.log_manager:
            self.log_manager.log(message, level)
        else:
            self.logger.log(message, level)

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
        self.stop_btn.setEnabled(False)

        if self.is_manual_stop:
            if self.log_manager:
                self.log_manager.log("清理已停止", "WARNING")
            else:
                self.logger.log("清理已停止", "WARNING")
            self.is_manual_stop = False
        else:
            if self.log_manager:
                self.log_manager.log("清理已完成", "SUCCESS")
            else:
                self.logger.log("清理已完成", "SUCCESS")

        # 更新统计
        stats = self.repo_cleaner.stats
        self._update_dashboard(stats)

        # 保存售出/收藏遗物到持久化存储
        cleaning_mode = "sell" if self.clean_mode_combo.currentIndex() == 0 else "favorite"
        if cleaning_mode == "sell":
            self._save_sold_relics()
        else:
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
        self.start_btn.setText("开始清理(F10)")
        # 输出成功日志
        if self.log_manager:
            self.log_manager.log("OCR 引擎异步加载完成", "SUCCESS")
        else:
            self.logger.log("OCR 引擎异步加载完成", "SUCCESS")

    def _setup_shortcuts(self):
        """设置全局快捷键"""
        # F10 开始清理
        keyboard.add_hotkey('F10', self._on_start_shortcut, suppress=False)
        # F11 停止清理
        keyboard.add_hotkey('F11', self._on_stop_shortcut, suppress=False)

    def _on_start_shortcut(self):
        """F10 快捷键触发开始"""
        if self.isVisible() and self.start_btn.isEnabled():
            # 使用 QMetaObject.invokeMethod 确保在主线程执行
            from PySide6.QtCore import QMetaObject, Qt as QtCore_Qt
            QMetaObject.invokeMethod(self, "_start_cleaning", QtCore_Qt.QueuedConnection)

    def _on_stop_shortcut(self):
        """F11 快捷键触发停止"""
        if self.isVisible() and self.stop_btn.isEnabled():
            from PySide6.QtCore import QMetaObject, Qt as QtCore_Qt
            QMetaObject.invokeMethod(self, "_stop_cleaning", QtCore_Qt.QueuedConnection)
