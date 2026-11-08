"""
NRrelic Bot v2 - 主程序入口
 - 异步初始化 OCR (使用 QThread)
"""

import sys
import json
from pathlib import Path

from PySide6.QtWidgets import (QApplication, QAbstractItemView, QAbstractScrollArea,
                               QAbstractSpinBox, QComboBox, QTableWidget)
from PySide6.QtCore import Signal, QObject, QThread, QEvent, Qt
from PySide6.QtGui import QFont, QWheelEvent
from qfluentwidgets import ComboBox as FluentComboBox
from ui import MainWindow
from ui.dialogs.welcome_dialog import WelcomeDialog
from core.utils import get_user_data_path



class NoWheelSelectionEdit(QObject):
    """Keep the wheel for page scrolling, never for changing compact controls."""

    def eventFilter(self, watched, event):
        if event.type() != QEvent.Wheel:
            return False
        widget = watched
        while widget is not None:
            if isinstance(widget, (QAbstractSpinBox, QComboBox, FluentComboBox)):
                parent = widget.parentWidget()
                while parent is not None and not isinstance(parent, QAbstractScrollArea):
                    parent = parent.parentWidget()
                if parent is not None:
                    viewport = parent.viewport()
                    forwarded = QWheelEvent(
                        viewport.mapFromGlobal(event.globalPosition().toPoint()),
                        event.globalPosition(), event.pixelDelta(), event.angleDelta(),
                        event.buttons(), event.modifiers(), event.phase(), event.inverted(),
                        event.source())
                    QApplication.sendEvent(viewport, forwarded)
                return True
            widget = widget.parentWidget() if hasattr(widget, 'parentWidget') else None
        return False


class RightClickChecks(QObject):
    """Toggle a checkable list row by right-clicking anywhere on that row."""

    def eventFilter(self, watched, event):
        if event.type() not in (QEvent.MouseButtonPress, QEvent.MouseButtonRelease, QEvent.ContextMenu):
            return False
        view = watched.parentWidget() if hasattr(watched, 'parentWidget') else None
        if not isinstance(view, QAbstractItemView) or watched is not view.viewport():
            return False
        if event.type() == QEvent.ContextMenu:
            return True
        if event.button() != Qt.RightButton:
            return False
        if event.type() == QEvent.MouseButtonPress:
            return True
        index = view.indexAt(event.position().toPoint())
        if not index.isValid():
            return False
        if isinstance(view, QTableWidget):
            index = index.siblingAtColumn(0)
        flags = view.model().flags(index)
        if not (flags & Qt.ItemIsEnabled and flags & Qt.ItemIsUserCheckable):
            return False
        old = index.data(Qt.CheckStateRole)
        old_value = old.value if isinstance(old, Qt.CheckState) else old
        new_value = (Qt.Unchecked if old_value == Qt.Checked.value else Qt.Checked).value
        view.model().setData(index, new_value,
                             Qt.CheckStateRole)
        return True


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
        self.no_wheel_selection_edit = NoWheelSelectionEdit(self.app)
        self.app.installEventFilter(self.no_wheel_selection_edit)
        self.right_click_checks = RightClickChecks(self.app)
        self.app.installEventFilter(self.right_click_checks)

        # 设置默认字体，避免Qt尝试加载不存在的MS Sans Serif
        default_font = QFont("Segoe UI", 9)
        self.app.setFont(default_font)

        # 设置字体替换，防止Qt尝试使用MS Sans Serif
        QFont.insertSubstitution("MS Sans Serif", "Segoe UI")
        QFont.insertSubstitution("MS Shell Dlg", "Segoe UI")
        QFont.insertSubstitution("MS Shell Dlg 2", "Segoe UI")
        QFont.insertSubstitution("System", "Segoe UI")
        QFont.insertSubstitution("Default", "Segoe UI")

        # 设置全局样式表，为所有使用font-weight的元素指定font-family和font-size
        self.app.setStyleSheet("""
            * {
                font-family: "Segoe UI", "Microsoft YaHei UI", sans-serif;
                font-size: 9pt;
            }
        """)

        self.window = None
        self.ocr_engine = None
        self.ocr_thread = None
        self.ocr_worker = None

    def _load_config(self) -> dict:
        """加载配置"""
        config_path = Path(get_user_data_path("data/settings.json"))
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
        # 词条库已在 initialize() 中加载，无需重复加载
        if self.ocr_engine:
            # 将引擎传递到 UI 层
            self.window.init_ocr_dependencies(self.ocr_engine)

    def _on_ocr_error(self, _error_msg: str):
        """OCR 初始化失败"""
        pass

    def _show_welcome_if_needed(self):
        """首次启动时显示使用须知"""
        settings_path = Path(get_user_data_path("data/settings.json"))
        try:
            if settings_path.exists():

                with open(settings_path, 'r', encoding='utf-8') as f:
                    settings = json.load(f)
                if settings.get("welcome_shown", False):
                    return
        except Exception:
            pass

        dlg = WelcomeDialog(self.window)
        dlg.exec()

        if dlg.should_hide_forever():
            try:
                if settings_path.exists():
                    with open(settings_path, 'r', encoding='utf-8') as f:
                        settings = json.load(f)
                else:
                    settings = {}
                settings["welcome_shown"] = True
                with open(settings_path, 'w', encoding='utf-8') as f:
                    json.dump(settings, f, ensure_ascii=False, indent=2)
            except Exception:
                pass

    def run(self):
        """运行应用"""
        self.initialize()
        self.window.show()
        self._show_welcome_if_needed()
        return self.app.exec()


def main():
    """主函数"""
    app = Application()
    sys.exit(app.run())


if __name__ == "__main__":
    main()

