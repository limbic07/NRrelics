"""
商店筛选页面
自动购买遗物并根据预设筛选，保留合格遗物，出售不合格遗物
"""

from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                               QPushButton, QComboBox, QTabWidget,
                               QScrollArea, QFrame, QSplitter, QGroupBox, QLineEdit)
from PySide6.QtCore import Qt, Signal, QThread
from PySide6.QtGui import QFont, QIntValidator
from qfluentwidgets import (CardWidget, PrimaryPushButton, PushButton,
                           ComboBox, MessageBox, InfoBar, InfoBarPosition)

from core.preset_manager import PresetManager, PRESET_TYPE_NORMAL_WHITELIST, PRESET_TYPE_DEEPNIGHT_WHITELIST
from ui.components.logger_widget import LoggerWidget
from core.utils import get_user_data_path
import json
import os


# 合格遗物数据文件路径
QUALIFIED_RELICS_FILE = get_user_data_path("data/shop_qualified_relics.json")



class ShopThread(QThread):
    """商店购买线程"""
    log_signal = Signal(str, str)  # (message, level)
    finished_signal = Signal()
    qualified_relic_signal = Signal(dict)  # 合格遗物信息
    stats_signal = Signal(dict)  # 统计信息

    def __init__(self, shop_automation, mode, version, stop_currency, require_double,
                 sl_mode_enabled=False, sl_qualified_target=0,
                 save_manager=None, steam_id="", backup_path=""):
        super().__init__()
        self.shop_automation = shop_automation
        self.mode = mode
        self.version = version
        self.stop_currency = stop_currency
        self.require_double = require_double
        self.sl_mode_enabled = sl_mode_enabled
        self.sl_qualified_target = sl_qualified_target
        self.save_manager = save_manager
        self.steam_id = steam_id
        self.backup_path = backup_path

    def run(self):
        """运行商店购买"""
        try:
            self.shop_automation.start_shopping(
                self.mode,
                self.version,
                self.stop_currency,
                self.require_double,
                log_callback=self.log_signal.emit,
                stats_callback=self.stats_signal.emit,
                sl_mode_enabled=self.sl_mode_enabled,
                sl_qualified_target=self.sl_qualified_target,
                save_manager=self.save_manager,
                steam_id=self.steam_id,
                backup_path=self.backup_path
            )

            # 购买完成后，发送所有合格遗物信息
            for relic_info in self.shop_automation.qualified_relics:
                self.qualified_relic_signal.emit(relic_info)

        except Exception as e:
            self.log_signal.emit(f"购买过程出错: {e}", "ERROR")
        finally:
            self.finished_signal.emit()


# 导入PresetCard和DragDropContainer from page_repo
from ui.pages.page_repo import PresetCard, DragDropContainer


