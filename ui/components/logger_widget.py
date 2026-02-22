"""日志面板组件 - 现代扁平化设计"""

from PySide6.QtWidgets import QTextEdit
from PySide6.QtCore import Qt
from qfluentwidgets import isDarkTheme
import html


class LoggerWidget(QTextEdit):
    """日志显示面板 - 现代扁平化设计"""

    def __init__(self):
        super().__init__()
        self.setReadOnly(True)
        self.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)  # 启用自动换行
        self._update_stylesheet()

    def _update_stylesheet(self):
        """根据主题更新样式"""
        if isDarkTheme():
            # 深色模式
            stylesheet = """
                QTextEdit {
                    background-color: #1e1e1e;
                    color: #e0e0e0;
                    border: 1px solid #3d3d3d;
                    border-radius: 8px;
                    padding: 12px;
                    font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
                    font-size: 11pt;
                    line-height: 1.5;
                }
            """
        else:
            # 浅色模式
            stylesheet = """
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
            """
        self.setStyleSheet(stylesheet)

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
        text_color = "#e0e0e0" if isDarkTheme() else "#333333"
        formatted_msg = f'<span style="color: {color}; font-weight: 500;">[{timestamp}]</span> <span style="color: {color};">[{level}]</span> <span style="color: {text_color};">{safe_message}</span>'
        self.append(formatted_msg)

    def _get_timestamp(self) -> str:
        """获取时间戳"""
        from datetime import datetime
        return datetime.now().strftime("%H:%M:%S")

    def clear_log(self):
        """清空日志"""
        self.clear()
