"""
仓库清理页面 - 完整实现
包含预设管理、清理控制、日志显示和统计仪表盘
"""

from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                               QPushButton, QComboBox, QSpinBox, QTabWidget,
                               QScrollArea, QFrame, QSplitter, QGroupBox, QCheckBox)
from PySide6.QtCore import Qt, Signal, QThread
from PySide6.QtGui import QFont
from qfluentwidgets import (CardWidget, PrimaryPushButton, PushButton,
                           ComboBox, SpinBox, MessageBox, InfoBar, InfoBarPosition)

from core.preset_manager import PresetManager, PRESET_TYPE_NORMAL_WHITELIST, PRESET_TYPE_DEEPNIGHT_WHITELIST
from core.ocr_engine import OCREngine
from core.relic_detector import RelicDetector
from core.repo_cleaner import RepoCleaner
from ui.dialogs.preset_edit_dialog import PresetEditDialog
from ui.components.logger_widget import LoggerWidget
import json
import os


class CleaningThread(QThread):
    """清理线程"""
    log_signal = Signal(str, str)  # (message, level)
    finished_signal = Signal()

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
        except Exception as e:
            self.log_signal.emit(f"清理过程出错: {e}", "ERROR")
        finally:
            self.finished_signal.emit()


class PresetCard(CardWidget):
    """预设卡片"""
    edit_clicked = Signal(str)  # preset_id
    delete_clicked = Signal(str)  # preset_id
    toggle_clicked = Signal(str)  # preset_id

    def __init__(self, preset_data: dict, is_general: bool = False, parent=None):
        super().__init__(parent)
        self.preset_data = preset_data
        self.is_general = is_general

        self._init_ui()

    def _init_ui(self):
        """初始化UI"""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(12)

        # 预设信息
        info_layout = QVBoxLayout()
        info_layout.setSpacing(4)

        # 名称
        name_label = QLabel(self.preset_data["name"])
        name_font = QFont()
        name_font.setPointSize(11)
        name_font.setBold(True)
        name_label.setFont(name_font)
        info_layout.addWidget(name_label)

        # 词条数量
        count_label = QLabel(f"{len(self.preset_data['affixes'])} 条词条")
        count_label.setStyleSheet("color: #666; font-size: 11px;")
        info_layout.addWidget(count_label)

        layout.addLayout(info_layout)
        layout.addStretch()

        # 按钮
        if not self.is_general:
            # 启用/禁用复选框
            self.active_checkbox = QCheckBox("启用")
            self.active_checkbox.setChecked(self.preset_data.get("is_active", True))
            self.active_checkbox.stateChanged.connect(
                lambda: self.toggle_clicked.emit(self.preset_data["id"])
            )
            layout.addWidget(self.active_checkbox)

        # 编辑按钮
        edit_btn = PushButton("编辑")
        edit_btn.setFixedWidth(60)
        edit_btn.clicked.connect(lambda: self.edit_clicked.emit(self.preset_data["id"]))
        layout.addWidget(edit_btn)

        # 删除按钮（仅专用预设）
        if not self.is_general:
            delete_btn = PushButton("删除")
            delete_btn.setFixedWidth(60)
            delete_btn.clicked.connect(lambda: self.delete_clicked.emit(self.preset_data["id"]))
            layout.addWidget(delete_btn)


