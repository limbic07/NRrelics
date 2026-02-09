"""存档管理页面 - 简洁框架"""

from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel


class SavePage(QWidget):
    """存档管理页面"""

    def __init__(self):
        super().__init__()
        self.setObjectName("SavePage")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 32, 32, 32)

        label = QLabel("存档管理")
        label.setStyleSheet("font-size: 24px; font-weight: bold;")
        layout.addWidget(label)

        layout.addStretch()
