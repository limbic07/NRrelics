"""商店筛选页面 - 简洁框架"""

from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel
from PySide6.QtCore import Qt


class ShopPage(QWidget):
    """商店筛选页面"""

    def __init__(self):
        super().__init__()
        self.setObjectName("ShopPage")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 32, 32, 32)

        label = QLabel("商店筛选")
        label.setStyleSheet("font-size: 24px; font-weight: bold;")
        layout.addWidget(label)

        layout.addStretch()
