"""设置页面"""

from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                               QLineEdit, QCheckBox, QGroupBox, QPushButton, QFileDialog,
                               QScrollArea)
from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import QFont
from qfluentwidgets import (CardWidget, SwitchButton, LineEdit,
                           PrimaryPushButton, PushButton, InfoBar, InfoBarPosition)
import json
import os
import shutil
from datetime import datetime
from core.utils import get_user_data_path



class SettingsPage(QWidget):
    """设置页面"""

    # 信号
    settings_changed = Signal(dict)  # 设置变更信号
    steam_path_changed = Signal(str)  # Steam路径变更信号

    def __init__(self):
        super().__init__()
        self.setObjectName("SettingsPage")

        # 设置文件路径
        self.settings_file = get_user_data_path("data/settings.json")
        self.settings = self._load_settings()

        self._init_ui()


    def _init_ui(self):
        """初始化UI"""
        # 外层布局
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)

        # 可滚动区域
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QScrollArea.NoFrame)
        outer_layout.addWidget(scroll_area)

        # 滚动内容容器
        scroll_content = QWidget()
        layout = QVBoxLayout(scroll_content)
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

        # 商店筛选设置
        shop_group = self._create_shop_settings()
        layout.addWidget(shop_group)

        layout.addWidget(self._create_validation_settings())

        # 开发者设置默认显示
        self.developer_card = self._create_developer_settings()
        layout.addWidget(self.developer_card)

        layout.addStretch()
        scroll_area.setWidget(scroll_content)

    def _create_validation_settings(self) -> CardWidget:
        card = CardWidget()
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(20, 20, 20, 20)
        card_layout.setSpacing(12)
        title = QLabel("遗物规则检查")
        title.setStyleSheet("font-size: 16pt; font-weight: bold;")
        card_layout.addWidget(title)
        row = QHBoxLayout()
        label = QLabel("检查 ID 一致性:")
        label.setFixedWidth(150)
        self.check_relic_id_switch = SwitchButton()
        self.check_relic_id_switch.setChecked(self.settings.get("check_relic_id_consistency", False))
        self.check_relic_id_switch.checkedChanged.connect(self._auto_save_settings)
        row.addWidget(label)
        row.addWidget(self.check_relic_id_switch)
        row.addStretch()
        card_layout.addLayout(row)
        description = QLabel(
            "开启后，额外检查存档中的遗物 ID 所规定的正负词条数量和生成模板是否与实际词条对应。"
            "关闭时按遗物类型、颜色、大小和词条组合判断是否合法。下次存档检查生效。")
        description.setFont(QFont("Segoe UI", 8))
        description.setStyleSheet("color: gray;")
        description.setWordWrap(True)
        card_layout.addWidget(description)
        return card

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

        # Steam安装目录
        steam_layout = QHBoxLayout()
        steam_label = QLabel("Steam安装目录:")
        steam_label.setFixedWidth(150)
        self.steam_path_input = LineEdit()
        self.steam_path_input.setText(self.settings.get("steam_path", ""))
        self.steam_path_input.setPlaceholderText("留空自动检测 Steam 安装目录")
        self.steam_path_input.textChanged.connect(self._auto_save_settings)
        steam_layout.addWidget(steam_label)
        steam_layout.addWidget(self.steam_path_input)

        self.steam_browse_btn = PushButton("浏览")
        self.steam_browse_btn.setFixedWidth(80)
        self.steam_browse_btn.clicked.connect(self._browse_steam_path)
        steam_layout.addWidget(self.steam_browse_btn)
        card_layout.addLayout(steam_layout)

        steam_desc = QLabel("用于读取Steam用户信息；留空时从注册表和各磁盘自动检测")
        steam_desc.setFont(QFont("Segoe UI", 8))
        steam_desc.setStyleSheet("color: gray;")
        card_layout.addWidget(steam_desc)

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

    def _create_shop_settings(self) -> CardWidget:
        """创建商店筛选设置组"""
        card = CardWidget()
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(20, 20, 20, 20)
        card_layout.setSpacing(12)

        # 标题
        title = QLabel("商店筛选设置")
        title.setStyleSheet("font-size: 16pt; font-weight: bold;")
        card_layout.addWidget(title)

        # 三有效模式
        shop_valid_layout = QHBoxLayout()
        shop_valid_label = QLabel("三有效模式:")
        shop_valid_label.setFixedWidth(150)
        self.shop_require_double_switch = SwitchButton()
        self.shop_require_double_switch.setChecked(not self.settings.get("shop_require_double_valid", True))
        self.shop_require_double_switch.checkedChanged.connect(self._auto_save_settings)
        shop_valid_layout.addWidget(shop_valid_label)
        shop_valid_layout.addWidget(self.shop_require_double_switch)
        shop_valid_layout.addStretch()

        # 说明文本
        shop_valid_desc = QLabel("开启: 3条词条匹配才合格 | 关闭: 2条词条匹配即合格")
        shop_valid_desc.setFont(QFont("Segoe UI", 8))
        shop_valid_desc.setStyleSheet("color: gray;")
        card_layout.addLayout(shop_valid_layout)
        card_layout.addWidget(shop_valid_desc)

        perfect_layout = QHBoxLayout()
        perfect_layout.addWidget(QLabel("发现完美遗物时停止"))
        self.shop_stop_on_perfect_switch = SwitchButton()
        self.shop_stop_on_perfect_switch.setChecked(self.settings.get("shop_stop_on_perfect_relic", False))
        self.shop_stop_on_perfect_switch.checkedChanged.connect(self._auto_save_settings)
        perfect_layout.addWidget(self.shop_stop_on_perfect_switch)
        perfect_layout.addStretch()
        card_layout.addLayout(perfect_layout)
        perfect_desc = QLabel("专用预设匹配至少3条有效词条且识别结果无不确定项时，保留当前遗物并停止购买")
        perfect_desc.setFont(QFont("Segoe UI", 8))
        perfect_desc.setStyleSheet("color: gray;")
        perfect_desc.setWordWrap(True)
        card_layout.addWidget(perfect_desc)

        # 根据合格遗物数量停止（SL模式）
        sl_mode_layout = QHBoxLayout()
        sl_mode_label = QLabel("根据合格遗物数量停止:")
        sl_mode_label.setFixedWidth(180)
        self.sl_mode_switch = SwitchButton()
        self.sl_mode_switch.setChecked(self.settings.get("sl_mode_enabled", False))
        self.sl_mode_switch.checkedChanged.connect(self._auto_save_settings)
        sl_mode_layout.addWidget(sl_mode_label)
        sl_mode_layout.addWidget(self.sl_mode_switch)
        sl_mode_layout.addStretch()
        card_layout.addLayout(sl_mode_layout)

        sl_mode_desc = QLabel("开启后商店筛选的「停止暗痕」将替换为「停止合格遗物数量」，\n"
                             "暗痕不足时自动退出到标题画面恢复存档继续购买，直到达到目标数量")
        sl_mode_desc.setFont(QFont("Segoe UI", 8))
        sl_mode_desc.setStyleSheet("color: gray;")
        sl_mode_desc.setWordWrap(True)
        card_layout.addWidget(sl_mode_desc)

        return card

    def _create_developer_settings(self) -> CardWidget:
        """创建开发者设置组"""
        card = CardWidget()
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(20, 20, 20, 20)
        card_layout.setSpacing(12)

        # 标题
        title = QLabel("🔧 开发者设置")
        title.setStyleSheet("font-size: 16pt; font-weight: bold;")
        card_layout.addWidget(title)

        hint = QLabel("以下为高级选项，修改前请确保了解其作用")
        hint.setFont(QFont("Segoe UI", 8))
        hint.setStyleSheet("color: #e67e22;")
        card_layout.addWidget(hint)

        debug_title = QLabel("运行调试")
        debug_title.setStyleSheet("font-size: 11pt; font-weight: 600;")
        card_layout.addWidget(debug_title)

        # OCR 调试模式
        ocr_debug_layout = QHBoxLayout()
        ocr_debug_label = QLabel("OCR调试模式:")
        ocr_debug_label.setFixedWidth(150)
        self.ocr_debug_switch = SwitchButton()
        self.ocr_debug_switch.setChecked(self.settings.get("ocr_debug", False))
        self.ocr_debug_switch.checkedChanged.connect(self._auto_save_settings)
        ocr_debug_layout.addWidget(ocr_debug_label)
        ocr_debug_layout.addWidget(self.ocr_debug_switch)
        ocr_debug_layout.addStretch()
        card_layout.addLayout(ocr_debug_layout)

        ocr_debug_desc = QLabel(
            "开启后，仓库清理与商店购买在执行词条OCR时保存完整窗口及六行截图、原始识别、"
            "纠错调用与阈值、词条库候选和最终预设匹配结果；识别失败也会记录，未进入OCR的遗物不会记录。"
            "默认保存到debug_ocr/collections，每次启动清理或购买时单独建目录。"
            "若设置NRRELIC_OCR_DIAGNOSTICS=1，关闭本开关仍会采集。")
        ocr_debug_desc.setFont(QFont("Segoe UI", 8))
        ocr_debug_desc.setStyleSheet("color: gray;")
        ocr_debug_desc.setWordWrap(True)
        card_layout.addWidget(ocr_debug_desc)

        # 商店耗时调试模式：与 OCR 采集开关集中管理，彼此独立。
        timing_debug_layout = QHBoxLayout()
        timing_debug_label = QLabel("耗时调试模式:")
        timing_debug_label.setFixedWidth(150)
        self.timing_debug_switch = SwitchButton()
        self.timing_debug_switch.setChecked(self.settings.get("timing_debug", False))
        self.timing_debug_switch.checkedChanged.connect(self._auto_save_settings)
        timing_debug_layout.addWidget(timing_debug_label)
        timing_debug_layout.addWidget(self.timing_debug_switch)
        timing_debug_layout.addStretch()
        card_layout.addLayout(timing_debug_layout)

        timing_debug_desc = QLabel(
            "开启后，商店筛选每轮十连输出一次各步骤耗时汇总；中途停止时输出已执行部分。"
            "包含购买、截图、OCR、匹配、调试采集、结果处理、筛选按键和确认；与 OCR 调试模式独立。")
        timing_debug_desc.setFont(QFont("Segoe UI", 8))
        timing_debug_desc.setStyleSheet("color: gray;")
        timing_debug_desc.setWordWrap(True)
        card_layout.addWidget(timing_debug_desc)

        # 模板匹配阈值
        threshold_layout = QHBoxLayout()
        threshold_label = QLabel("模板匹配阈值:")
        threshold_label.setFixedWidth(150)
        self.threshold_input = LineEdit()
        self.threshold_input.setText(str(self.settings.get("template_threshold", 0.7)))
        self.threshold_input.setFixedWidth(80)
        self.threshold_input.textChanged.connect(self._auto_save_settings)
        threshold_layout.addWidget(threshold_label)
        threshold_layout.addWidget(self.threshold_input)
        threshold_layout.addStretch()
        card_layout.addLayout(threshold_layout)

        threshold_desc = QLabel("商店模板匹配的置信度阈值（0.0-1.0），默认0.7")
        threshold_desc.setFont(QFont("Segoe UI", 8))
        threshold_desc.setStyleSheet("color: gray;")
        card_layout.addWidget(threshold_desc)

        # 亮度阈值（遗物状态检测）
        lum_layout = QHBoxLayout()
        lum_label = QLabel("亮度阈值:")
        lum_label.setFixedWidth(150)
        self.lum_threshold_input = LineEdit()
        self.lum_threshold_input.setText(str(self.settings.get("brightness_threshold", 45)))
        self.lum_threshold_input.setFixedWidth(80)
        self.lum_threshold_input.textChanged.connect(self._auto_save_settings)
        lum_layout.addWidget(lum_label)
        lum_layout.addWidget(self.lum_threshold_input)
        lum_layout.addStretch()
        card_layout.addLayout(lum_layout)

        lum_desc = QLabel("遗物亮/暗状态判断的亮度阈值（0-255），默认45")
        lum_desc.setFont(QFont("Segoe UI", 8))
        lum_desc.setStyleSheet("color: gray;")
        card_layout.addWidget(lum_desc)

        return card

    def _export_presets(self):
        """导出预设配置文件"""
        presets_file = get_user_data_path("data/presets.json")

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
        presets_file = get_user_data_path("data/presets.json")

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

            # 发送预设变更信号，让主窗口通知页面刷新
            main_window = self.window()
            if hasattr(main_window, 'preset_manager'):
                main_window.preset_manager.load_presets()
                if hasattr(main_window, '_on_presets_changed'):
                    main_window._on_presets_changed()

            InfoBar.success(
                title="导入成功",
                content=f"预设配置已导入并生效",
                orient=Qt.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
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
                settings.pop("stop_on_perfect_relic", None)
                settings["developer_mode"] = True  # 兼容旧版隐藏开发者设置的配置
                return settings
        except Exception as e:
            print(f"[错误] 加载设置失败: {e}")
            return self._default_settings()

    def _default_settings(self) -> dict:
        """默认设置"""
        return {
            "allow_operate_favorited": False,
            "require_double_valid": True,
            "shop_require_double_valid": True,
            "shop_stop_on_perfect_relic": False,
            "steam_path": "",
            "ocr_debug": False,
            "timing_debug": False,
            "check_relic_id_consistency": False,
            "template_threshold": 0.7,
            "brightness_threshold": 45,
            "sl_mode_enabled": False,
            "developer_mode": True
        }

    def _auto_save_settings(self):
        """自动保存设置"""
        old_steam_path = self.settings.get("steam_path", "")

        self.settings = {
            **self.settings,
            "check_relic_id_consistency": self.check_relic_id_switch.isChecked() if hasattr(self, 'check_relic_id_switch') else self.settings.get("check_relic_id_consistency", False),
            "allow_operate_favorited": self.allow_favorited_switch.isChecked(),
            "require_double_valid": not self.require_double_switch.isChecked(),
            "shop_require_double_valid": not self.shop_require_double_switch.isChecked(),
            "shop_stop_on_perfect_relic": self.shop_stop_on_perfect_switch.isChecked(),
            "steam_path": self.steam_path_input.text(),
            "ocr_debug": self.ocr_debug_switch.isChecked() if hasattr(self, 'ocr_debug_switch') else self.settings.get("ocr_debug", False),
            "timing_debug": self.timing_debug_switch.isChecked() if hasattr(self, 'timing_debug_switch') else self.settings.get("timing_debug", False),
            "template_threshold": self._get_threshold_value(),
            "brightness_threshold": self._get_brightness_threshold_value(),
            "sl_mode_enabled": self.sl_mode_switch.isChecked() if hasattr(self, 'sl_mode_switch') else self.settings.get("sl_mode_enabled", False),
            "developer_mode": True
        }

        try:
            os.makedirs(os.path.dirname(self.settings_file), exist_ok=True)
            with open(self.settings_file, 'w', encoding='utf-8') as f:
                json.dump(self.settings, f, ensure_ascii=False, indent=2)

            # 发送设置变更信号
            self.settings_changed.emit(self.settings)

            # Steam路径变更时发送专用信号
            new_steam_path = self.settings.get("steam_path", "")
            if new_steam_path != old_steam_path:
                self.steam_path_changed.emit(new_steam_path)

        except Exception as e:
            print(f"[错误] 自动保存设置失败: {e}")

    def _get_threshold_value(self) -> float:
        """安全获取模板匹配阈值"""
        if not hasattr(self, 'threshold_input'):
            return self.settings.get("template_threshold", 0.7)
        try:
            val = float(self.threshold_input.text())
            return max(0.0, min(1.0, val))
        except (ValueError, TypeError):
            return 0.7

    def _get_brightness_threshold_value(self) -> int:
        """安全获取亮度阈值"""
        if not hasattr(self, 'lum_threshold_input'):
            return self.settings.get("brightness_threshold", 45)
        try:
            val = int(self.lum_threshold_input.text())
            return max(0, min(255, val))
        except (ValueError, TypeError):
            return 45

    def _save_settings(self):
        """保存设置"""
        self.settings = {
            "game_window_title": self.window_title_input.text(),
            "allow_operate_favorited": self.allow_favorited_switch.isChecked(),
            "require_double_valid": not self.require_double_switch.isChecked(),
            "steam_path": self.steam_path_input.text()
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

    def set_steam_path(self, steam_path: str):
        """接收存档页选择的路径，并沿用现有设置保存与通知流程。"""
        if self.steam_path_input.text() != steam_path:
            self.steam_path_input.setText(steam_path)

    def _browse_steam_path(self):
        """浏览选择Steam安装目录"""
        dir_path = QFileDialog.getExistingDirectory(
            self, "选择Steam安装目录",
            self.steam_path_input.text() or os.path.expanduser("~")
        )
        if dir_path:
            self.steam_path_input.setText(dir_path)

