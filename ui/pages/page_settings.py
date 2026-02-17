"""设置页面"""

from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                               QLineEdit, QCheckBox, QGroupBox, QPushButton, QFileDialog)
from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import QFont
from qfluentwidgets import (CardWidget, SwitchButton, LineEdit,
                           PrimaryPushButton, PushButton, InfoBar, InfoBarPosition)
import json
import os
import shutil
from datetime import datetime


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
        title.setStyleSheet("font-size: 24pt; font-weight: bold;")
        layout.addWidget(title)

        # 通用设置
        general_group = self._create_general_settings()
        layout.addWidget(general_group)

        # 仓库清理设置
        repo_group = self._create_repo_settings()
        layout.addWidget(repo_group)

        layout.addStretch()

    def _create_general_settings(self) -> CardWidget:
        """创建通用设置组"""
        card = CardWidget()
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(20, 20, 20, 20)
        card_layout.setSpacing(12)

        # 标题
        title = QLabel("通用设置")
        title.setStyleSheet("font-size: 16pt; font-weight: bold;")
        card_layout.addWidget(title)

        # 游戏窗口标题
        window_layout = QHBoxLayout()
        window_label = QLabel("游戏窗口标题:")
        window_label.setFixedWidth(150)
        self.window_title_input = LineEdit()
        self.window_title_input.setText(self.settings.get("game_window_title", "NIGHTREIGN"))
        self.window_title_input.setPlaceholderText("输入游戏窗口标题")
        self.window_title_input.textChanged.connect(self._auto_save_settings)
        window_layout.addWidget(window_label)
        window_layout.addWidget(self.window_title_input)
        card_layout.addLayout(window_layout)

        # 预设配置管理
        preset_layout = QHBoxLayout()
        preset_label = QLabel("预设配置管理:")
        preset_label.setFixedWidth(150)
        self.export_btn = PushButton("导出预设")
        self.export_btn.setFixedWidth(120)
        self.export_btn.clicked.connect(self._export_presets)
        self.import_btn = PushButton("导入预设")
        self.import_btn.setFixedWidth(120)
        self.import_btn.clicked.connect(self._import_presets)
        preset_layout.addWidget(preset_label)
        preset_layout.addWidget(self.export_btn)
        preset_layout.addWidget(self.import_btn)
        preset_layout.addStretch()
        card_layout.addLayout(preset_layout)

        # 说明文本
        preset_desc = QLabel("导出/导入所有预设配置（导入会覆盖当前配置）")
        preset_desc.setFont(QFont("Segoe UI", 8))
        preset_desc.setStyleSheet("color: gray;")
        card_layout.addWidget(preset_desc)

        return card

    def _create_repo_settings(self) -> CardWidget:
        """创建仓库清理设置组"""
        card = CardWidget()
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(20, 20, 20, 20)
        card_layout.setSpacing(12)

        # 标题
        title = QLabel("仓库清理设置")
        title.setStyleSheet("font-size: 16pt; font-weight: bold;")
        card_layout.addWidget(title)

        # 是否允许对被收藏遗物操作
        favorited_layout = QHBoxLayout()
        favorited_label = QLabel("允许操作被收藏遗物:")
        favorited_label.setFixedWidth(150)
        self.allow_favorited_switch = SwitchButton()
        self.allow_favorited_switch.setChecked(self.settings.get("allow_operate_favorited", False))
        self.allow_favorited_switch.checkedChanged.connect(self._auto_save_settings)
        favorited_layout.addWidget(favorited_label)
        favorited_layout.addWidget(self.allow_favorited_switch)
        favorited_layout.addStretch()
        card_layout.addLayout(favorited_layout)

        # 三有效模式
        valid_layout = QHBoxLayout()
        valid_label = QLabel("三有效模式:")
        valid_label.setFixedWidth(150)
        self.require_double_switch = SwitchButton()
        self.require_double_switch.setChecked(not self.settings.get("require_double_valid", True))
        self.require_double_switch.checkedChanged.connect(self._auto_save_settings)
        valid_layout.addWidget(valid_label)
        valid_layout.addWidget(self.require_double_switch)
        valid_layout.addStretch()

        # 说明文本
        valid_desc = QLabel("开启: 3条词条匹配才合格 | 关闭: 2条词条匹配即合格")
        valid_desc.setFont(QFont("Segoe UI", 8))
        valid_desc.setStyleSheet("color: gray;")
        card_layout.addLayout(valid_layout)
        card_layout.addWidget(valid_desc)

        return card

    def _export_presets(self):
        """导出预设配置文件"""
        presets_file = "data/presets.json"

        # 检查预设文件是否存在
        if not os.path.exists(presets_file):
            InfoBar.error(
                title="导出失败",
                content="预设配置文件不存在",
                orient=Qt.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=self
            )
            return

        # 生成默认文件名（带时间戳）
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        default_filename = f"presets_backup_{timestamp}.json"

        # 打开文件保存对话框
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "导出预设配置",
            default_filename,
            "JSON Files (*.json);;All Files (*)"
        )

        if not file_path:
            return  # 用户取消

        try:
            # 复制预设文件到目标位置
            shutil.copy2(presets_file, file_path)

            InfoBar.success(
                title="导出成功",
                content=f"预设配置已导出到: {os.path.basename(file_path)}",
                orient=Qt.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=self
            )

        except Exception as e:
            InfoBar.error(
                title="导出失败",
                content=f"导出预设配置失败: {e}",
                orient=Qt.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=self
            )

    def _import_presets(self):
        """导入预设配置文件"""
        presets_file = "data/presets.json"

        # 打开文件选择对话框
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "导入预设配置",
            "",
            "JSON Files (*.json);;All Files (*)"
        )

        if not file_path:
            return  # 用户取消

        try:
            # 读取并验证导入的文件
            with open(file_path, 'r', encoding='utf-8') as f:
                imported_data = json.load(f)

            # 验证必要的字段
            required_fields = ["version", "normal_general", "deepnight_general",
                             "normal_dedicated", "deepnight_whitelist_dedicated",
                             "deepnight_blacklist"]

            missing_fields = [field for field in required_fields if field not in imported_data]
            if missing_fields:
                InfoBar.error(
                    title="导入失败",
                    content=f"配置文件格式不正确，缺少字段: {', '.join(missing_fields)}",
                    orient=Qt.Horizontal,
                    isClosable=True,
                    position=InfoBarPosition.TOP,
                    duration=3000,
                    parent=self
                )
                return

            # 备份当前配置
            if os.path.exists(presets_file):
                backup_file = f"{presets_file}.backup"
                shutil.copy2(presets_file, backup_file)

            # 写入新配置
            os.makedirs(os.path.dirname(presets_file), exist_ok=True)
            with open(presets_file, 'w', encoding='utf-8') as f:
                json.dump(imported_data, f, ensure_ascii=False, indent=2)

            InfoBar.success(
                title="导入成功",
                content=f"预设配置已导入，请重启应用以生效",
                orient=Qt.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=5000,
                parent=self
            )

        except json.JSONDecodeError as e:
            InfoBar.error(
                title="导入失败",
                content=f"配置文件格式错误: {e}",
                orient=Qt.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=self
            )
        except Exception as e:
            InfoBar.error(
                title="导入失败",
                content=f"导入预设配置失败: {e}",
                orient=Qt.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=self
            )

    def _load_settings(self) -> dict:
        """加载设置"""
        if not os.path.exists(self.settings_file):
            # 首次启动，使用默认设置
            default_settings = self._default_settings()

            # 保存默认设置
            try:
                os.makedirs(os.path.dirname(self.settings_file), exist_ok=True)
                with open(self.settings_file, 'w', encoding='utf-8') as f:
                    json.dump(default_settings, f, ensure_ascii=False, indent=2)
                print(f"[信息] 首次启动，创建默认设置")
            except Exception as e:
                print(f"[错误] 保存默认设置失败: {e}")

            return default_settings

        try:
            with open(self.settings_file, 'r', encoding='utf-8') as f:
                settings = json.load(f)
                return settings
        except Exception as e:
            print(f"[错误] 加载设置失败: {e}")
            return self._default_settings()

    def _default_settings(self) -> dict:
        """默认设置"""
        return {
            "game_window_title": "NIGHTREIGN",
            "allow_operate_favorited": False,
            "require_double_valid": True
        }

    def _auto_save_settings(self):
        """自动保存设置"""
        self.settings = {
            "game_window_title": self.window_title_input.text(),
            "allow_operate_favorited": self.allow_favorited_switch.isChecked(),
            "require_double_valid": not self.require_double_switch.isChecked()
        }

        try:
            os.makedirs(os.path.dirname(self.settings_file), exist_ok=True)
            with open(self.settings_file, 'w', encoding='utf-8') as f:
                json.dump(self.settings, f, ensure_ascii=False, indent=2)

            # 发送设置变更信号
            self.settings_changed.emit(self.settings)

        except Exception as e:
            print(f"[错误] 自动保存设置失败: {e}")

    def _save_settings(self):
        """保存设置"""
        self.settings = {
            "game_window_title": self.window_title_input.text(),
            "allow_operate_favorited": self.allow_favorited_switch.isChecked(),
            "require_double_valid": not self.require_double_switch.isChecked()
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

