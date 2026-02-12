"""
预设编辑对话框
用于编辑通用预设和专用预设
"""

from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                               QLineEdit, QListWidget, QListWidgetItem, QPushButton,
                               QCheckBox, QMessageBox)
from PySide6.QtCore import Qt, Signal
from qfluentwidgets import (LineEdit, PrimaryPushButton, PushButton,
                           MessageBox, InfoBar, InfoBarPosition)


class PresetEditDialog(QDialog):
    """预设编辑对话框"""

    # 信号
    preset_saved = Signal(str, str, list)  # (preset_id, name, affixes)

    def __init__(self, vocabulary: list, preset_data: dict = None, is_general: bool = False, parent=None):
        """
        初始化对话框

        Args:
            vocabulary: 词条库列表
            preset_data: 预设数据（编辑模式）
            is_general: 是否为通用预设
            parent: 父窗口
        """
        super().__init__(parent)
        self.vocabulary = vocabulary
        self.preset_data = preset_data
        self.is_general = is_general
        self.is_edit_mode = preset_data is not None

        self.setWindowTitle("编辑预设" if self.is_edit_mode else "创建预设")
        self.setMinimumSize(600, 500)

        self._init_ui()
        self._load_preset_data()

    def _init_ui(self):
        """初始化UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        # 预设名称
        if not self.is_general:
            name_layout = QHBoxLayout()
            name_label = QLabel("预设名称:")
            name_label.setFixedWidth(80)
            self.name_input = LineEdit()
            self.name_input.setPlaceholderText("输入预设名称")
            name_layout.addWidget(name_label)
            name_layout.addWidget(self.name_input)
            layout.addLayout(name_layout)
        else:
            # 通用预设显示标题
            title = QLabel("通用预设词条选择")
            title.setStyleSheet("font-size: 16px; font-weight: bold;")
            layout.addWidget(title)

        # 搜索框
        search_layout = QHBoxLayout()
        search_label = QLabel("搜索:")
        search_label.setFixedWidth(80)
        self.search_input = LineEdit()
        self.search_input.setPlaceholderText("输入关键词搜索词条")
        self.search_input.textChanged.connect(self._filter_vocabulary)
        search_layout.addWidget(search_label)
        search_layout.addWidget(self.search_input)
        layout.addLayout(search_layout)

        # 词条列表
        list_label = QLabel(f"词条列表 (共 {len(self.vocabulary)} 条):")
        layout.addWidget(list_label)

        self.vocab_list = QListWidget()
        # === 重新设计的现代化样式表 (使用 Fluent 图标) ===
        self.vocab_list.setStyleSheet("""
            QListWidget {
                border: 1px solid #e0e0e0;
                border-radius: 6px;
                background-color: white;
                outline: none;
                padding: 4px;
            }
            QListWidget::item {
                height: 38px; /* 稍微增加高度让布局更宽松 */
                padding-left: 8px;
                color: #333;
                border-radius: 4px; /* 让选中项有圆角 */
                margin-bottom: 2px;
            }
            QListWidget::item:hover {
                background-color: #f5f5f5;
            }
            QListWidget::item:selected {
                background-color: #e3f2fd; /* 选中时的浅蓝背景 */
                color: #000;
            }

            /* === 复选框指示器样式 === */
            QListWidget::indicator {
                width: 20px;
                height: 20px;
                border-radius: 4px;
                border: 1px solid #c0c0c0; /* 默认浅灰边框 */
                background-color: white;
                margin-right: 12px;
            }

            /* 鼠标悬停 */
            QListWidget::indicator:hover {
                border-color: #009faa;
                background-color: #f0f8ff;
            }

            /* === 关键修改：勾选状态 (Checked) === */
            /* 使用蓝色背景 + 内置的白色对钩图标 */
            QListWidget::indicator:checked {
                background-color: #009faa; /* Fluent 主题蓝 */
                border: 1px solid #009faa;
                /* 引用 QFluentWidgets 库内置的白色对钩资源 */
                image: url(":/qfluentwidgets/images/check_box_checked_white.png");
            }

            /* === 关键修改：选中行时的勾选状态 (Checked + Selected) === */
            /* 保持样式不变，蓝色背景+白勾在浅蓝底色上非常清晰 */
            QListWidget::indicator:checked:selected {
                 background-color: #009faa;
                 border: 1px solid #009faa;
                 image: url(":/qfluentwidgets/images/check_box_checked_white.png");
            }

            /* 未勾选时的选中状态 */
            QListWidget::indicator:unchecked:selected {
                border: 1px solid #009faa;
                background-color: white;
            }
        """)

        # 添加词条到列表
        for vocab in self.vocabulary:
            item = QListWidgetItem(vocab)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Unchecked)
            self.vocab_list.addItem(item)

        layout.addWidget(self.vocab_list)

        # 统计信息
        self.count_label = QLabel("已选择: 0 条")
        self.count_label.setStyleSheet("color: #666; font-size: 12px;")
        layout.addWidget(self.count_label)

        self.vocab_list.itemChanged.connect(self._update_count)
        self.vocab_list.itemChanged.connect(self._sort_items)  # 勾选变化时重新排序

        # 按钮
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        self.cancel_btn = PushButton("取消")
        self.cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(self.cancel_btn)

        self.save_btn = PrimaryPushButton("保存")
        self.save_btn.clicked.connect(self._save_preset)
        button_layout.addWidget(self.save_btn)

        layout.addLayout(button_layout)

    def _load_preset_data(self):
        """加载预设数据（编辑模式）"""
        if not self.preset_data:
            return

        # 设置名称
        if not self.is_general and "name" in self.preset_data:
            self.name_input.setText(self.preset_data["name"])

        # 勾选已有词条
        selected_affixes = set(self.preset_data.get("affixes", []))
        for i in range(self.vocab_list.count()):
            item = self.vocab_list.item(i)
            if item.text() in selected_affixes:
                item.setCheckState(Qt.Checked)

        self._update_count()
        self._sort_items()  # 加载后排序，已勾选的置顶

    def _filter_vocabulary(self, text: str):
        """过滤词条列表"""
        for i in range(self.vocab_list.count()):
            item = self.vocab_list.item(i)
            item.setHidden(text.lower() not in item.text().lower())

    def _update_count(self):
        """更新选择计数"""
        count = sum(1 for i in range(self.vocab_list.count())
                   if self.vocab_list.item(i).checkState() == Qt.Checked)
        self.count_label.setText(f"已选择: {count} 条")

    def _sort_items(self):
        """将已勾选的词条置顶"""
        # 暂时断开信号，避免排序时触发 itemChanged
        self.vocab_list.itemChanged.disconnect(self._update_count)
        self.vocab_list.itemChanged.disconnect(self._sort_items)

        # 收集所有项
        items = []
        for i in range(self.vocab_list.count()):
            item = self.vocab_list.item(i)
            items.append((item.text(), item.checkState()))

        # 排序：已勾选的在前，未勾选的在后，同类按字母排序
        items.sort(key=lambda x: (x[1] != Qt.Checked, x[0]))

        # 清空列表并重新添加
        self.vocab_list.clear()
        for text, check_state in items:
            item = QListWidgetItem(text)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(check_state)
            self.vocab_list.addItem(item)

        # 重新连接信号
        self.vocab_list.itemChanged.connect(self._update_count)
        self.vocab_list.itemChanged.connect(self._sort_items)

    def _save_preset(self):
        """保存预设"""
        # 验证名称（非通用预设）
        if not self.is_general:
            name = self.name_input.text().strip()
            if not name:
                MessageBox("错误", "请输入预设名称", self).exec()
                return
        else:
            name = "通用预设"

        # 获取选中的词条
        selected_affixes = []
        for i in range(self.vocab_list.count()):
            item = self.vocab_list.item(i)
            if item.checkState() == Qt.Checked:
                selected_affixes.append(item.text())

        if not selected_affixes:
            MessageBox("错误", "请至少选择一条词条", self).exec()
            return

        # 发送信号
        preset_id = self.preset_data.get("id", "") if self.preset_data else ""
        self.preset_saved.emit(preset_id, name, selected_affixes)
        self.accept()

    def get_selected_affixes(self) -> list:
        """获取选中的词条"""
        selected = []
        for i in range(self.vocab_list.count()):
            item = self.vocab_list.item(i)
            if item.checkState() == Qt.Checked:
                selected.append(item.text())
        return selected

    def closeEvent(self, event):
        """关闭窗口时自动保存"""
        # 验证名称（非通用预设）
        if not self.is_general:
            name = self.name_input.text().strip()
            if not name:
                # 如果没有名称，询问是否放弃
                reply = MessageBox("提示", "预设名称为空，是否放弃保存？", self)
                if reply.exec():
                    event.accept()
                else:
                    event.ignore()
                return
        else:
            name = "通用预设"

        # 获取选中的词条
        selected_affixes = self.get_selected_affixes()

        if not selected_affixes:
            # 如果没有选择词条，询问是否放弃
            reply = MessageBox("提示", "未选择任何词条，是否放弃保存？", self)
            if reply.exec():
                event.accept()
            else:
                event.ignore()
            return

        # 发送保存信号
        preset_id = self.preset_data.get("id", "") if self.preset_data else ""
        self.preset_saved.emit(preset_id, name, selected_affixes)
        event.accept()