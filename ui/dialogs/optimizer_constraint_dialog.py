"""Choose one OR group of required affixes or official relics."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QLabel, QLineEdit,
                               QTreeWidget, QTreeWidgetItem, QVBoxLayout, QAbstractItemView)
from core.official_relics import load_official_relics


def describe_requirement(entry):
    if entry.get('kind') == 'official':
        return f"官方遗物 #{entry['id']} {entry['label']}"
    return entry['name']


class ConstraintGroupDialog(QDialog):
    def __init__(self, choices, selected=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle('编辑一组必备条件')
        self.resize(740, 560)
        self.setStyleSheet('QDialog { background: #f5f5f5; } QTreeWidget { background: white; border: 1px solid #d8d8d8; border-radius: 8px; padding: 5px; } QTreeWidget::item { min-height: 30px; padding: 4px 8px; } QPushButton { min-height: 30px; }')
        layout=QVBoxLayout(self)
        layout.setContentsMargins(24,20,24,20)
        layout.setSpacing(8)
        layout.addWidget(QLabel('勾选至少一项。本组满足任意一项即可；不同组之间必须全部满足。'))
        self.search=QLineEdit()
        self.search.setPlaceholderText('搜索词条或官方遗物')
        self.search.textChanged.connect(self._filter)
        layout.addWidget(self.search)
        self.list=QTreeWidget()
        self.list.setSelectionMode(QAbstractItemView.NoSelection)
        self.list.setHeaderHidden(True)
        layout.addWidget(self.list)
        layout.addWidget(QLabel('右键条件所在行可勾选或取消勾选；官方遗物的展开词条仅供查看。'))
        selected_keys={self._key(entry) for entry in selected or []}
        catalog={entry['id']:entry for entry in load_official_relics()}
        for choice in choices:
            item=QTreeWidgetItem([describe_requirement(choice)])
            item.setData(0,Qt.UserRole,choice)
            item.setFlags(item.flags()|Qt.ItemIsUserCheckable)
            item.setCheckState(0,Qt.Checked if self._key(choice) in selected_keys else Qt.Unchecked)
            self.list.addTopLevelItem(item)
            if choice.get('kind')=='official':
                for affix in catalog.get(choice['id'],{}).get('affixes',[]):
                    child=QTreeWidgetItem([affix])
                    child.setFlags(Qt.ItemIsEnabled)
                    item.addChild(child)
                item.setExpanded(False)
        buttons=QDialogButtonBox(QDialogButtonBox.Save|QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setText('保存')
        buttons.button(QDialogButtonBox.Cancel).setText('取消')
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    @staticmethod
    def _key(entry):
        return (entry.get('kind'),entry.get('name'),entry.get('id'))

    def _filter(self, *_):
        text=self.search.text().strip().lower()
        for index in range(self.list.topLevelItemCount()):
            item=self.list.topLevelItem(index)
            content=item.text(0)+' '.join(item.child(i).text(0) for i in range(item.childCount()))
            item.setHidden(text not in content.lower())

    def _accept(self):
        if self.selected():
            self.accept()

    def selected(self):
        return [self.list.topLevelItem(index).data(0,Qt.UserRole)
                for index in range(self.list.topLevelItemCount())
                if self.list.topLevelItem(index).checkState(0)==Qt.Checked]
