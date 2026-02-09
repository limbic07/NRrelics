"""仓库清理页面 - 简洁框架"""

from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel


class RepoPage(QWidget):
    """仓库清理页面"""

    def __init__(self):
        super().__init__()
        self.setObjectName("RepoPage")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 32, 32, 32)

        label = QLabel("仓库清理")
        label.setStyleSheet("font-size: 24px; font-weight: bold;")
        layout.addWidget(label)

        layout.addStretch()