class PageShop(QWidget):
    """商店筛选页面"""
    settings_changed = Signal()
    presets_modified = Signal()  # 预设修改信号

    def __init__(self, log_manager=None, preset_manager=None):
        super().__init__()
        self.setObjectName("PageShop")

        # 初始化组件
        self.preset_manager = preset_manager if preset_manager else PresetManager()
        self.ocr_engine = None  # 延迟加载，初始为 None

        # 商店自动化实例（延迟初始化）
        self.shop_automation = None

        # 当前模式
        self.current_mode = "normal"

        # 购买线程
        self.shop_thread = None

        # 统计数据
        self.stats = {
            "total_purchased": 0,
            "qualified": 0,
            "unqualified": 0,
            "sold": 0
        }

        # 加载持久化的合格遗物
        self.qualified_relics = self._load_qualified_relics()

        # 加载设置
        self.settings = self._load_settings()

        # 日志管理器
        self.log_manager = log_manager

        self._init_ui()
        self._refresh_presets()
        self._load_qualified_relics_ui()

    def set_ocr_engine(self, engine):
        """设置 OCR 引擎（异步加载完成后调用）"""
        self.ocr_engine = engine
        self.start_btn.setEnabled(True)
        self.start_btn.setText("开始购买")

    def _load_settings(self) -> dict:
        """加载设置"""
        settings_file = get_user_data_path("data/settings.json")
        if os.path.exists(settings_file):
            with open(settings_file, "r", encoding="utf-8") as f:
                return json.load(f)

        return {}

    def update_settings(self, settings: dict):
        """外部更新设置（由设置页面信号触发）"""
        self.settings = settings
        self._update_stop_condition_ui()

    def _update_stop_condition_ui(self):
        """根据SL模式设置切换停止条件UI"""
        sl_enabled = self.settings.get("sl_mode_enabled", False)
        # 停止暗痕
        self.currency_label.setVisible(not sl_enabled)
        self.currency_input.setVisible(not sl_enabled)
        # 停止合格遗物数量
        self.sl_target_label.setVisible(sl_enabled)
        self.sl_target_input.setVisible(sl_enabled)

    def _init_ui(self):
        """初始化UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 8, 16, 16)
        layout.setSpacing(6)

        # 标题
        title = QLabel("商店筛选")
        title.setStyleSheet("font-size: 24pt; font-weight: bold;")
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

        # 调整比例
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 3)

        # 设置初始尺寸（确保2:3比例）
        splitter.setSizes([400, 600])

        layout.addWidget(splitter, 1)

    def _create_toolbar(self) -> CardWidget:
        """创建顶部工具栏"""
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

        # 遗物版本
        version_label = QLabel("版本:")
        layout.addWidget(version_label)

        self.version_combo = ComboBox()
        self.version_combo.addItems(["新版", "旧版"])
        self.version_combo.setFixedWidth(100)
        layout.addWidget(self.version_combo)

        layout.addSpacing(10)

        # 停止条件（根据设置动态切换）
        self.currency_label = QLabel("停止暗痕:")
        layout.addWidget(self.currency_label)

        self.currency_input = QLineEdit()
        self.currency_input.setText("5000")
        self.currency_input.setFixedWidth(120)

        self.currency_input.setFixedHeight(33)
        validator = QIntValidator(0, 2147483647, self)  # 使用int最大值
        self.currency_input.setValidator(validator)
        self.currency_input.setPlaceholderText("输入暗痕数量")
        layout.addWidget(self.currency_input)

        # SL模式：停止合格遗物数量（默认隐藏）
        self.sl_target_label = QLabel("停止合格遗物数量:")
        self.sl_target_label.setVisible(False)
        layout.addWidget(self.sl_target_label)

        self.sl_target_input = QLineEdit()
        self.sl_target_input.setText("1")
        self.sl_target_input.setFixedWidth(120)
        self.sl_target_input.setFixedHeight(33)
        sl_validator = QIntValidator(1, 999, self)
        self.sl_target_input.setValidator(sl_validator)
        self.sl_target_input.setPlaceholderText("合格遗物数")
        self.sl_target_input.setVisible(False)
        layout.addWidget(self.sl_target_input)

        # 根据设置切换显示
        self._update_stop_condition_ui()

        layout.addStretch()

        # 开始/停止按钮
        self.start_btn = PrimaryPushButton("初始化OCR...")
        self.start_btn.setFixedHeight(36)
        self.start_btn.setFixedWidth(120)
        self.start_btn.setEnabled(False)
        self.start_btn.clicked.connect(self._start_shopping)
        layout.addWidget(self.start_btn)

        self.stop_btn = PushButton("停止")
        self.stop_btn.setFixedHeight(36)
        self.stop_btn.setFixedWidth(80)
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self._stop_shopping)
        layout.addWidget(self.stop_btn)

        return card

    def _create_preset_panel(self) -> QWidget:
        """创建预设面板（与仓库清理共享）"""
        panel = QWidget()
        panel.setMinimumWidth(400)  # 设置最小宽度
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        # 标题
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
        layout.addWidget(scroll, 1)

        return panel

    def _create_right_panel(self) -> QWidget:
        """创建右侧面板（日志+仪表盘）"""
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        # TabWidget
        tab_widget = QTabWidget()

        # 日志标签页
        self.logger = LoggerWidget()
        if self.log_manager:
            self.log_manager.subscribe(self.logger)
        tab_widget.addTab(self.logger, "日志")

        # 仪表盘标签页
        dashboard = self._create_dashboard()
        tab_widget.addTab(dashboard, "仪表盘")

        layout.addWidget(tab_widget)

        return panel

    def _create_dashboard(self) -> QWidget:
        """创建仪表盘"""
        dashboard = QWidget()
        layout = QVBoxLayout(dashboard)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)

        # 统计卡片
        stats_layout = QHBoxLayout()

        self.stat_value_labels = {}

        purchased_card, purchased_value = self._create_stat_card("已购买", "0", "#2196F3")
        self.stat_value_labels["total_purchased"] = purchased_value
        stats_layout.addWidget(purchased_card)

        qualified_card, qualified_value = self._create_stat_card("合格", "0", "#4CAF50")
        self.stat_value_labels["qualified"] = qualified_value
        stats_layout.addWidget(qualified_card)

        unqualified_card, unqualified_value = self._create_stat_card("不合格", "0", "#FF9800")
        self.stat_value_labels["unqualified"] = unqualified_value
        stats_layout.addWidget(unqualified_card)

        sold_card, sold_value = self._create_stat_card("已售出", "0", "#F44336")
        self.stat_value_labels["sold"] = sold_value
        stats_layout.addWidget(sold_card)

        layout.addLayout(stats_layout)

        # 合格遗物列表
        qualified_group = QGroupBox("合格遗物词条")
        qualified_layout = QVBoxLayout(qualified_group)
        qualified_layout.setContentsMargins(8, 8, 8, 8)
        qualified_layout.setSpacing(4)

        # 清空按钮
        clear_btn = PushButton("清空记录")
        clear_btn.clicked.connect(self._clear_qualified_relics)
        qualified_layout.addWidget(clear_btn)

        # 滚动区域
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        scroll_content = QWidget()
        self.qualified_relics_layout = QVBoxLayout(scroll_content)
        self.qualified_relics_layout.setSpacing(6)
        self.qualified_relics_layout.addStretch()

        scroll.setWidget(scroll_content)
        qualified_layout.addWidget(scroll)

        layout.addWidget(qualified_group, 1)

        return dashboard

    def _create_stat_card(self, title: str, value: str, color: str) -> tuple:
        """创建统计卡片，返回(card, value_label)"""
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

        # 添加按钮
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
        self.presets_modified.emit()  # 发出预设修改信号

    def refresh_presets_ui(self):
        """外部调用：刷新预设UI（当其他页面修改预设时）"""
        self._refresh_presets()

    def _on_mode_changed(self):
        """模式切换"""
        self.current_mode = "normal" if self.mode_combo.currentIndex() == 0 else "deepnight"
        self._refresh_presets()

    def _edit_general_preset(self, preset_id: str):
        """编辑通用预设"""
        from ui.dialogs.preset_edit_dialog import PresetEditDialog

        mode = "normal" if self.mode_combo.currentIndex() == 0 else "deepnight"
        preset = self.preset_manager.get_general_preset(mode)
        vocab = self.preset_manager.load_vocabulary(
            PRESET_TYPE_NORMAL_WHITELIST if mode == "normal" else PRESET_TYPE_DEEPNIGHT_WHITELIST,
            for_editing=True
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
            for_editing=True
        )

        dialog = PresetEditDialog(vocab, None, is_general=False, parent=self)
        dialog.preset_saved.connect(lambda pid, name, affixes: self._save_dedicated_preset(mode, name, affixes))
        dialog.exec()

    def _save_dedicated_preset(self, mode: str, name: str, affixes: list):
        """保存专用预设"""
        self.preset_manager.create_dedicated_preset(mode, name, affixes)
        self._refresh_presets()
        self.presets_modified.emit()  # 发出预设修改信号
        InfoBar.success("创建成功", f"专用预设 \"{name}\" 已创建", parent=self)

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
            for_editing=True
        )

        dialog = PresetEditDialog(vocab, preset, is_general=False, parent=self)
        dialog.preset_saved.connect(lambda pid, name, affixes: self._update_dedicated_preset(mode, pid, name, affixes))
        dialog.exec()

    def _update_dedicated_preset(self, mode: str, preset_id: str, name: str, affixes: list):
        """更新专用预设"""
        self.preset_manager.update_dedicated_preset(mode, preset_id, name, affixes)
        self._refresh_presets()
        self.presets_modified.emit()  # 发出预设修改信号
        InfoBar.success("保存成功", f"专用预设 \"{name}\" 已更新", parent=self)

    def _delete_preset(self, preset_id: str):
        """删除预设"""
        mode = "normal" if self.mode_combo.currentIndex() == 0 else "deepnight"
        presets = self.preset_manager.get_dedicated_presets(mode)
        preset = presets.get(preset_id)
        if not preset:
            return

        msg_box = MessageBox("确认删除", f"确定要删除预设 \"{preset['name']}\" 吗？", self)
        if msg_box.exec():
            self.preset_manager.delete_dedicated_preset(mode, preset_id)
            self._refresh_presets()
            self.presets_modified.emit()  # 发出预设修改信号
            InfoBar.success("删除成功", f"预设 \"{preset['name']}\" 已删除", parent=self)

    def _toggle_preset(self, preset_id: str):
        """切换预设启用状态"""
        mode = "normal" if self.mode_combo.currentIndex() == 0 else "deepnight"
        self.preset_manager.toggle_preset_active(mode, preset_id)
        self._refresh_presets()

    def _edit_blacklist_preset(self, preset_id: str):
        """编辑黑名单预设"""
        from ui.dialogs.preset_edit_dialog import PresetEditDialog

        preset = self.preset_manager.get_blacklist_preset()
        vocab = self.preset_manager.load_vocabulary(
            "deepnight_blacklist",
            for_editing=True
        )

        dialog = PresetEditDialog(vocab, preset, is_general=True, parent=self)
        dialog.preset_saved.connect(lambda pid, name, affixes: self._save_blacklist_preset(affixes))
        dialog.exec()

    def _save_blacklist_preset(self, affixes: list):
        """保存黑名单预设"""
        self.preset_manager.update_blacklist_preset(affixes)
        self._refresh_presets()
        InfoBar.success("保存成功", "黑名单预设已更新", parent=self)

    def _start_shopping(self):
        """开始购买"""
        if self.shop_thread and self.shop_thread.isRunning():
            InfoBar.warning("提示", "购买正在进行中", parent=self)
            return

        # 检查 OCR 引擎是否已加载
        if not self.ocr_engine:
            InfoBar.error("错误", "OCR 引擎未加载，请稍后再试", parent=self)
            return

        # 初始化商店自动化（延迟初始化）
        if not self.shop_automation:
            from core.shop_automation import ShopAutomation
            from core.automation import RepositoryFilter

            repo_filter = RepositoryFilter(self.settings)
            self.shop_automation = ShopAutomation(
                self.ocr_engine,
                self.preset_manager,
                repo_filter,
                self.settings
            )

        # 获取参数
        mode = "normal" if self.mode_combo.currentIndex() == 0 else "deepnight"
        version = "new" if self.version_combo.currentIndex() == 0 else "old"
        stop_currency = int(self.currency_input.text() or "0")

        # 获取商店三有效设置
        settings_file = get_user_data_path("data/settings.json")
        require_double = True  # 默认双有效
        if os.path.exists(settings_file):

            with open(settings_file, "r", encoding="utf-8") as f:
                settings = json.load(f)
                require_double = settings.get("shop_require_double_valid", True)

        # SL 模式参数
        sl_mode_enabled = self.settings.get("sl_mode_enabled", False)
        sl_qualified_target = int(self.sl_target_input.text() or "0") if sl_mode_enabled else 0
        save_manager = None
        steam_id = ""
        backup_path = ""

        # SL 模式：备份存档
        if sl_mode_enabled and sl_qualified_target > 0:
            from core.save_manager import SaveManager
            steam_path = self.settings.get("steam_path", "")
            save_manager = SaveManager(steam_path)
            steam_id = save_manager.get_most_recent_user()

            if not steam_id:
                InfoBar.error("错误", "未检测到Steam用户，无法使用合格遗物数量停止功能", parent=self)
                return

            # 备份存档
            backup_dir = os.path.join(save_manager.BACKUP_DIR, steam_id)
            existing_path = os.path.join(backup_dir, "sl_auto_backup.sl2")
            if os.path.exists(existing_path):
                # 已有自动备份，覆盖更新
                os.remove(existing_path)

            success, msg = save_manager.backup_save(steam_id, "sl_auto_backup")
            if not success:
                InfoBar.error("错误", f"存档备份失败: {msg}", parent=self)
                return
            backup_path = existing_path

        # 清空日志和统计
        self.logger.clear()
        if self.log_manager:
            self.log_manager.clear_all()  # 清空所有订阅者的日志
        self.stats = {
            "total_purchased": 0,
            "qualified": 0,
            "unqualified": 0,
            "sold": 0
        }
        self._update_stats()

        # 清空合格遗物列表和UI
        self.qualified_relics.clear()
        while self.qualified_relics_layout.count() > 1:  # 保留stretch
            item = self.qualified_relics_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # 创建并启动线程
        self.shop_thread = ShopThread(
            self.shop_automation,
            mode,
            version,
            stop_currency,
            require_double,
            sl_mode_enabled=sl_mode_enabled,
            sl_qualified_target=sl_qualified_target,
            save_manager=save_manager,
            steam_id=steam_id,
            backup_path=backup_path
        )
        self.shop_thread.log_signal.connect(self._on_log)
        self.shop_thread.qualified_relic_signal.connect(self._add_qualified_relic)
        self.shop_thread.stats_signal.connect(self._update_stats_from_signal)
        self.shop_thread.finished_signal.connect(self._on_shopping_finished)
        self.shop_thread.start()

        # 更新按钮状态
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)

        if sl_mode_enabled and sl_qualified_target > 0:
            log_msg = f"开始购买遗物（目标: {sl_qualified_target}个合格遗物）..."
        else:
            log_msg = "开始购买遗物..."

        if self.log_manager:
            self.log_manager.log(log_msg, "INFO")
        else:
            self.logger.log(log_msg, "INFO")

    def _on_log(self, message: str, level: str):
        """处理日志信号"""
        if self.log_manager:
            self.log_manager.log(message, level)
        else:
            self.logger.log(message, level)

    def _stop_shopping(self):
        """停止购买"""
        if self.shop_automation:
            self.shop_automation.stop()
            if self.log_manager:
                self.log_manager.log("正在停止购买...", "WARNING")
            else:
                self.logger.log("正在停止购买...", "WARNING")

    def _on_shopping_finished(self):
        """购买完成"""
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        if self.log_manager:
            self.log_manager.log("购买已完成", "INFO")
        else:
            self.logger.log("购买已完成", "INFO")

    def _add_qualified_relic(self, relic_info: dict):
        """添加合格遗物到UI和持久化存储"""
        # 添加到内存
        self.qualified_relics.append(relic_info)

        # 持久化保存
        self._save_qualified_relics()

        # 添加到UI
        self._add_qualified_relic_ui(relic_info)

    def _add_qualified_relic_ui(self, relic_info: dict):
        """添加合格遗物到UI"""
        card = CardWidget()
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(8, 6, 8, 6)
        card_layout.setSpacing(4)

        # 时间戳
        timestamp_label = QLabel(relic_info.get("timestamp", ""))
        timestamp_label.setFont(QFont("Segoe UI", 8))
        timestamp_label.setStyleSheet("color: gray;")
        card_layout.addWidget(timestamp_label)

        # 词条列表
        affixes = relic_info.get("affixes", [])
        for affix_info in affixes:
            affix_text = affix_info.get("text", "")
            is_positive = affix_info.get("is_positive", True)
            color = "#4CAF50" if is_positive else "#F44336"

            affix_label = QLabel(f"• {affix_text}")
            affix_label.setFont(QFont("Segoe UI", 9))
            affix_label.setStyleSheet(f"color: {color};")
            card_layout.addWidget(affix_label)

        # 插入到布局顶部（最新的在上面）
        self.qualified_relics_layout.insertWidget(0, card)

    def _update_stats(self):
        """更新统计显示"""
        self.stat_value_labels["total_purchased"].setText(str(self.stats["total_purchased"]))
        self.stat_value_labels["qualified"].setText(str(self.stats["qualified"]))
        self.stat_value_labels["unqualified"].setText(str(self.stats["unqualified"]))
        self.stat_value_labels["sold"].setText(str(self.stats["sold"]))

    def _update_stats_from_signal(self, stats: dict):
        """从信号更新统计"""
        self.stats.update(stats)
        self._update_stats()

    def _load_qualified_relics(self) -> list:
        """从文件加载合格遗物"""
        if os.path.exists(QUALIFIED_RELICS_FILE):
            try:
                with open(QUALIFIED_RELICS_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                print(f"加载合格遗物失败: {e}")
                return []
        return []

    def _save_qualified_relics(self):
        """保存合格遗物到文件"""
        try:
            os.makedirs(os.path.dirname(QUALIFIED_RELICS_FILE), exist_ok=True)
            with open(QUALIFIED_RELICS_FILE, "w", encoding="utf-8") as f:
                json.dump(self.qualified_relics, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"保存合格遗物失败: {e}")

    def _load_qualified_relics_ui(self):
        """加载合格遗物到UI"""
        for relic_info in self.qualified_relics:
            self._add_qualified_relic_ui(relic_info)

    def _clear_qualified_relics(self):
        """清空合格遗物记录"""
        msg_box = MessageBox("确认清空", "确定要清空所有合格遗物记录吗？", self)
        if msg_box.exec():
            self.qualified_relics.clear()
            self._save_qualified_relics()

            # 清空UI
            while self.qualified_relics_layout.count() > 1:  # 保留stretch
                item = self.qualified_relics_layout.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()

            InfoBar.success("清空成功", "合格遗物记录已清空", parent=self)
