"""中央日志管理器 - 同步两个页面的日志"""

from PySide6.QtCore import QObject, Signal


class LogManager(QObject):
    """中央日志管理器 - 广播日志到所有订阅者"""

    log_signal = Signal(str, str)  # (message, level)

    def __init__(self):
        super().__init__()
        self.subscribers = []

    def subscribe(self, logger_widget):
        """订阅日志"""
        self.subscribers.append(logger_widget)
        self.log_signal.connect(logger_widget.log)

    def log(self, message: str, level: str = "INFO"):
        """发送日志到所有订阅者"""
        self.log_signal.emit(message, level)

    def clear_all(self):
        """清空所有日志"""
        for logger in self.subscribers:
            logger.clear()