class RepoPage(QWidget):
    """仓库清理页面"""

    def __init__(self):
        super().__init__()
        self.setObjectName("RepoPage")

        # 初始化组件
        self.preset_manager = PresetManager()
        self.ocr_engine = OCREngine()
        self.relic_detector = RelicDetector()
        self.repo_cleaner = RepoCleaner(self.preset_manager, self.ocr_engine, self.relic_detector)

        # 清理线程
        self.cleaning_thread = None

        # 当前模式
        self.current_mode = "normal"

        # 加载设置
        self.settings = self._load_settings()

        self._init_ui()

    def _init_ui(self):
        """初始化UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 32, 32, 32)
        layout.setSpacing(16)

        # 标题
        title = QLabel("仓库清理")
        title.setStyleSheet("font-size: 24px; font-weight: bold;")
        layout.addWidget(title)

        # 顶部工具栏
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

        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)

        layout.addWidget(splitter)

    def _create_toolbar(self) -> CardWidget:
        """创建顶部工具栏"""
        card = CardWidget()
        layout = QHBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(16)

        # 模式选择
        mode_label = QLabel("模式:")
        layout.addWidget(mode_label)

        self.mode_combo = ComboBox()
        self.mode_combo.addItems(["普通", "深夜"])
        self.mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        layout.addWidget(self.mode_combo)

        layout.addSpacing(20)

        # 清理模式
        clean_mode_label = QLabel("清理模式:")
        layout.addWidget(clean_mode_label)

        self.clean_mode_combo = ComboBox()
        self.clean_mode_combo.addItems(["售出", "收藏"])
        layout.addWidget(self.clean_mode_combo)

        layout.addSpacing(20)

        # 最大检测数量
        max_label = QLabel("最大数量:")
        layout.addWidget(max_label)

        self.max_spin = SpinBox()
        self.max_spin.setRange(0, 9999)
        self.max_spin.setValue(0)
        self.max_spin.setSpecialValueText("无限制")
        layout.addWidget(self.max_spin)

        layout.addStretch()

        return card

    def _create_preset_panel(self) -> QWidget:
        """创建预设面板"""
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        # 标题
        title = QLabel("预设管理")
        title.setStyleSheet("font-size: 16px; font-weight: bold;")
        layout.addWidget(title)

        # 滚动区域
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        scroll_content = QWidget()
        self.preset_layout = QVBoxLayout(scroll_content)
        self.preset_layout.setSpacing(12)

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
        tab_widget.addTab(self.logger, "日志")

        # 仪表盘
        dashboard = self._create_dashboard()
        tab_widget.addTab(dashboard, "仪表盘")

        layout.addWidget(tab_widget)

        # 控制按钮
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        self.start_btn = PrimaryPushButton("开始清理")
        self.start_btn.setFixedWidth(120)
        self.start_btn.clicked.connect(self._start_cleaning)
        button_layout.addWidget(self.start_btn)

        self.stop_btn = PushButton("停止")
        self.stop_btn.setFixedWidth(120)
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self._stop_cleaning)
        button_layout.addWidget(self.stop_btn)

        layout.addLayout(button_layout)

        return panel

    def _create_dashboard(self) -> QWidget:
        """创建仪表盘"""
        dashboard = QWidget()
        layout = QVBoxLayout(dashboard)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

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

        layout.addStretch()

        return dashboard

    def _create_stat_card(self, title: str, value: str, color: str) -> tuple:
        """创建统计卡片，返回(card, value_label)"""
        card = CardWidget()
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(20, 16, 20, 16)
        card_layout.setSpacing(8)

        title_label = QLabel(title)
        title_label.setStyleSheet(f"color: {color}; font-size: 12px;")
        card_layout.addWidget(title_label)

        value_label = QLabel(value)
        value_label.setStyleSheet(f"color: {color}; font-size: 24px; font-weight: bold;")
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

        # 专用预设
        dedicated_presets = self.preset_manager.get_dedicated_presets(mode)
        for preset in dedicated_presets.values():
            card = PresetCard(preset, is_general=False)
            card.edit_clicked.connect(self._edit_dedicated_preset)
            card.delete_clicked.connect(self._delete_preset)
            card.toggle_clicked.connect(self._toggle_preset)
            self.preset_layout.addWidget(card)

        # 添加按钮
        add_btn = PrimaryPushButton("+ 创建专用预设")
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

    def _on_mode_changed(self):
        """模式切换"""
        self.current_mode = "normal" if self.mode_combo.currentIndex() == 0 else "deepnight"
        self._refresh_presets()

    def _edit_general_preset(self, preset_id: str):
        """编辑通用预设"""
        mode = "normal" if self.mode_combo.currentIndex() == 0 else "deepnight"
        preset = self.preset_manager.get_general_preset(mode)
        vocab = self.preset_manager.load_vocabulary(
            PRESET_TYPE_NORMAL_WHITELIST if mode == "normal" else PRESET_TYPE_DEEPNIGHT_WHITELIST
        )

        dialog = PresetEditDialog(vocab, preset, is_general=True, parent=self)
        dialog.preset_saved.connect(lambda pid, name, affixes: self._save_general_preset(mode, affixes))
        dialog.exec()

    def _save_general_preset(self, mode: str, affixes: list):
        """保存通用预设"""
        self.preset_manager.update_general_preset(mode, affixes)
        self._refresh_presets()
        InfoBar.success("保存成功", "通用预设已更新", parent=self)

    def _create_dedicated_preset(self):
        """创建专用预设"""
        mode = "normal" if self.mode_combo.currentIndex() == 0 else "deepnight"

        # 检查数量限制
        dedicated_presets = self.preset_manager.get_dedicated_presets(mode)
        if len(dedicated_presets) >= 20:
            MessageBox("错误", "专用预设数量已达上限（20个）", self).exec()
            return

        vocab = self.preset_manager.load_vocabulary(
            PRESET_TYPE_NORMAL_WHITELIST if mode == "normal" else PRESET_TYPE_DEEPNIGHT_WHITELIST
        )

        dialog = PresetEditDialog(vocab, parent=self)
        dialog.preset_saved.connect(lambda pid, name, affixes: self._save_new_preset(mode, name, affixes))
        dialog.exec()

    def _save_new_preset(self, mode: str, name: str, affixes: list):
        """保存新预设"""
        try:
            self.preset_manager.create_dedicated_preset(mode, name, affixes)
            self._refresh_presets()
            InfoBar.success("创建成功", f"预设 '{name}' 已创建", parent=self)
        except Exception as e:
            MessageBox("错误", f"创建预设失败: {e}", self).exec()

    def _edit_dedicated_preset(self, preset_id: str):
        """编辑专用预设"""
        mode = "normal" if self.mode_combo.currentIndex() == 0 else "deepnight"
        presets = self.preset_manager.get_dedicated_presets(mode)
        preset = presets.get(preset_id)

        if not preset:
            return

        vocab = self.preset_manager.load_vocabulary(
            PRESET_TYPE_NORMAL_WHITELIST if mode == "normal" else PRESET_TYPE_DEEPNIGHT_WHITELIST
        )

        dialog = PresetEditDialog(vocab, preset, parent=self)
        dialog.preset_saved.connect(lambda pid, name, affixes: self._update_preset(mode, preset_id, name, affixes))
        dialog.exec()

    def _update_preset(self, mode: str, preset_id: str, name: str, affixes: list):
        """更新预设"""
        self.preset_manager.update_dedicated_preset(mode, preset_id, name, affixes)
        self._refresh_presets()
        InfoBar.success("保存成功", f"预设 '{name}' 已更新", parent=self)

    def _delete_preset(self, preset_id: str):
        """删除预设"""
        mode = "normal" if self.mode_combo.currentIndex() == 0 else "deepnight"
        self.preset_manager.delete_dedicated_preset(mode, preset_id)
        self._refresh_presets()
        InfoBar.success("删除成功", "预设已删除", parent=self)

    def _toggle_preset(self, preset_id: str):
        """切换预设激活状态"""
        mode = "normal" if self.mode_combo.currentIndex() == 0 else "deepnight"
        self.preset_manager.toggle_preset_active(mode, preset_id)

    def _edit_blacklist_preset(self, preset_id: str):
        """编辑黑名单预设"""
        preset = self.preset_manager.get_blacklist_preset()
        vocab = self.preset_manager.load_vocabulary("deepnight_blacklist")

        dialog = PresetEditDialog(vocab, preset, is_general=True, parent=self)
        dialog.preset_saved.connect(lambda pid, name, affixes: self._save_blacklist(affixes))
        dialog.exec()

    def _save_blacklist(self, affixes: list):
        """保存黑名单"""
        self.preset_manager.update_blacklist_preset(affixes)
        self._refresh_presets()
        InfoBar.success("保存成功", "黑名单已更新", parent=self)

    def _start_cleaning(self):
        """开始清理"""
        mode = "normal" if self.mode_combo.currentIndex() == 0 else "deepnight"
        cleaning_mode = "sell" if self.clean_mode_combo.currentIndex() == 0 else "favorite"
        max_relics = self.max_spin.value()

        # 从设置获取参数
        allow_favorited = self.settings.get("allow_operate_favorited", False)
        require_double = self.settings.get("require_double_valid", True)

        # 清空日志
        self.logger.clear()
        self.logger.log("开始清理...", "INFO")

        # 禁用按钮
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)

        # 创建并启动线程
        self.cleaning_thread = CleaningThread(
            self.repo_cleaner, mode, cleaning_mode, max_relics, allow_favorited, require_double
        )
        self.cleaning_thread.log_signal.connect(self.logger.log)
        self.cleaning_thread.finished_signal.connect(self._on_cleaning_finished)
        self.cleaning_thread.start()

    def _stop_cleaning(self):
        """停止清理"""
        if self.cleaning_thread:
            self.repo_cleaner.stop_cleaning()
            self.logger.log("正在停止清理...", "WARNING")

    def _on_cleaning_finished(self):
        """清理完成"""
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.logger.log("清理已完成", "SUCCESS")

        # 更新统计
        stats = self.repo_cleaner.stats
        self._update_dashboard(stats)

    def _update_dashboard(self, stats: dict):
        """更新仪表盘"""
        # 更新统计卡片的值
        for key, value_label in self.stat_value_labels.items():
            if key in stats:
                value_label.setText(str(stats[key]))

    def _load_settings(self) -> dict:
        """加载设置"""
        settings_file = "data/settings.json"
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
