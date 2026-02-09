"""设置页面 - 简洁框架"""

from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel


class SettingsPage(QWidget):
    """设置页面"""

    def __init__(self):
        super().__init__()
        self.setObjectName("SettingsPage")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 32, 32, 32)

        label = QLabel("设置")
        label.setStyleSheet("font-size: 24px; font-weight: bold;")
        layout.addWidget(label)

        layout.addStretch()
