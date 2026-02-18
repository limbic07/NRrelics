"""日志面板组件 - 现代扁平化设计"""

from PySide6.QtWidgets import QTextEdit
from PySide6.QtCore import Qt
import html


class LoggerWidget(QTextEdit):
    """日志显示面板 - 现代扁平化设计"""

    def __init__(self):
        super().__init__()
        self.setReadOnly(True)
        self.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)  # 启用自动换行
        self.setStyleSheet("""
            QTextEdit {
                background-color: #ffffff;
                color: #333333;
                border: 1px solid #e8e8e8;
                border-radius: 8px;
                padding: 12px;
                font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
                font-size: 11pt;
                line-height: 1.5;
            }
        """)

    def log(self, message: str, level: str = "INFO"):
        """添加日志"""
        color_map = {
            "INFO": "#0066cc",
            "SUCCESS": "#27ae60",
            "WARNING": "#f39c12",
            "ERROR": "#e74c3c",
            "DEBUG": "#95a5a6",
        }
        color = color_map.get(level, "#333333")
        timestamp = self._get_timestamp()

        # 使用 HTML 格式化日志（转义message中的特殊字符防止被当作HTML标签）
        safe_message = html.escape(message)
        formatted_msg = f'<span style="color: {color}; font-weight: 500;">[{timestamp}]</span> <span style="color: {color};">[{level}]</span> <span style="color: #333333;">{safe_message}</span>'
        self.append(formatted_msg)

    def _get_timestamp(self) -> str:
        """获取时间戳"""
        from datetime import datetime
        return datetime.now().strftime("%H:%M:%S")

    def clear_log(self):
        """清空日志"""
        self.clear()
