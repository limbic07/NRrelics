"""Mouse wheel scrolls the page without changing selection controls."""
from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QWheelEvent
from PySide6.QtWidgets import QApplication, QComboBox, QLabel, QScrollArea, QSpinBox, QVBoxLayout, QWidget
from qfluentwidgets import ComboBox as FluentComboBox

from main import NoWheelSelectionEdit


def test_wheel_over_combo_and_spin_scrolls_parent_area():
    app = QApplication.instance() or QApplication([])
    guard = NoWheelSelectionEdit(app)
    app.installEventFilter(guard)
    try:
        scroll = QScrollArea()
        content = QWidget()
        layout = QVBoxLayout(content)
        combo = QComboBox()
        combo.addItems(['追踪者', '女爵', '守护者'])
        fluent_combo = FluentComboBox()
        fluent_combo.addItems(['普通遗物', '深夜遗物'])
        spin = QSpinBox()
        spin.setRange(0, 100)
        spin.setValue(75)
        layout.addWidget(combo)
        layout.addWidget(fluent_combo)
        layout.addWidget(spin)
        layout.addWidget(QLabel('页面内容'))
        layout.addStretch()
        content.setMinimumHeight(600)
        scroll.setWidget(content)
        scroll.resize(300, 120)
        scroll.show()
        app.processEvents()

        def wheel(widget):
            center = widget.rect().center()
            event = QWheelEvent(QPointF(center), QPointF(widget.mapToGlobal(center)),
                                QPoint(), QPoint(0, -120), Qt.NoButton,
                                Qt.NoModifier, Qt.NoScrollPhase, False)
            QApplication.sendEvent(widget, event)
            app.processEvents()

        wheel(combo)
        assert combo.currentIndex() == 0
        assert scroll.verticalScrollBar().value() > 0
        before = scroll.verticalScrollBar().value()
        wheel(spin)
        assert spin.value() == 75
        assert scroll.verticalScrollBar().value() > before
        before = scroll.verticalScrollBar().value()
        wheel(fluent_combo)
        assert fluent_combo.currentIndex() == 0
        assert scroll.verticalScrollBar().value() > before
        scroll.close()
    finally:
        app.removeEventFilter(guard)
