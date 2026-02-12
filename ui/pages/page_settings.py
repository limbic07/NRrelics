"""设置页面"""

from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                               QLineEdit, QCheckBox, QGroupBox, QPushButton)
from PySide6.QtCore import Signal, Qt
from qfluentwidgets import (CardWidget, SwitchButton, LineEdit,
                           PrimaryPushButton, InfoBar, InfoBarPosition)
import json
import os


class SettingsPage(QWidget):
    """设置页面"""

    # 信号
    settings_changed = Signal(dict)  # 设置变更信号

    def __init__(self):
        super().__init__()
        self.setObjectName("SettingsPage")

        # 设置文件路径
        self.settings_file = "data/settings.json"
        self.settings = self._load_settings()

        self._init_ui()

    def _init_ui(self):
        """初始化UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 32, 32, 32)
        layout.setSpacing(16)

        # 标题
        title = QLabel("设置")
        title.setStyleSheet("font-size: 24px; font-weight: bold;")
        layout.addWidget(title)

        # 通用设置
        general_group = self._create_general_settings()
        layout.addWidget(general_group)

        # 仓库清理设置
        repo_group = self._create_repo_settings()
        layout.addWidget(repo_group)

        # 保存按钮
        save_btn = PrimaryPushButton("保存设置")
        save_btn.clicked.connect(self._save_settings)
        layout.addWidget(save_btn)

        layout.addStretch()

    def _create_general_settings(self) -> CardWidget:
        """创建通用设置组"""
        card = CardWidget()
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(20, 20, 20, 20)
        card_layout.setSpacing(12)

        # 标题
        title = QLabel("通用设置")
        title.setStyleSheet("font-size: 16px; font-weight: bold;")
        card_layout.addWidget(title)

        # 游戏窗口标题
        window_layout = QHBoxLayout()
        window_label = QLabel("游戏窗口标题:")
        window_label.setFixedWidth(150)
        self.window_title_input = LineEdit()
        self.window_title_input.setText(self.settings.get("game_window_title", "ELDEN RING™"))
        self.window_title_input.setPlaceholderText("输入游戏窗口标题")
        window_layout.addWidget(window_label)
        window_layout.addWidget(self.window_title_input)
        card_layout.addLayout(window_layout)

        return card

    def _create_repo_settings(self) -> CardWidget:
        """创建仓库清理设置组"""
        card = CardWidget()
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(20, 20, 20, 20)
        card_layout.setSpacing(12)

        # 标题
        title = QLabel("仓库清理设置")
        title.setStyleSheet("font-size: 16px; font-weight: bold;")
        card_layout.addWidget(title)

        # 是否允许对被收藏遗物操作
        favorited_layout = QHBoxLayout()
        favorited_label = QLabel("允许操作被收藏遗物:")
        favorited_label.setFixedWidth(150)
        self.allow_favorited_switch = SwitchButton()
        self.allow_favorited_switch.setChecked(self.settings.get("allow_operate_favorited", False))
        favorited_layout.addWidget(favorited_label)
        favorited_layout.addWidget(self.allow_favorited_switch)
        favorited_layout.addStretch()
        card_layout.addLayout(favorited_layout)

        # 双有效/三有效模式
        valid_layout = QHBoxLayout()
        valid_label = QLabel("双有效模式:")
        valid_label.setFixedWidth(150)
        self.require_double_switch = SwitchButton()
        self.require_double_switch.setChecked(self.settings.get("require_double_valid", True))
        valid_layout.addWidget(valid_label)
        valid_layout.addWidget(self.require_double_switch)
        valid_layout.addStretch()

        # 说明文本
        valid_desc = QLabel("开启: 2条词条匹配即合格 | 关闭: 3条词条匹配才合格")
        valid_desc.setStyleSheet("color: gray; font-size: 12px;")
        card_layout.addLayout(valid_layout)
        card_layout.addWidget(valid_desc)

        return card

    def _load_settings(self) -> dict:
        """加载设置"""
        if not os.path.exists(self.settings_file):
            return self._default_settings()

        try:
            with open(self.settings_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"[错误] 加载设置失败: {e}")
            return self._default_settings()

    def _default_settings(self) -> dict:
        """默认设置"""
        return {
            "game_window_title": "ELDEN RING™",
            "allow_operate_favorited": False,
            "require_double_valid": True
        }

    def _save_settings(self):
        """保存设置"""
        self.settings = {
            "game_window_title": self.window_title_input.text(),
            "allow_operate_favorited": self.allow_favorited_switch.isChecked(),
            "require_double_valid": self.require_double_switch.isChecked()
        }

        try:
            os.makedirs(os.path.dirname(self.settings_file), exist_ok=True)
            with open(self.settings_file, 'w', encoding='utf-8') as f:
                json.dump(self.settings, f, ensure_ascii=False, indent=2)

            InfoBar.success(
                title="保存成功",
                content="设置已保存",
                orient=Qt.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=2000,
                parent=self
            )

            # 发送设置变更信号
            self.settings_changed.emit(self.settings)

        except Exception as e:
            InfoBar.error(
                title="保存失败",
                content=f"保存设置失败: {e}",
                orient=Qt.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=self
            )

    def get_settings(self) -> dict:
        """获取当前设置"""
        return self.settings

