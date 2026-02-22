"""
预设编辑对话框
用于编辑通用预设和专用预设
"""

from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                               QLineEdit, QListWidget, QListWidgetItem, QPushButton,
                               QCheckBox, QMessageBox)
from PySide6.QtCore import Qt, Signal
from qfluentwidgets import (LineEdit, PrimaryPushButton, PushButton,
                           MessageBox, InfoBar, InfoBarPosition, isDarkTheme)


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
            title.setStyleSheet("font-size: 16pt; font-weight: bold;")
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

        # 批量操作按钮
        batch_layout = QHBoxLayout()
        batch_layout.addWidget(QLabel("批量操作:"))

        self.select_all_btn = PushButton("全选")
        self.select_all_btn.setFixedWidth(80)
        self.select_all_btn.setToolTip("选择所有可见词条（受搜索过滤影响）")
        self.select_all_btn.clicked.connect(self._select_all)
        batch_layout.addWidget(self.select_all_btn)

        self.deselect_all_btn = PushButton("全不选")
        self.deselect_all_btn.setFixedWidth(80)
        self.deselect_all_btn.setToolTip("取消选择所有可见词条（受搜索过滤影响）")
        self.deselect_all_btn.clicked.connect(self._deselect_all)
        batch_layout.addWidget(self.deselect_all_btn)

        self.invert_selection_btn = PushButton("反选")
        self.invert_selection_btn.setFixedWidth(80)
        self.invert_selection_btn.setToolTip("反选所有可见词条（受搜索过滤影响）")
        self.invert_selection_btn.clicked.connect(self._invert_selection)
        batch_layout.addWidget(self.invert_selection_btn)

        batch_layout.addStretch()
        layout.addLayout(batch_layout)

        # 词条列表
        list_label = QLabel(f"词条列表 (共 {len(self.vocabulary)} 条):")
        layout.addWidget(list_label)

        self.vocab_list = QListWidget()
        self._apply_list_stylesheet()

        # 添加词条到列表
        for vocab in self.vocabulary:
            item = QListWidgetItem(vocab)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Unchecked)
            self.vocab_list.addItem(item)

        layout.addWidget(self.vocab_list)

        # 统计信息
        self.count_label = QLabel("已选择: 0 条")
        self.count_label.setStyleSheet("color: #666; font-size: 12pt;")
        layout.addWidget(self.count_label)

        # 只连接更新计数，不连接排序（排序只在加载时执行一次）
        self.vocab_list.itemChanged.connect(self._update_count)

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

    def _apply_list_stylesheet(self):
        """根据主题应用列表样式"""
        if isDarkTheme():
            # 深色模式
            stylesheet = """
                QListWidget {
                    border: 1px solid #3d3d3d;
                    border-radius: 6px;
                    background-color: #1e1e1e;
                    outline: none;
                    padding: 4px;
                }
                QListWidget::item {
                    height: 38px;
                    padding-left: 8px;
                    color: #e0e0e0;
                    border-radius: 4px;
                    margin-bottom: 2px;
                }
                QListWidget::item:hover {
                    background-color: #2d2d2d;
                }
                QListWidget::item:selected {
                    background-color: #1a3a52;
                    color: #e0e0e0;
                }
                QListWidget::indicator {
                    width: 20px;
                    height: 20px;
                    border-radius: 4px;
                    border: 1px solid #555555;
                    background-color: #2d2d2d;
                    margin-right: 12px;
                }
                QListWidget::indicator:hover {
                    border-color: #009faa;
                    background-color: #3d3d3d;
                }
                QListWidget::indicator:checked {
                    background-color: #009faa;
                    border: 1px solid #009faa;
                    image: url(":/qfluentwidgets/images/check_box_checked_white.png");
                }
                QListWidget::indicator:checked:selected {
                    background-color: #009faa;
                    border: 1px solid #009faa;
                    image: url(":/qfluentwidgets/images/check_box_checked_white.png");
                }
                QListWidget::indicator:unchecked:selected {
                    border: 1px solid #009faa;
                    background-color: #2d2d2d;
                }
            """
        else:
            # 浅色模式
            stylesheet = """
                QListWidget {
                    border: 1px solid #e0e0e0;
                    border-radius: 6px;
                    background-color: white;
                    outline: none;
                    padding: 4px;
                }
                QListWidget::item {
                    height: 38px;
                    padding-left: 8px;
                    color: #333;
                    border-radius: 4px;
                    margin-bottom: 2px;
                }
                QListWidget::item:hover {
                    background-color: #f5f5f5;
                }
                QListWidget::item:selected {
                    background-color: #e3f2fd;
                    color: #000;
                }
                QListWidget::indicator {
                    width: 20px;
                    height: 20px;
                    border-radius: 4px;
                    border: 1px solid #c0c0c0;
                    background-color: white;
                    margin-right: 12px;
                }
                QListWidget::indicator:hover {
                    border-color: #009faa;
                    background-color: #f0f8ff;
                }
                QListWidget::indicator:checked {
                    background-color: #009faa;
                    border: 1px solid #009faa;
                    image: url(":/qfluentwidgets/images/check_box_checked_white.png");
                }
                QListWidget::indicator:checked:selected {
                    background-color: #009faa;
                    border: 1px solid #009faa;
                    image: url(":/qfluentwidgets/images/check_box_checked_white.png");
                }
                QListWidget::indicator:unchecked:selected {
                    border: 1px solid #009faa;
                    background-color: white;
                }
            """
        self.vocab_list.setStyleSheet(stylesheet)

    def _load_preset_data(self):
        """加载预设数据（编辑模式）"""
        if not self.preset_data:
            return

        # 设置名称
        if not self.is_general and "name" in self.preset_data:
            self.name_input.setText(self.preset_data["name"])

        # 暂时断开信号，避免加载时触发排序
        self.vocab_list.itemChanged.disconnect(self._update_count)

        # 勾选已有词条
        selected_affixes = set(self.preset_data.get("affixes", []))
        for i in range(self.vocab_list.count()):
            item = self.vocab_list.item(i)
            if item.text() in selected_affixes:
                item.setCheckState(Qt.Checked)

        # 重新连接信号
        self.vocab_list.itemChanged.connect(self._update_count)

        # 更新计数和排序（只在加载时执行一次）
        self._update_count()
        self._sort_items()

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

    def _select_all(self):
        """全选所有可见词条"""
        self.vocab_list.itemChanged.disconnect(self._update_count)

        for i in range(self.vocab_list.count()):
            item = self.vocab_list.item(i)
            # 只选择可见的词条
            if not item.isHidden():
                item.setCheckState(Qt.Checked)

        self.vocab_list.itemChanged.connect(self._update_count)
        self._update_count()

    def _deselect_all(self):
        """取消全选所有可见词条"""
        self.vocab_list.itemChanged.disconnect(self._update_count)

        for i in range(self.vocab_list.count()):
            item = self.vocab_list.item(i)
            # 只取消选择可见的词条
            if not item.isHidden():
                item.setCheckState(Qt.Unchecked)

        self.vocab_list.itemChanged.connect(self._update_count)
        self._update_count()

    def _invert_selection(self):
        """反选所有可见词条"""
        self.vocab_list.itemChanged.disconnect(self._update_count)

        for i in range(self.vocab_list.count()):
            item = self.vocab_list.item(i)
            # 只反选可见的词条
            if not item.isHidden():
                if item.checkState() == Qt.Checked:
                    item.setCheckState(Qt.Unchecked)
                else:
                    item.setCheckState(Qt.Checked)

        self.vocab_list.itemChanged.connect(self._update_count)
        self._update_count()

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

        # 获取选中的词条（允许为空）
        selected_affixes = []
        for i in range(self.vocab_list.count()):
            item = self.vocab_list.item(i)
            if item.checkState() == Qt.Checked:
                selected_affixes.append(item.text())

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