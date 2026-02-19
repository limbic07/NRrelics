"""
使用须知对话框
首次启动时显示
"""

from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QCheckBox
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from qfluentwidgets import PrimaryPushButton, CardWidget


class WelcomeDialog(QDialog):
    """使用须知对话框（首次启动显示）"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("使用须知")
        self.setFixedWidth(520)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)

        # 标题
        title = QLabel("使用须知")
        title.setFont(QFont("Segoe UI", 22, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-size: 22pt; font-weight: bold;")
        layout.addWidget(title)

        # 须知条目
        notices = [
            (
                "1. 游戏亮度设置",
                "请将游戏「显示设置」中的亮度调为 6，否则仓库清理功能中遗物状态检测（亮/暗）可能会出错。"
            ),
            (
                "2. 分辨率要求",
                "本程序支持多分辨率及各种显示模式（窗口化、全屏等），但分辨率过低时遗物词条的 OCR 识别准确率会下降。"
            ),
            (
                "3. 非 16:9 屏幕",
                "若您的显示器非 16:9 比例，请将游戏显示模式调为「窗口化」或「全屏拉伸（无黑边）」，否则坐标缩放可能不准确。"
            ),
        ]

        for title_text, body_text in notices:
            card = CardWidget()
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(14, 10, 14, 10)
            card_layout.setSpacing(4)

            t = QLabel(title_text)
            t.setFont(QFont("Segoe UI", 10, QFont.Bold))
            t.setStyleSheet("font-size: 10pt; font-weight: bold;")
            card_layout.addWidget(t)

            b = QLabel(body_text)
            b.setFont(QFont("Segoe UI", 9))
            b.setWordWrap(True)
            b.setStyleSheet("color: #555;")
            card_layout.addWidget(b)

            layout.addWidget(card)

        layout.addSpacing(4)

        # 底部：不再提示 + 确认按钮
        bottom = QHBoxLayout()
        self.no_more_check = QCheckBox("不再提示")
        self.no_more_check.setFont(QFont("Segoe UI", 9))
        bottom.addWidget(self.no_more_check)
        bottom.addStretch()

        ok_btn = PrimaryPushButton("我知道了")
        ok_btn.setFixedWidth(100)
        ok_btn.clicked.connect(self.accept)
        bottom.addWidget(ok_btn)

        layout.addLayout(bottom)

    def should_hide_forever(self) -> bool:
        """用户是否勾选了「不再提示」"""
        return self.no_more_check.isChecked()
