"""仓库清理页面 - 完整实现"""

from pathlib import Path
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea, QFrame,
    QPushButton, QListWidget, QListWidgetItem, QTabWidget, QSplitter
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from ui.components.logger_widget import LoggerWidget


class PresetPanel(QFrame):
    """词条预设面板"""

    def __init__(self, title: str, items: list, parent=None):
        super().__init__(parent)
        self.title = title
        self.items = items
        self.selected_items = set()
        self.init_ui()

    def init_ui(self):
        """初始化UI"""
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        # 标题
        title_label = QLabel(self.title)
        title_font = QFont()
        title_font.setPointSize(11)
        title_font.setBold(True)
        title_label.setFont(title_font)
        title_label.setStyleSheet("color: #333333;")
        layout.addWidget(title_label)

        # 词条列表
        self.list_widget = QListWidget()
        self.list_widget.setStyleSheet("""
            QListWidget {
                border: 1px solid #e8e8e8;
                border-radius: 6px;
                background-color: #ffffff;
                outline: none;
            }
            QListWidget::item {
                padding: 8px 12px;
                border-bottom: 1px solid #f0f0f0;
                color: #333333;
            }
            QListWidget::item:hover {
                background-color: #f5f5f5;
            }
            QListWidget::item:selected {
                background-color: #e3f2fd;
                color: #1976d2;
            }
        """)

        for item in self.items:
            list_item = QListWidgetItem(item)
            list_item.setFlags(list_item.flags() | Qt.ItemIsUserCheckable)
            list_item.setCheckState(Qt.Unchecked)
            self.list_widget.addItem(list_item)

        self.list_widget.itemChanged.connect(self.on_item_changed)
        layout.addWidget(self.list_widget)

        # 统计信息
        self.count_label = QLabel("已选择: 0 项")
        count_font = QFont()
        count_font.setPointSize(10)
        self.count_label.setFont(count_font)
        self.count_label.setStyleSheet("color: #666666;")
        layout.addWidget(self.count_label)

        self.setLayout(layout)
        self.setStyleSheet("""
            QFrame {
                border: 1px solid #e8e8e8;
                border-radius: 8px;
                background-color: #ffffff;
                padding: 16px;
            }
        """)

    def on_item_changed(self, item):
        """项目改变时更新选择"""
        if item.checkState() == Qt.Checked:
            self.selected_items.add(item.text())
        else:
            self.selected_items.discard(item.text())

        self.count_label.setText(f"已选择: {len(self.selected_items)} 项")

    def get_selected(self):
        """获取选中的项目"""
        return list(self.selected_items)


