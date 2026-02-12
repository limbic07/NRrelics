"""遗物卡片组件 - Fluent Design"""

from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QHBoxLayout, QPushButton
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QColor
from qfluentwidgets import CardWidget


class RelicCard(CardWidget):
    """遗物卡片 - Fluent Design"""

    def __init__(self, name: str = "遗物", quality: str = "普通", count: int = 1):
        super().__init__()
        self.setFixedSize(200, 240)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # 遗物名称
        name_label = QLabel(name)
        name_label.setFont(QFont("Segoe UI", 12, QFont.Bold))
        name_label.setStyleSheet("color: #1a1a1a;")
        name_label.setWordWrap(True)
        layout.addWidget(name_label)

        # 品质标签
        quality_label = QLabel(f"品质: {quality}")
        quality_label.setFont(QFont("Segoe UI", 10))
        quality_color = self._get_quality_color(quality)
        quality_label.setStyleSheet(f"color: {quality_color};")
        layout.addWidget(quality_label)

        # 数量
        count_label = QLabel(f"数量: {count}")
        count_label.setFont(QFont("Segoe UI", 10))
        count_label.setStyleSheet("color: #666666;")
        layout.addWidget(count_label)

        layout.addStretch()

        # 操作按钮
        button_layout = QHBoxLayout()
        button_layout.setSpacing(8)

        delete_btn = QPushButton("删除")
        delete_btn.setFixedHeight(32)
        delete_btn.setStyleSheet("""
            QPushButton {
                background-color: #f3f3f3;
                color: #333333;
                border: none;
                border-radius: 4px;
                font-size: 11px;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: #e8e8e8;
            }
        """)
        button_layout.addWidget(delete_btn)

        layout.addLayout(button_layout)

    @staticmethod
    def _get_quality_color(quality: str) -> str:
        """根据品质返回颜色"""
        quality_colors = {
            "普通": "#666666",
            "稀有": "#0066cc",
            "史诗": "#9933ff",
            "传说": "#ff9900",
        }
        return quality_colors.get(quality, "#666666")
