"""Choose one OR group of required affixes or official relics."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QLabel, QLineEdit,
                               QTreeWidget, QTreeWidgetItem, QVBoxLayout, QAbstractItemView,
                               QHBoxLayout, QTextBrowser, QMessageBox)
from html import escape
from qfluentwidgets import PushButton, PrimaryPushButton
from core.official_relics import load_official_relics


def describe_requirement(entry):
    if entry.get('kind') == 'official':
        return f"官方遗物 #{entry['id']} {entry['label']}"
    return entry['name']


class ConstraintGroupDialog(QDialog):
    suppress_duplicate_hint = False

    def __init__(self, choices, selected=None, parent=None, other_groups=None):
        super().__init__(parent)
        self.other_groups = other_groups or []
        self.setWindowTitle('编辑一组必备条件')
        self.resize(740, 560)
        self.setStyleSheet('QDialog { background: palette(window); } QTreeWidget { background: palette(base); border: 1px solid palette(mid); border-radius: 8px; padding: 5px; } QTreeWidget::item { min-height: 30px; padding: 4px 8px; } QPushButton { min-height: 30px; }')
        layout=QVBoxLayout(self)
        layout.setContentsMargins(24,20,24,20)
        layout.setSpacing(8)
        add_rule_help(layout, self)
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
        self.list.itemChanged.connect(self._warn_duplicate)
        buttons=QDialogButtonBox(QDialogButtonBox.Save|QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setText('保存')
        buttons.button(QDialogButtonBox.Cancel).setText('取消')
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _warn_duplicate(self, item, column):
        if item.checkState(0) != Qt.Checked:
            return
        if ConstraintGroupDialog.suppress_duplicate_hint:
            return
        entry = item.data(0, Qt.UserRole)
        if not entry:
            return
        owners = [str(index) for index, group in self.other_groups
                  if any(self._key(x) == self._key(entry) for x in group)]
        if not owners:
            return
        noun = '遗物' if entry.get('kind') == 'official' else '词条'
        box = QMessageBox(self)
        box.setWindowTitle('重复条件提示')
        box.setText(f'“{describe_requirement(entry)}”也在条件 {"、".join(owners)} 中。')
        box.setInformativeText(f'{noun}重复出现会提高对其数量的需求。')
        close = box.addButton('知道了', QMessageBox.AcceptRole)
        never = box.addButton('本次运行不再提示', QMessageBox.ActionRole)
        box.setDefaultButton(close)
        box.exec()
        if box.clickedButton() == never:
            ConstraintGroupDialog.suppress_duplicate_hint = True

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


RULE_TEXT = '每组至少满足一项；同一词条出现在不同组别时，会提高对该词条数量的需求。'


def add_rule_help(layout, parent):
    row = QHBoxLayout()
    label = QLabel(RULE_TEXT)
    label.setWordWrap(True)
    row.addWidget(label, 1)
    button = PushButton('完整示例')
    button.clicked.connect(lambda: show_constraint_details(parent, example=True))
    row.addWidget(button)
    layout.addLayout(row)


def show_constraint_details(parent, groups=None, example=False):
    dialog = QDialog(parent)
    dialog.setWindowTitle('完整示例' if example else '当前必备条件逻辑')
    dialog.resize(740, 580)
    dialog.setStyleSheet('QDialog { background: palette(window); } QTextBrowser { background: palette(base); border: 1px solid palette(mid); border-radius: 8px; padding: 14px; }')
    layout = QVBoxLayout(dialog)
    layout.setContentsMargins(24, 20, 24, 20)
    layout.setSpacing(12)
    title = QLabel('条件组如何同时满足' if example else '本次配装的完整条件')
    title.setStyleSheet('font-weight: bold; font-size: 13pt;')
    layout.addWidget(title)
    browser = QTextBrowser()
    browser.setOpenExternalLinks(False)
    if example:
        a, b, c, d = '物理攻击力＋3', '物理攻击力＋4', '提升大剑攻击力', '强化防御反击'
        pairs = [(a,a),(a,b),(a,d),(b,b),(b,d),(c,a),(c,b),(c,d)]
        rows = ''.join(f'<tr><td style="padding:8px">{x} ×2</td></tr>' if x==y else
                       f'<tr><td style="padding:8px">{x} ×1 ＋ {y} ×1</td></tr>' for x,y in pairs)
        body = f'<p><b>条件 1：</b>{a} 或 {b} 或 {c}</p><p><b>并且</b></p><p><b>条件 2：</b>{a} 或 {b} 或 {d}</p>'
        body += '<p>两组都需要满足。一条词条只能分给一组：只带一条物理攻击力＋3不够；带两条＋3，或者带＋3和大剑加攻，就可以。</p>'
        body += '<p><b>下面 8 种搭配，满足其中一种即可：</b></p><table width="100%">'+rows+'</table>'
        body += '<p>不计前后顺序，可以多带其他词条。这里计算携带数量，不改变词条的评分叠加规则。</p>'
    else:
        cards = []
        for i, group in enumerate(groups or [], 1):
            entries = '<br><span style="color:#008c95">或</span><br>'.join(escape(describe_requirement(x)) for x in group)
            cards.append(f'<table width="100%" cellpadding="12"><tr><td><b>条件 {i}</b><p>（{entries}）</p></td></tr></table>')
        body = '<p style="color:#008c95"><b>并且</b></p>'.join(cards) or '<p>没有必备条件。</p>'
        body += '<p style="color:#888">'+RULE_TEXT+'</p>'
    browser.setHtml(body)
    layout.addWidget(browser, 1)
    bottom = QHBoxLayout()
    bottom.addStretch()
    close = PrimaryPushButton('关闭')
    close.clicked.connect(dialog.accept)
    bottom.addWidget(close)
    layout.addLayout(bottom)
    dialog.exec()
