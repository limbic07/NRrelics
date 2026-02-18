"""存档管理页面"""

from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                               QLineEdit, QInputDialog, QMessageBox, QScrollArea,
                               QDialog, QDialogButtonBox)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from qfluentwidgets import (CardWidget, ComboBox, PrimaryPushButton, PushButton,
                           InfoBar, InfoBarPosition, LineEdit as FluentLineEdit)
import os
import json

from core.save_manager import SaveManager


class SavePage(QWidget):
    """存档管理页面"""

    def __init__(self):
        super().__init__()
        self.setObjectName("SavePage")

        # 加载设置中的Steam路径
        self.settings_file = "data/settings.json"
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
        layout = QVBoxLayout(self)
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

        # 备份列表卡片
        self.backup_card = self._create_backup_card()
        layout.addWidget(self.backup_card, 1)  # stretch=1 填满剩余空间

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

        # Steam路径提示
        steam_status = "已检测" if self.save_manager.steam_path else "未检测到，请在设置中配置"
        self.steam_status_label = QLabel(f"Steam路径: {self.save_manager.steam_path or steam_status}")
        self.steam_status_label.setFont(QFont("Segoe UI", 8))
        self.steam_status_label.setStyleSheet("color: gray;")
        card_layout.addWidget(self.steam_status_label)

        return card

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
            no_backup_label.setStyleSheet("color: gray;")
            no_backup_label.setAlignment(Qt.AlignCenter)
            self.backup_list_layout.insertWidget(0, no_backup_label)
            return

        for backup in backups:
            row = self._create_backup_row(backup)
            self.backup_list_layout.insertWidget(self.backup_list_layout.count() - 1, row)

    def _create_backup_row(self, backup: dict) -> QWidget:
        """创建备份行"""
        row = QWidget()
        row.setStyleSheet("QWidget { background-color: #f8f8f8; border-radius: 6px; padding: 4px; }")
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(12, 8, 12, 8)
        row_layout.setSpacing(12)

        # 备份名称
        name_label = QLabel(backup["display_name"])
        name_label.setFont(QFont("Segoe UI", 10))
        name_label.setMinimumWidth(150)
        row_layout.addWidget(name_label)

        # 修改时间
        time_label = QLabel(backup["modified_time"])
        time_label.setFont(QFont("Segoe UI", 8))
        time_label.setStyleSheet("color: gray;")
        row_layout.addWidget(time_label)

        # 文件大小
        size_mb = backup["size"] / (1024 * 1024)
        size_label = QLabel(f"{size_mb:.1f} MB")
        size_label.setFont(QFont("Segoe UI", 8))
        size_label.setStyleSheet("color: gray;")
        size_label.setFixedWidth(60)
        row_layout.addWidget(size_label)

        row_layout.addStretch()

        # 操作按钮
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
        self.steam_status_label.setText(f"Steam路径: {self.save_manager.steam_path or '未检测到'}")
        self._refresh_all()
