"""Compact editor for whole-relic scores in normal presets."""

from PySide6.QtWidgets import (QCheckBox, QDialog, QDialogButtonBox, QHBoxLayout,
                               QLabel, QLineEdit, QSpinBox, QTreeWidget,
                               QTreeWidgetItem, QVBoxLayout)

from core.official_relics import load_official_relics


class OfficialRelicScoreDialog(QDialog):
    def __init__(self, scores=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle('官方遗物分数')
        self.resize(860, 650)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel('每件遗物单独计分；未指定时按该预设的有效词条计分。点击遗物可展开固定词条。'))
        search_row = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText('搜索遗物名称或词条')
        self.search.textChanged.connect(self._filter)
        self.only_scored = QCheckBox('仅看已设置')
        self.only_scored.toggled.connect(self._filter)
        search_row.addWidget(self.search)
        search_row.addWidget(self.only_scored)
        layout.addLayout(search_row)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(['官方遗物（点击展开词条）', '颜色', '分数'])
        self.tree.setColumnWidth(0, 650)
        self.tree.setColumnWidth(1, 60)
        layout.addWidget(self.tree)
        self.entries = []
        scores = scores or {}
        for relic in load_official_relics():
            item = QTreeWidgetItem([f"#{relic['id']}  {relic['name']}", relic['color'], ''])
            self.tree.addTopLevelItem(item)
            for affix in relic['affixes']:
                QTreeWidgetItem(item, [affix, '', ''])
            item.setExpanded(False)
            spin = QSpinBox()
            spin.setRange(-1, 999)
            spin.setSpecialValueText('未指定')
            spin.setValue(scores.get(str(relic['id']), -1))
            spin.valueChanged.connect(self._filter)
            self.tree.setItemWidget(item, 2, spin)
            self.entries.append((relic, item, spin))
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _filter(self, *_):
        query = self.search.text().strip().lower()
        for relic, item, spin in self.entries:
            text = relic['name'] + ' ' + ' '.join(relic['affixes'])
            item.setHidden((query not in text.lower()) or
                           (self.only_scored.isChecked() and spin.value() < 0))

    def scores(self):
        return {str(relic['id']): spin.value() for relic, _, spin in self.entries
                if spin.value() >= 0}
