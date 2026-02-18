"""关于页面"""

from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QFont
from qfluentwidgets import CardWidget


class AboutPage(QWidget):
    """关于页面"""

    # 开发者模式信号
    developer_mode_activated = Signal()

    def __init__(self):
        super().__init__()
        self.setObjectName("AboutPage")
        self.click_count = 0
        self._developer_mode = False

        # 点击超时重置计时器（2秒内未继续点击则重置）
        self._click_timer = QTimer()
        self._click_timer.setSingleShot(True)
        self._click_timer.setInterval(2000)
        self._click_timer.timeout.connect(self._reset_click_count)

        self._init_ui()

    def _init_ui(self):
        """初始化UI"""
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)

        # 可滚动区域
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QScrollArea.NoFrame)
        outer_layout.addWidget(scroll_area)

        scroll_content = QWidget()
        layout = QVBoxLayout(scroll_content)
        layout.setContentsMargins(32, 32, 32, 32)
        layout.setSpacing(16)

        # 标题
        title = QLabel("关于")
        title.setStyleSheet("font-size: 24pt; font-weight: bold;")
        layout.addWidget(title)

        # 应用信息卡片
        info_card = CardWidget()
        info_layout = QVBoxLayout(info_card)
        info_layout.setContentsMargins(24, 20, 24, 20)
        info_layout.setSpacing(8)

        app_name = QLabel("NRrelic Bot")
        app_name.setStyleSheet("font-size: 18pt; font-weight: bold;")
        info_layout.addWidget(app_name)

        desc_text = QLabel("艾尔登法环：黑夜君临 遗物管理工具")
        desc_text.setFont(QFont("Segoe UI", 10))
        desc_text.setStyleSheet("color: #555;")
        info_layout.addWidget(desc_text)

        layout.addWidget(info_card)

        # 版本号卡片（彩蛋入口）
        version_card = CardWidget()
        version_card.setCursor(Qt.PointingHandCursor)
        version_layout = QVBoxLayout(version_card)
        version_layout.setContentsMargins(24, 20, 24, 20)
        version_layout.setSpacing(8)

        version_title = QLabel("版本")
        version_title.setStyleSheet("font-size: 12pt; font-weight: bold;")
        version_layout.addWidget(version_title)

        self.version_label = QLabel("v2.0.0")
        self.version_label.setFont(QFont("Segoe UI", 9))
        self.version_label.setStyleSheet("color: gray;")
        version_layout.addWidget(self.version_label)

        version_card.mousePressEvent = self._on_version_clicked
        layout.addWidget(version_card)

        # GitHub 卡片
        github_card = CardWidget()
        github_layout = QVBoxLayout(github_card)
        github_layout.setContentsMargins(24, 20, 24, 20)
        github_layout.setSpacing(8)

        github_title = QLabel("开源项目")
        github_title.setStyleSheet("font-size: 12pt; font-weight: bold;")
        github_layout.addWidget(github_title)

        github_link = QLabel('<a href="https://github.com/limbic07/NRrelics" style="color: #0066cc;">https://github.com/limbic07/NRrelics</a>')
        github_link.setOpenExternalLinks(True)
        github_link.setFont(QFont("Segoe UI", 9))
        github_layout.addWidget(github_link)

        github_desc = QLabel("欢迎访问GitHub项目页面，提交问题反馈或贡献代码。")
        github_desc.setFont(QFont("Segoe UI", 9))
        github_desc.setStyleSheet("color: gray;")
        github_layout.addWidget(github_desc)

        layout.addWidget(github_card)

        # 免责声明卡片
        disclaimer_card = CardWidget()
        disclaimer_layout = QVBoxLayout(disclaimer_card)
        disclaimer_layout.setContentsMargins(24, 20, 24, 20)
        disclaimer_layout.setSpacing(8)

        disclaimer_title = QLabel("免责声明")
        disclaimer_title.setStyleSheet("font-size: 12pt; font-weight: bold;")
        disclaimer_layout.addWidget(disclaimer_title)

        disclaimer_text = QLabel(
            "本软件仅供学习交流使用，使用本软件产生的任何后果由使用者自行承担。\n\n"
            "• 本软件通过OCR识别和自动化操作辅助游戏，不修改游戏文件\n"
            "• 使用本软件可能违反游戏服务条款，请谨慎使用\n"
            "• 开发者不对使用本软件导致的账号封禁或其他问题负责\n"
        )
        disclaimer_text.setFont(QFont("Segoe UI", 9))
        disclaimer_text.setWordWrap(True)
        disclaimer_text.setStyleSheet("color: #666;")
        disclaimer_layout.addWidget(disclaimer_text)

        layout.addWidget(disclaimer_card)

        layout.addStretch()
        scroll_area.setWidget(scroll_content)

    def _on_version_clicked(self, event):
        """版本号点击事件（彩蛋）"""
        if self._developer_mode:
            return

        self.click_count += 1
        self._click_timer.start()

        if self.click_count >= 5:
            self.click_count = 0
            self._developer_mode = True
            self._click_timer.stop()
            self.developer_mode_activated.emit()

    def _reset_click_count(self):
        """超时重置点击计数"""
        self.click_count = 0
