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
                "仓库清理建议将游戏「显示设置」中的亮度调为 5。启动时会读取最新存档检查亮度，读取失败时提示手动确认。"
            ),
            (
                "2. 分辨率要求",
                "商店筛选和仓库清理仅支持游戏实际画面为 16:9；建议使用 1920x1080 或 1280x720 窗口化。"
            ),
            (
                "3. 多显示器",
                "游戏可以放在副屏；启动前请确保游戏窗口可见，且实际画面保持 16:9。"
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
            b.setStyleSheet("color: palette(text);")
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
