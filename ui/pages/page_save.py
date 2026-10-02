"""存档管理页面"""

from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                               QLineEdit, QInputDialog, QMessageBox, QScrollArea,
                               QDialog, QDialogButtonBox, QFileDialog, QApplication)
from PySide6.QtCore import Qt, Signal, QObject, QThread
from PySide6.QtGui import QFont
from qfluentwidgets import (CardWidget, ComboBox, PrimaryPushButton, PushButton,
                           InfoBar, InfoBarPosition, LineEdit as FluentLineEdit,
                           isDarkTheme)
import os
import json

from core.save_manager import SaveManager
from core.affix_catalog import validation_affix_names
from core.relic_validation import ReadOnlySaveValidator, ValidationReport, ValidationStatus
from core.utils import get_user_data_path


class _ValidationWorker(QObject):
    finished = Signal(object)

    def __init__(self, path: str):
        super().__init__()
        self.path = path

    def run(self):
        try:
            report = ReadOnlySaveValidator().validate_path(self.path)
        except Exception as exc:
            report = ValidationReport(ValidationStatus.UNKNOWN, reasons=(f"验证失败：{exc}",))
        self.finished.emit(report)


class SavePage(QWidget):
    """存档管理页面"""

    steam_path_selected = Signal(str)

    def __init__(self):
        super().__init__()
        self.setObjectName("SavePage")

        # 加载设置中的Steam路径
        self.settings_file = get_user_data_path("data/settings.json")
        steam_path = self._load_steam_path()

        # 初始化存档管理器
        self.save_manager = SaveManager(steam_path)

        self._init_ui()
        self._refresh_all()

    def _load_steam_path(self) -> str:
        """从设置文件加载Steam路径"""
        if os.path.exists(self.settings_file):
            try:
                with open(self.settings_file, 'r', encoding='utf-8') as f:
                    settings = json.load(f)
                return settings.get("steam_path", "")
            except Exception:
                pass
        return ""

    def _init_ui(self):
        """初始化UI"""
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        self.page_scroll = QScrollArea(self)
        self.page_scroll.setWidgetResizable(True)
        self.page_scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        self.page_content = QWidget()
        layout = QVBoxLayout(self.page_content)
        layout.setContentsMargins(32, 32, 32, 32)
        layout.setSpacing(16)

        # 标题
        title = QLabel("存档管理")
        title.setStyleSheet("font-size: 24pt; font-weight: bold;")
        layout.addWidget(title)

        # 用户选择卡片
        user_card = self._create_user_card()
        layout.addWidget(user_card)

        # 当前存档信息卡片
        self.save_info_card = self._create_save_info_card()
        layout.addWidget(self.save_info_card)

        self.validation_card = self._create_validation_card()
        layout.addWidget(self.validation_card)

        # 备份列表卡片
        self.backup_card = self._create_backup_card()
        layout.addWidget(self.backup_card, 1)  # stretch=1 填满剩余空间
        self.page_scroll.setWidget(self.page_content)
        outer_layout.addWidget(self.page_scroll)

    def _create_user_card(self) -> CardWidget:
        """创建用户选择卡片"""
        card = CardWidget()
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(20, 20, 20, 20)
        card_layout.setSpacing(12)

        title = QLabel("Steam 用户")
        title.setStyleSheet("font-size: 16pt; font-weight: bold;")
        card_layout.addWidget(title)

        # 用户选择
        user_layout = QHBoxLayout()
        user_label = QLabel("选择用户:")
        user_label.setFixedWidth(80)
        user_layout.addWidget(user_label)

        self.user_combo = ComboBox()
        self.user_combo.setFixedWidth(300)
        self._populate_user_combo()
        self.user_combo.currentIndexChanged.connect(self._on_user_changed)
        user_layout.addWidget(self.user_combo)

        user_layout.addStretch()
        card_layout.addLayout(user_layout)

        # Steam 路径与修改入口
        steam_path_layout = QHBoxLayout()
        self.steam_status_label = QLabel(
            f"Steam路径: {self.save_manager.steam_path or '未检测到，请修改路径或自动检测'}")
        self.steam_status_label.setFont(QFont("Segoe UI", 8))
        self.steam_status_label.setWordWrap(True)
        self.steam_status_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self._update_steam_status_style()
        steam_path_layout.addWidget(self.steam_status_label, 1)

        self.steam_browse_btn = PushButton("浏览修改")
        self.steam_browse_btn.clicked.connect(self._browse_steam_path)
        steam_path_layout.addWidget(self.steam_browse_btn)

        self.steam_detect_btn = PushButton("自动检测")
        self.steam_detect_btn.clicked.connect(self._auto_detect_steam_path)
        steam_path_layout.addWidget(self.steam_detect_btn)
        card_layout.addLayout(steam_path_layout)

        return card

    def _create_validation_card(self) -> CardWidget:
        """Create the non-mutating save rule validation controls."""
        card = CardWidget()
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(20, 20, 20, 20)
        card_layout.setSpacing(8)

        title = QLabel("违规遗物检测")
        title.setStyleSheet("font-size: 16pt; font-weight: bold;")
        card_layout.addWidget(title)
        note = QLabel("仅列出违规遗物，包括用CE修改的合法遗物（只读取不修改存档）")
        note.setWordWrap(True)
        card_layout.addWidget(note)

        controls = QHBoxLayout()
        self.validate_current_btn = PushButton("验证当前存档")
        self.validate_current_btn.clicked.connect(self._validate_current_save)
        controls.addWidget(self.validate_current_btn)
        self.validate_file_btn = PushButton("选择存档")
        self.validate_file_btn.clicked.connect(self._choose_validation_file)
        controls.addWidget(self.validate_file_btn)
        controls.addStretch()
        card_layout.addLayout(controls)

        players = QHBoxLayout()
        players.addWidget(QLabel("选择角色："))
        self.validation_player_combo = ComboBox()
        self.validation_player_combo.addItem("全部角色", userData=None)
        self.validation_player_combo.setEnabled(False)
        self.validation_player_combo.currentIndexChanged.connect(self._render_validation_report)
        players.addWidget(self.validation_player_combo)
        players.addStretch()
        card_layout.addLayout(players)
        self._validation_report = None

        self.validation_status_label = QLabel("尚未验证")
        self.validation_status_label.setWordWrap(True)
        card_layout.addWidget(self.validation_status_label)
        self.validation_scroll = QScrollArea()
        self.validation_scroll.setWidgetResizable(True)
        self.validation_scroll.setMinimumHeight(180)
        self.validation_scroll.setMaximumHeight(360)
        self.validation_results = QWidget()
        self.validation_results_layout = QVBoxLayout(self.validation_results)
        self.validation_results_layout.setContentsMargins(0, 0, 0, 0)
        self.validation_results_layout.setSpacing(8)
        self.validation_results_layout.addStretch()
        self.validation_entries = []
        self.validation_scroll.setWidget(self.validation_results)
        card_layout.addWidget(self.validation_scroll)
        return card

    def _validate_current_save(self):
        steam_id = self._get_current_steam_id()
        if steam_id:
            self._start_validation(self.save_manager.get_save_path(steam_id))

    def _choose_validation_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "选择存档", "", "Nightreign save (*.sl2 *.co2);;All files (*)")
        if path:
            self._start_validation(path)

    def _start_validation(self, path: str):
        if getattr(self, "_validation_thread", None) is not None:
            return
        if not os.path.isfile(path):
            self._on_validation_finished(ValidationReport(
                ValidationStatus.UNKNOWN, reasons=("无法验证：文件不存在。",), source=path))
            return
        self.validate_current_btn.setEnabled(False)
        self.validate_file_btn.setEnabled(False)
        self.validation_player_combo.setEnabled(False)
        self.validation_status_label.setText("正在只读验证，不会写入或修改存档……")
        # App ownership keeps a worker alive even if this page is destroyed.
        self._validation_thread = QThread(QApplication.instance())
        self._validation_worker = _ValidationWorker(path)
        self._validation_worker.moveToThread(self._validation_thread)
        self._validation_thread.started.connect(self._validation_worker.run)
        self._validation_worker.finished.connect(self._on_validation_finished)
        self._validation_worker.finished.connect(self._validation_thread.quit, Qt.DirectConnection)
        self._validation_worker.finished.connect(self._validation_worker.deleteLater)
        self._validation_thread.finished.connect(self._validation_thread.deleteLater)
        self._validation_thread.finished.connect(self._validation_done)
        QApplication.instance().aboutToQuit.connect(self._validation_thread.quit)
        QApplication.instance().aboutToQuit.connect(self._validation_thread.wait)
        self._validation_thread.start()

    def closeEvent(self, event):
        thread = getattr(self, "_validation_thread", None)
        if thread is not None:
            thread.quit()
            thread.wait()
        super().closeEvent(event)

    def _validation_done(self):
        self.validate_current_btn.setEnabled(True)
        self.validate_file_btn.setEnabled(True)
        self.validation_player_combo.setEnabled(self.validation_player_combo.count() > 1)
        self._validation_thread = None
        self._validation_worker = None

    def _on_validation_finished(self, report: ValidationReport):
        self._validation_report = report
        self.validation_player_combo.blockSignals(True)
        self.validation_player_combo.clear()
        self.validation_player_combo.addItem("全部角色", userData=None)
        players = {}
        for item in report.results:
            players.setdefault(item.relic.slot, item.relic.player_name or "未命名角色")
        for slot, name in players.items():
            self.validation_player_combo.addItem(name, userData=slot)
        self.validation_player_combo.setCurrentIndex(0)
        self.validation_player_combo.blockSignals(False)
        self.validation_player_combo.setEnabled(len(players) > 0)
        self._render_validation_report()

    def _render_validation_report(self, *_):
        report = self._validation_report
        if report is None:
            return
        slot = self.validation_player_combo.currentData()
        if slot is not None:
            results = tuple(item for item in report.results if item.relic.slot == slot)
            statuses = {item.status for item in results}
            status = (ValidationStatus.UNKNOWN if report.reasons
                      else ValidationStatus.VIOLATES if ValidationStatus.VIOLATES in statuses
                      else ValidationStatus.UNKNOWN if ValidationStatus.UNKNOWN in statuses or not results
                      else ValidationStatus.CONFORMS)
            report = ValidationReport(status, results, report.reasons, report.source)
        labels = {
            ValidationStatus.CONFORMS: "符合已知规则（不代表官方有效性或无封禁风险）",
            ValidationStatus.VIOLATES: "违反明确的已知规则",
            ValidationStatus.UNKNOWN: "未知：无法对该存档或遗物作出安全判断",
        }
        detail = "；".join(report.reasons)
        counts = {status: sum(item.status is status for item in report.results) for status in ValidationStatus}
        summary = (f"共 {len(report.results)} 个遗物：符合 {counts[ValidationStatus.CONFORMS]}，"
                   f"违反 {counts[ValidationStatus.VIOLATES]}，无法判定 {counts[ValidationStatus.UNKNOWN]}。")
        if (report.status is ValidationStatus.CONFORMS and report.results
                and counts[ValidationStatus.CONFORMS] == len(report.results) and not report.reasons):
            self.validation_status_label.setText("所有遗物都合法")
        elif not report.results and report.status is ValidationStatus.CONFORMS:
            self.validation_status_label.setText("未检测到遗物，无法确认全部合法。")
        else:
            self.validation_status_label.setText(summary + labels[report.status] + (f"：{detail}" if detail else ""))
        while self.validation_results_layout.count() > 1:
            child = self.validation_results_layout.takeAt(0).widget()
            if child is not None:
                child.setParent(None)
                child.deleteLater()
        self.validation_entries.clear()
        names = validation_affix_names()
        by_slot = {}
        for item in report.results:
            if item.status is not ValidationStatus.VIOLATES:
                continue
            by_slot.setdefault(item.relic.slot or "未知槽位", []).append(item.relic)
        color_names = {"Red": "红色", "Blue": "蓝色", "Yellow": "黄色",
                       "Green": "绿色", "White": "白色"}
        for slot, relics in by_slot.items():
            header = QLabel(f"玩家：{relics[0].player_name or '未命名角色'}")
            header.setTextFormat(Qt.PlainText)
            header.setStyleSheet("font-size: 10pt; font-weight: bold;")
            self.validation_results_layout.insertWidget(self.validation_results_layout.count() - 1, header)
            for relic in relics:
                entry = CardWidget()
                entry_layout = QVBoxLayout(entry)
                entry_layout.setContentsMargins(8, 6, 8, 6)
                entry_layout.setSpacing(4)
                title = QLabel(f"{color_names.get(relic.color, '未知颜色')} · "
                               f"{'已收藏' if relic.favorite else '未收藏'}")
                title.setStyleSheet("font-size: 10pt; font-weight: bold;")
                entry_layout.addWidget(title)
                for index in range(3):
                    for effect, positive in ((relic.effects[index], True),
                                             (relic.effects[index + 3], False)):
                        if effect in ReadOnlySaveValidator.EMPTY_EFFECTS:
                            continue
                        text = names.get(effect, f"未知词条（ID: {effect}）")
                        affix = QLabel(f"[{'正面' if positive else '负面'}] {text}")
                        affix.setFont(QFont("Segoe UI", 9))
                        affix.setStyleSheet(f"color: {'#4CAF50' if positive else '#FF5722'};")
                        affix.setWordWrap(True)
                        affix.setTextInteractionFlags(Qt.TextSelectableByMouse)
                        entry_layout.addWidget(affix)
                self.validation_results_layout.insertWidget(self.validation_results_layout.count() - 1, entry)
                self.validation_entries.append(entry)

    def _create_save_info_card(self) -> CardWidget:
        """创建存档信息卡片"""
        card = CardWidget()
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(20, 20, 20, 20)
        card_layout.setSpacing(12)

        title = QLabel("当前存档")
        title.setStyleSheet("font-size: 16pt; font-weight: bold;")
        card_layout.addWidget(title)

        # 存档信息
        info_layout = QHBoxLayout()

        self.save_status_label = QLabel("存档状态: 检测中...")
        info_layout.addWidget(self.save_status_label)

        info_layout.addStretch()

        self.save_time_label = QLabel("")
        info_layout.addWidget(self.save_time_label)

        card_layout.addLayout(info_layout)

        # 操作按钮
        btn_layout = QHBoxLayout()

        self.backup_btn = PrimaryPushButton("备份存档")
        self.backup_btn.setFixedWidth(120)
        self.backup_btn.clicked.connect(self._backup_save)
        btn_layout.addWidget(self.backup_btn)

        self.refresh_btn = PushButton("刷新")
        self.refresh_btn.setFixedWidth(80)
        self.refresh_btn.clicked.connect(self._refresh_all)
        btn_layout.addWidget(self.refresh_btn)

        btn_layout.addStretch()
        card_layout.addLayout(btn_layout)

        return card

    def _create_backup_card(self) -> CardWidget:
        """创建备份列表卡片"""
        card = CardWidget()
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(20, 20, 20, 20)
        card_layout.setSpacing(12)

        title = QLabel("备份列表")
        title.setStyleSheet("font-size: 16pt; font-weight: bold;")
        card_layout.addWidget(title)

        # 备份列表滚动区域（移除最大高度限制，让它填满剩余空间）
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; }")

        self.backup_list_widget = QWidget()
        self.backup_list_layout = QVBoxLayout(self.backup_list_widget)
        self.backup_list_layout.setContentsMargins(0, 0, 0, 0)
        self.backup_list_layout.setSpacing(8)
        self.backup_list_layout.addStretch()

        scroll.setWidget(self.backup_list_widget)
        card_layout.addWidget(scroll)

        return card

    def _populate_user_combo(self):
        """填充用户下拉框"""
        self.user_combo.clear()
        users = self.save_manager.get_users()
        most_recent_id = self.save_manager.get_most_recent_user()
        default_index = 0

        for i, (steam_id, info) in enumerate(users.items()):
            display = f"{info['name']} ({steam_id})"
            if info.get("most_recent"):
                display += " [最近登录]"
                default_index = i
            self.user_combo.addItem(display, userData=steam_id)

        if users:
            self.user_combo.setCurrentIndex(default_index)

        if not users:
            self.user_combo.addItem("未检测到Steam用户")

    def _get_current_steam_id(self) -> str:
        """获取当前选中的Steam用户ID"""
        index = self.user_combo.currentIndex()
        if index >= 0:
            data = self.user_combo.itemData(index)
            if data:
                return data
        return ""

    def _on_user_changed(self):
        """用户切换"""
        self._refresh_save_info()
        self._refresh_backup_list()

    def _refresh_all(self):
        """刷新所有信息"""
        self._refresh_save_info()
        self._refresh_backup_list()

    def _refresh_save_info(self):
        """刷新存档信息"""
        steam_id = self._get_current_steam_id()
        if not steam_id:
            self.save_status_label.setText("存档状态: 未选择用户")
            self.save_time_label.setText("")
            self.backup_btn.setEnabled(False)
            return

        info = self.save_manager.get_save_info(steam_id)
        if info["exists"]:
            size_mb = info["size"] / (1024 * 1024)
            self.save_status_label.setText(f"存档状态: 已找到 ({size_mb:.1f} MB)")
            self.save_time_label.setText(f"最后修改: {info['modified_time']}")
            self.backup_btn.setEnabled(True)
        else:
            self.save_status_label.setText("存档状态: 未找到存档文件")
            self.save_time_label.setText("")
            self.backup_btn.setEnabled(False)

    def _refresh_backup_list(self):
        """刷新备份列表"""
        # 清空现有列表
        while self.backup_list_layout.count() > 1:  # 保留stretch
            item = self.backup_list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        steam_id = self._get_current_steam_id()
        if not steam_id:
            return

        backups = self.save_manager.get_backups(steam_id)

        if not backups:
            no_backup_label = QLabel("暂无备份")
            no_backup_label.setStyleSheet(f"color: {'#aaaaaa' if isDarkTheme() else 'gray'};")
            no_backup_label.setAlignment(Qt.AlignCenter)
            self.backup_list_layout.insertWidget(0, no_backup_label)
            return

        for backup in backups:
            row = self._create_backup_row(backup)
            self.backup_list_layout.insertWidget(self.backup_list_layout.count() - 1, row)

    def _create_backup_row(self, backup: dict) -> QWidget:
        """创建备份行"""
        row = QWidget()
        secondary_color = "#aaaaaa" if isDarkTheme() else "gray"
        name_color = "#e0e0e0" if isDarkTheme() else "#333333"
        row_bg = "#2d2d2d" if isDarkTheme() else "#f8f8f8"
        row.setStyleSheet(f"QWidget {{ background-color: {row_bg}; border-radius: 6px; padding: 4px; }}")
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(12, 8, 12, 8)
        row_layout.setSpacing(12)

        # 备份名称
        name_label = QLabel(backup["display_name"])
        name_label.setFont(QFont("Segoe UI", 10))
        name_label.setMinimumWidth(150)
        name_label.setStyleSheet(f"color: {name_color};")
        row_layout.addWidget(name_label)

        # 修改时间
        time_label = QLabel(backup["modified_time"])
        time_label.setFont(QFont("Segoe UI", 8))
        time_label.setStyleSheet(f"color: {secondary_color};")
        row_layout.addWidget(time_label)

        # 文件大小
        size_mb = backup["size"] / (1024 * 1024)
        size_label = QLabel(f"{size_mb:.1f} MB")
        size_label.setFont(QFont("Segoe UI", 8))
        size_label.setStyleSheet(f"color: {secondary_color};")
        size_label.setFixedWidth(60)
        row_layout.addWidget(size_label)

        row_layout.addStretch()

        # 操作按钮
        validate_btn = PushButton("只读验证")
        validate_btn.setFixedSize(80, 28)
        validate_btn.clicked.connect(lambda checked, b=backup: self._start_validation(b["path"]))
        row_layout.addWidget(validate_btn)

        restore_btn = PrimaryPushButton("恢复")
        restore_btn.setFixedSize(60, 28)
        restore_btn.clicked.connect(lambda checked, b=backup: self._restore_backup(b))
        row_layout.addWidget(restore_btn)

        rename_btn = PushButton("重命名")
        rename_btn.setFixedSize(70, 28)
        rename_btn.clicked.connect(lambda checked, b=backup: self._rename_backup(b))
        row_layout.addWidget(rename_btn)

        delete_btn = PushButton("删除")
        delete_btn.setFixedSize(60, 28)
        delete_btn.clicked.connect(lambda checked, b=backup: self._delete_backup(b))
        row_layout.addWidget(delete_btn)

        return row

    def _backup_save(self):
        """备份存档"""
        steam_id = self._get_current_steam_id()
        if not steam_id:
            return

        # 创建自定义对话框，设置更大的输入框
        dialog = QDialog(self)
        dialog.setWindowTitle("备份存档")
        dialog.setMinimumWidth(400)

        layout = QVBoxLayout(dialog)
        layout.setSpacing(12)

        label = QLabel("输入备份名称（留空使用时间戳）:")
        layout.addWidget(label)

        line_edit = FluentLineEdit()
        line_edit.setMinimumWidth(350)
        line_edit.setFixedHeight(35)
        layout.addWidget(line_edit)

        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(dialog.accept)
        button_box.rejected.connect(dialog.reject)
        layout.addWidget(button_box)

        if dialog.exec() != QDialog.Accepted:
            return

        name = line_edit.text().strip()

        success, message = self.save_manager.backup_save(steam_id, name)

        if success:
            InfoBar.success(
                title="备份成功",
                content=message,
                orient=Qt.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=self
            )
            self._refresh_backup_list()
        else:
            InfoBar.error(
                title="备份失败",
                content=message,
                orient=Qt.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=self
            )

    def _restore_backup(self, backup: dict):
        """恢复备份"""
        steam_id = self._get_current_steam_id()
        if not steam_id:
            return

        reply = QMessageBox.question(
            self, "确认恢复",
            f"确定要恢复备份 \"{backup['display_name']}\" 吗？\n当前存档将被覆盖。",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply != QMessageBox.Yes:
            return

        success, message = self.save_manager.restore_save(steam_id, backup["path"])

        if success:
            InfoBar.success(
                title="恢复成功",
                content=message,
                orient=Qt.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=self
            )
            self._refresh_save_info()
        else:
            InfoBar.error(
                title="恢复失败",
                content=message,
                orient=Qt.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=self
            )

    def _rename_backup(self, backup: dict):
        """重命名备份"""
        # 创建自定义对话框，设置更大的输入框
        dialog = QDialog(self)
        dialog.setWindowTitle("重命名备份")
        dialog.setMinimumWidth(400)

        layout = QVBoxLayout(dialog)
        layout.setSpacing(12)

        label = QLabel("输入新名称:")
        layout.addWidget(label)

        line_edit = FluentLineEdit()
        line_edit.setText(backup["display_name"])
        line_edit.setMinimumWidth(350)
        line_edit.setFixedHeight(35)
        layout.addWidget(line_edit)

        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(dialog.accept)
        button_box.rejected.connect(dialog.reject)
        layout.addWidget(button_box)

        if dialog.exec() != QDialog.Accepted:
            return

        name = line_edit.text().strip()
        if not name:
            return

        success, message = self.save_manager.rename_backup(backup["path"], name)

        if success:
            InfoBar.success(
                title="重命名成功",
                content=message,
                orient=Qt.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=self
            )
            self._refresh_backup_list()
        else:
            InfoBar.error(
                title="重命名失败",
                content=message,
                orient=Qt.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=self
            )

    def _delete_backup(self, backup: dict):
        """删除备份"""
        reply = QMessageBox.question(
            self, "确认删除",
            f"确定要删除备份 \"{backup['display_name']}\" 吗？\n此操作不可撤销。",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply != QMessageBox.Yes:
            return

        success, message = self.save_manager.delete_backup(backup["path"])

        if success:
            InfoBar.success(
                title="删除成功",
                content=message,
                orient=Qt.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=self
            )
            self._refresh_backup_list()
        else:
            InfoBar.error(
                title="删除失败",
                content=message,
                orient=Qt.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=self
            )

    def update_steam_path(self, steam_path: str):
        """外部更新Steam路径"""
        self.save_manager.set_steam_path(steam_path)
        self._populate_user_combo()
        self.steam_status_label.setText(
            f"Steam路径: {self.save_manager.steam_path or '未检测到，请修改路径或自动检测'}")
        self._update_steam_status_style()
        self._refresh_all()

    def _select_steam_path(self, steam_path: str):
        """由存档页选择路径，并同步到设置页持久化。"""
        self.update_steam_path(steam_path)
        self.steam_path_selected.emit(self.save_manager.steam_path)

    def _browse_steam_path(self):
        """浏览并验证 Steam 安装目录。"""
        initial_path = self.save_manager.steam_path or os.path.expanduser("~")
        path = QFileDialog.getExistingDirectory(self, "选择Steam安装目录", initial_path)
        if not path:
            return
        if not SaveManager.is_valid_steam_path(path):
            InfoBar.error(
                title="路径无效",
                content="请选择包含 steam.exe 或 config/loginusers.vdf 的 Steam 安装目录",
                orient=Qt.Horizontal, isClosable=True,
                position=InfoBarPosition.TOP, duration=4000, parent=self)
            return
        self._select_steam_path(path)

    def _auto_detect_steam_path(self):
        """重新扫描注册表和所有盘符，覆盖旧路径。"""
        path = SaveManager.detect_steam_path()
        if not path:
            InfoBar.warning(
                title="未找到 Steam",
                content="请点击“浏览修改”选择 Steam 安装目录",
                orient=Qt.Horizontal, isClosable=True,
                position=InfoBarPosition.TOP, duration=4000, parent=self)
            return
        self._select_steam_path(path)
        InfoBar.success(
            title="检测成功", content=f"Steam安装目录: {path}",
            orient=Qt.Horizontal, isClosable=True,
            position=InfoBarPosition.TOP, duration=3000, parent=self)

    def _update_steam_status_style(self):
        """根据当前主题更新Steam状态标签颜色"""
        self.steam_status_label.setStyleSheet(
            f"color: {'#aaaaaa' if isDarkTheme() else 'gray'};"
        )
