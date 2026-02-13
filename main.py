"""
NRrelic Bot v2.0.0 - 主程序入口
简洁框架 - 异步初始化 OCR (使用 QThread)
"""

import sys
import json
from pathlib import Path

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Signal, QObject, QThread
from PySide6.QtGui import QFont
from ui import MainWindow


class OCRWorker(QObject):
    """OCR 工作线程"""
    finished = Signal()
    error = Signal(str)

    def __init__(self):
        super().__init__()
        self.ocr_engine = None

    def initialize(self):
        """初始化 OCR"""
        try:
            from core import OCREngine
            self.ocr_engine = OCREngine()
            self.finished.emit()
        except Exception as e:
            self.error.emit(str(e))


class Application:
    """应用程序主类"""

    def __init__(self):
        self.config = self._load_config()
        self.app = QApplication(sys.argv)

        # 设置默认字体，避免Qt尝试加载不存在的MS Sans Serif
        default_font = QFont("Segoe UI", 9)
        self.app.setFont(default_font)

        # 设置字体替换，防止Qt尝试使用MS Sans Serif
        QFont.insertSubstitution("MS Sans Serif", "Segoe UI")
        QFont.insertSubstitution("MS Shell Dlg", "Segoe UI")
        QFont.insertSubstitution("MS Shell Dlg 2", "Segoe UI")

        # 设置全局样式表，为所有使用font-weight的元素指定font-family
        self.app.setStyleSheet("""
            * {
                font-family: "Segoe UI", "Microsoft YaHei UI", sans-serif;
            }
        """)

        self.window = None
        self.ocr_engine = None
        self.ocr_thread = None
        self.ocr_worker = None

    def _load_config(self) -> dict:
        """加载配置"""
        config_path = Path("config/settings.json")
        if config_path.exists():
            with open(config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}

    def initialize(self):
        """初始化应用"""
        # 创建主窗口
        self.window = MainWindow()

        # 后台初始化 OCR (使用 QThread)
        self._init_ocr_qthread()

    def _init_ocr_qthread(self):
        """使用 QThread 异步初始化 OCR"""
        # 创建工作线程
        self.ocr_thread = QThread()
        self.ocr_worker = OCRWorker()

        # 将 worker 移到线程
        self.ocr_worker.moveToThread(self.ocr_thread)

        # 连接信号
        self.ocr_thread.started.connect(self.ocr_worker.initialize)
        self.ocr_worker.finished.connect(self._on_ocr_initialized)
        self.ocr_worker.error.connect(self._on_ocr_error)
        self.ocr_worker.finished.connect(self.ocr_thread.quit)
        self.ocr_worker.error.connect(self.ocr_thread.quit)
        self.ocr_thread.finished.connect(self.ocr_thread.deleteLater)

        # 启动线程
        self.ocr_thread.start()



    def _on_ocr_initialized(self):
        """OCR 初始化完成"""
        self.ocr_engine = self.ocr_worker.ocr_engine
        relic_type = self.config.get("ocr", {}).get("relic_type", "normal")
        if self.ocr_engine:
            self.ocr_engine.load_vocabulary(relic_type)
            # 将引擎传递到 UI 层
            self.window.init_ocr_dependencies(self.ocr_engine)

    def _on_ocr_error(self, _error_msg: str):
        """OCR 初始化失败"""
        pass

    def run(self):
        """运行应用"""
        self.initialize()
        self.window.show()
        return self.app.exec()


def main():
    """主函数"""
    app = Application()
    sys.exit(app.run())


if __name__ == "__main__":
    main()

