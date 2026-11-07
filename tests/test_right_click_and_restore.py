import json
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import (QApplication, QListWidget, QListWidgetItem,
                               QTableWidget, QTableWidgetItem, QTreeWidget, QTreeWidgetItem)

from core.preset_manager import PresetManager
from main import RightClickChecks


def test_right_click_toggles_checkable_rows_but_not_disabled_official():
    app = QApplication.instance() or QApplication([])
    guard = RightClickChecks(app)
    app.installEventFilter(guard)
    try:
        widgets = []
        listing = QListWidget()
        entry = QListWidgetItem('智力+1')
        entry.setFlags(entry.flags() | Qt.ItemIsUserCheckable)
        entry.setCheckState(Qt.Unchecked)
        listing.addItem(entry)
        widgets.append((listing, listing.model().index(0, 0), entry))

        tree = QTreeWidget()
        tree.setHeaderHidden(True)
        node = QTreeWidgetItem(['词条'])
        node.setFlags(node.flags() | Qt.ItemIsUserCheckable)
        node.setCheckState(0, Qt.Unchecked)
        tree.addTopLevelItem(node)
        widgets.append((tree, tree.model().index(0, 0), node))

        table = QTableWidget(2, 2)
        editable = QTableWidgetItem('')
        editable.setFlags(Qt.ItemIsEnabled | Qt.ItemIsUserCheckable)
        editable.setCheckState(Qt.Unchecked)
        table.setItem(0, 0, editable)
        table.setItem(0, 1, QTableWidgetItem('普通遗物'))
        official = QTableWidgetItem('')
        official.setFlags(Qt.ItemIsUserCheckable)
        official.setCheckState(Qt.Unchecked)
        table.setItem(1, 0, official)
        table.setItem(1, 1, QTableWidgetItem('官方遗物'))
        widgets.append((table, table.model().index(0, 1), editable))
        widgets.append((table, table.model().index(1, 1), official))

        for widget, index, item in widgets:
            widget.show()
            app.processEvents()
            pos = widget.visualRect(index).center()
            QTest.mouseClick(widget.viewport(), Qt.RightButton, Qt.NoModifier, pos)
            expected = Qt.Unchecked if item is official else Qt.Checked
            state = item.checkState(0) if item is node else item.checkState()
            assert state == expected, (type(widget).__name__, state, expected,
                                       widget.model().flags(index))
            QTest.mouseClick(widget.viewport(), Qt.RightButton, Qt.NoModifier, pos)
            state = item.checkState(0) if item is node else item.checkState()
            assert state == Qt.Unchecked
            widget.close()
    finally:
        app.removeEventFilter(guard)


def test_restore_defaults_replaces_presets_without_creating_backup(tmp_path):
    manager = PresetManager(str(tmp_path))
    original = Path(manager.presets_file)
    manager.normal_general['name'] = '自定义预设'
    manager.save_presets()
    manager.restore_bundled_defaults()
    assert not list(tmp_path.rglob('presets_backup_*.json'))
    assert manager.normal_general['name'] != '自定义预设'
    assert json.loads(original.read_text(encoding='utf-8'))['normal_general'] == manager.normal_general


def test_new_preset_name_uses_selected_character_for_optimizer():
    from ui.dialogs.preset_character_dialog import PresetCharacterDialog, next_preset_title
    from ui.dialogs.preset_edit_dialog import PresetEditDialog

    app = QApplication.instance() or QApplication([])
    chooser = PresetCharacterDialog()
    assert chooser.character_combo.count() == 10
    chooser.character_combo.setCurrentIndex(0)
    assert chooser.selected_character() == '追踪者'
    chooser.close()
    presets = {'first': {'name': '追踪者｜自定义流派 1'}}
    title = next_preset_title('追踪者', presets)
    assert title == '自定义流派 2'
    dialog = PresetEditDialog([], mode='normal', new_character='追踪者',
                              suggested_name=title)
    saved = []
    dialog.graded_saved.connect(lambda _id, name, *_: saved.append(name))
    dialog._save()
    assert saved == ['追踪者｜自定义流派 2']
    assert saved[0].startswith('追踪者｜')
    assert app is not None