class RepoPage(QWidget):
    """仓库清理页面"""

    # 信号
    start_cleaning = Signal(str, list)  # mode, selected_items
    stop_cleaning = Signal()

    def __init__(self):
        super().__init__()
        self.setObjectName("RepoPage")

        # 加载词条数据
        self.normal_items = self.load_items("data/normal.txt")
        self.deepnight_pos_items = self.load_items("data/deepnight_pos.txt")
        self.deepnight_neg_items = self.load_items("data/deepnight_neg.txt")

        self.current_mode = "normal"
        self.is_running = False

        self.init_ui()

    def load_items(self, filepath: str) -> list:
        """加载词条文件"""
        try:
            full_path = Path(__file__).parent.parent.parent / filepath
            if full_path.exists():
                with open(full_path, 'r', encoding='utf-8') as f:
                    items = [line.strip() for line in f if line.strip()]
                    return items
        except Exception as e:
            print(f"加载文件失败: {e}")
        return []

    def init_ui(self):
        """初始化主界面"""
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(24, 24, 24, 24)
        main_layout.setSpacing(20)

        # 左侧：模式选择和预设
        left_layout = QVBoxLayout()
        left_layout.setSpacing(16)

        # 模式选择框
        mode_frame = QFrame()
        mode_frame.setStyleSheet("""
            QFrame {
                border: 1px solid #e8e8e8;
                border-radius: 8px;
                background-color: #ffffff;
                padding: 16px;
            }
        """)
        mode_layout = QHBoxLayout(mode_frame)
        mode_layout.setContentsMargins(0, 0, 0, 0)
        mode_layout.setSpacing(12)

        mode_label = QLabel("筛选模式:")
        mode_font = QFont()
        mode_font.setPointSize(11)
        mode_font.setBold(True)
        mode_label.setFont(mode_font)
        mode_label.setStyleSheet("color: #333333;")
        mode_layout.addWidget(mode_label)

        self.normal_btn = QPushButton("普通模式")
        self.normal_btn.setCheckable(True)
        self.normal_btn.setChecked(True)
        self.normal_btn.setMinimumHeight(36)
        self.normal_btn.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 8px 20px;
                font-weight: bold;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
            QPushButton:pressed {
                background-color: #3d8b40;
            }
            QPushButton:!checked {
                background-color: #e8e8e8;
                color: #666666;
            }
        """)
        self.normal_btn.clicked.connect(self.switch_to_normal_mode)
        mode_layout.addWidget(self.normal_btn)

        self.deepnight_btn = QPushButton("深夜模式")
        self.deepnight_btn.setCheckable(True)
        self.deepnight_btn.setMinimumHeight(36)
        self.deepnight_btn.setStyleSheet("""
            QPushButton {
                background-color: #9C27B0;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 8px 20px;
                font-weight: bold;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #8B1FA0;
            }
            QPushButton:pressed {
                background-color: #7B1890;
            }
            QPushButton:!checked {
                background-color: #e8e8e8;
                color: #666666;
            }
        """)
        self.deepnight_btn.clicked.connect(self.switch_to_deepnight_mode)
        mode_layout.addWidget(self.deepnight_btn)

        mode_layout.addStretch()
        left_layout.addWidget(mode_frame)

        # 预设面板容器
        self.preset_container = QWidget()
        self.preset_layout = QVBoxLayout(self.preset_container)
        self.preset_layout.setContentsMargins(0, 0, 0, 0)
        self.preset_layout.setSpacing(16)

        # 初始化普通模式预设
        self.normal_preset = PresetPanel("正面词条预设", self.normal_items)
        self.preset_layout.addWidget(self.normal_preset)

        # 深夜模式预设（初始隐藏）
        self.deepnight_pos_preset = PresetPanel("正面词条预设", self.deepnight_pos_items)
        self.deepnight_neg_preset = PresetPanel("负面词条预设（黑名单）", self.deepnight_neg_items)

        scroll_area = QScrollArea()
        scroll_area.setWidget(self.preset_container)
        scroll_area.setWidgetResizable(True)
        scroll_area.setStyleSheet("""
            QScrollArea {
                border: none;
                background-color: transparent;
            }
            QScrollBar:vertical {
                border: none;
                background-color: #f5f5f5;
                width: 8px;
                border-radius: 4px;
            }
            QScrollBar::handle:vertical {
                background-color: #cccccc;
                border-radius: 4px;
            }
            QScrollBar::handle:vertical:hover {
                background-color: #999999;
            }
        """)
        left_layout.addWidget(scroll_area, 1)

        # 右侧：日志和仪表盘
        right_layout = QVBoxLayout()
        right_layout.setSpacing(16)

        # 标签页
        self.tab_widget = QTabWidget()
        self.tab_widget.setStyleSheet("""
            QTabWidget::pane {
                border: 1px solid #e8e8e8;
                border-radius: 8px;
            }
            QTabBar::tab {
                background-color: #f5f5f5;
                padding: 10px 20px;
                margin-right: 2px;
                border: none;
                color: #666666;
            }
            QTabBar::tab:selected {
                background-color: white;
                color: #333333;
                border-bottom: 3px solid #4CAF50;
            }
        """)

        # 日志标签页
        log_widget = QWidget()
        log_layout = QVBoxLayout(log_widget)
        log_layout.setContentsMargins(0, 0, 0, 0)
        log_layout.setSpacing(12)

        log_label = QLabel("执行日志")
        log_font = QFont()
        log_font.setPointSize(11)
        log_font.setBold(True)
        log_label.setFont(log_font)
        log_label.setStyleSheet("color: #333333;")
        log_layout.addWidget(log_label)

        self.logger = LoggerWidget()
        log_layout.addWidget(self.logger)

        # 仪表盘标签页
        dashboard_widget = QWidget()
        dashboard_layout = QVBoxLayout(dashboard_widget)
        dashboard_layout.setContentsMargins(0, 0, 0, 0)
        dashboard_layout.setSpacing(12)

        dashboard_label = QLabel("仪表盘")
        dashboard_font = QFont()
        dashboard_font.setPointSize(11)
        dashboard_font.setBold(True)
        dashboard_label.setFont(dashboard_font)
        dashboard_label.setStyleSheet("color: #333333;")
        dashboard_layout.addWidget(dashboard_label)

        # 统计信息框
        stats_frame = QFrame()
        stats_frame.setStyleSheet("""
            QFrame {
                border: 1px solid #e8e8e8;
                border-radius: 8px;
                background-color: #ffffff;
                padding: 16px;
            }
        """)
        stats_layout = QVBoxLayout(stats_frame)
        stats_layout.setContentsMargins(0, 0, 0, 0)
        stats_layout.setSpacing(16)

        self.stats_labels = {}
        stats_items = [
            ("当前识别", "recognized_count", "#1976d2"),
            ("已售出", "sold_count", "#4CAF50"),
            ("已收藏", "collected_count", "#FF9800"),
            ("处理中", "processing_count", "#f44336"),
        ]

        for label_text, key, color in stats_items:
            item_layout = QHBoxLayout()
            label = QLabel(f"{label_text}:")
            label.setFont(QFont("Arial", 10, QFont.Bold))
            label.setStyleSheet("color: #666666;")
            value = QLabel("0")
            value.setFont(QFont("Arial", 16, QFont.Bold))
            value.setStyleSheet(f"color: {color};")
            item_layout.addWidget(label)
            item_layout.addWidget(value)
            item_layout.addStretch()
            stats_layout.addLayout(item_layout)
            self.stats_labels[key] = value

        dashboard_layout.addWidget(stats_frame)
        dashboard_layout.addStretch()

        self.tab_widget.addTab(log_widget, "执行日志")
        self.tab_widget.addTab(dashboard_widget, "仪表盘")
        right_layout.addWidget(self.tab_widget, 1)

        # 控制按钮
        button_layout = QHBoxLayout()
        button_layout.setSpacing(12)
        button_layout.addStretch()

        self.start_btn = QPushButton("开始")
        self.start_btn.setMinimumHeight(40)
        self.start_btn.setMinimumWidth(100)
        self.start_btn.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 10px 30px;
                font-weight: bold;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
            QPushButton:pressed {
                background-color: #3d8b40;
            }
            QPushButton:disabled {
                background-color: #cccccc;
                color: #999999;
            }
        """)
        self.start_btn.clicked.connect(self.start_cleaning_handler)
        button_layout.addWidget(self.start_btn)

        self.stop_btn = QPushButton("停止")
        self.stop_btn.setEnabled(False)
        self.stop_btn.setMinimumHeight(40)
        self.stop_btn.setMinimumWidth(100)
        self.stop_btn.setStyleSheet("""
            QPushButton {
                background-color: #f44336;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 10px 30px;
                font-weight: bold;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #da190b;
            }
            QPushButton:pressed {
                background-color: #ba0000;
            }
            QPushButton:disabled {
                background-color: #cccccc;
                color: #999999;
            }
        """)
        self.stop_btn.clicked.connect(self.stop_cleaning_handler)
        button_layout.addWidget(self.stop_btn)

        right_layout.addLayout(button_layout)

        # 组合左右布局
        splitter = QSplitter(Qt.Horizontal)
        splitter.setStyleSheet("""
            QSplitter::handle {
                background-color: #e8e8e8;
                width: 1px;
            }
        """)

        left_widget = QWidget()
        left_widget.setLayout(left_layout)
        splitter.addWidget(left_widget)

        right_widget = QWidget()
        right_widget.setLayout(right_layout)
        splitter.addWidget(right_widget)

        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)

        main_layout.addWidget(splitter)

        self.setStyleSheet("""
            QWidget {
                background-color: #f9f9f9;
            }
        """)

    def switch_to_normal_mode(self):
        """切换到普通模式"""
        if self.is_running:
            self.logger.log("清理进行中，无法切换模式", "WARNING")
            return

        self.current_mode = "normal"
        self.normal_btn.setChecked(True)
        self.deepnight_btn.setChecked(False)

        # 清空预设容器
        while self.preset_layout.count():
            widget = self.preset_layout.takeAt(0).widget()
            if widget:
                widget.deleteLater()

        # 添加普通模式预设
        self.preset_layout.addWidget(self.normal_preset)
        self.preset_layout.addStretch()

        self.logger.log("已切换到普通模式", "INFO")

    def switch_to_deepnight_mode(self):
        """切换到深夜模式"""
        if self.is_running:
            self.logger.log("清理进行中，无法切换模式", "WARNING")
            return

        self.current_mode = "deepnight"
        self.normal_btn.setChecked(False)
        self.deepnight_btn.setChecked(True)

        # 清空预设容器
        while self.preset_layout.count():
            widget = self.preset_layout.takeAt(0).widget()
            if widget:
                widget.deleteLater()

        # 添加深夜模式预设
        self.preset_layout.addWidget(self.deepnight_pos_preset)
        self.preset_layout.addWidget(self.deepnight_neg_preset)
        self.preset_layout.addStretch()

        self.logger.log("已切换到深夜模式", "INFO")

    def start_cleaning_handler(self):
        """开始清理处理"""
        if self.current_mode == "normal":
            selected = self.normal_preset.get_selected()
        else:
            selected_pos = self.deepnight_pos_preset.get_selected()
            selected_neg = self.deepnight_neg_preset.get_selected()
            selected = selected_pos + selected_neg

        if not selected:
            self.logger.log("请先选择词条", "WARNING")
            return

        self.is_running = True
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.normal_btn.setEnabled(False)
        self.deepnight_btn.setEnabled(False)

        self.logger.log(f"开始清理 ({self.current_mode}模式)", "INFO")
        self.logger.log(f"已选择 {len(selected)} 项词条", "INFO")

        # 发送信号启动清理
        self.start_cleaning.emit(self.current_mode, selected)

    def stop_cleaning_handler(self):
        """停止清理处理"""
        self.is_running = False
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.normal_btn.setEnabled(True)
        self.deepnight_btn.setEnabled(True)

        self.logger.log("已停止清理", "WARNING")

        # 发送信号停止清理
        self.stop_cleaning.emit()

    def update_stats(self, key: str, value: int):
        """更新统计信息"""
        if key in self.stats_labels:
            self.stats_labels[key].setText(str(value))
