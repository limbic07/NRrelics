"""Choose one OR group of required affixes or official relics."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QLabel, QLineEdit,
                               QTreeWidget, QTreeWidgetItem, QVBoxLayout, QAbstractItemView,
                               QHBoxLayout, QTextBrowser, QMessageBox, QButtonGroup)
from html import escape
from qfluentwidgets import PushButton, PrimaryPushButton, TogglePushButton
from core.official_relics import load_official_relics


def describe_requirement(entry):
    if entry.get('kind') == 'official':
        return f"官方遗物 #{entry['id']} {entry['label']}"
    return entry['name']


class ConstraintGroupDialog(QDialog):
    suppress_duplicate_hint = False

    def __init__(self, choices, selected=None, parent=None, other_groups=None, negative_choices=None):
        super().__init__(parent)
        self.other_groups = other_groups or []
        self.setWindowTitle('编辑一组必备条件')
        self.resize(740, 560)
        self.setStyleSheet('QDialog { background: palette(window); } QTreeWidget { background: palette(base); border: 1px solid palette(mid); border-radius: 8px; padding: 5px; } QTreeWidget::item { min-height: 30px; padding: 4px 8px; } QPushButton { min-height: 30px; }')
        layout=QVBoxLayout(self)
        layout.setContentsMargins(24,20,24,20)
        layout.setSpacing(8)
        self.negative = bool(selected and selected[0].get('exclude', False))
        self.positive_keys = {self._key(e) for e in choices}
        choices = list({self._key(e): e for e in choices + (negative_choices or []) + (selected or [])}.values())
        self.direction_buttons = add_direction_buttons(layout, self, self._set_direction, self.negative)
        self.rule_label = QLabel()
        self.rule_label.setWordWrap(True)
        layout.addWidget(self.rule_label)
        example_button = PushButton('完整示例', self)
        example_button.clicked.connect(lambda: show_constraint_details(self, example=True))
        layout.addWidget(example_button)
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
        self._set_direction(self.negative)
        self.list.itemChanged.connect(self._warn_duplicate)
        buttons=QDialogButtonBox(QDialogButtonBox.Save|QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setText('保存')
        buttons.button(QDialogButtonBox.Cancel).setText('取消')
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _set_direction(self, negative):
        self.negative = negative
        self.rule_label.setText('所选词条和官方遗物均不得出现在配装中；重复添加不会增加限制。' if negative else RULE_TEXT)
        self._filter()

    def _warn_duplicate(self, item, column):
        if self.negative:
            return
        if item.checkState(0) != Qt.Checked:
            return
        if ConstraintGroupDialog.suppress_duplicate_hint:
            return
        entry = item.data(0, Qt.UserRole)
        if not entry:
            return
        owners = [str(index) for index, group in self.other_groups
                  if any(not x.get("exclude", False) and self._key(x) == self._key(entry) for x in group)]
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
            allowed = self.negative or self._key(item.data(0, Qt.UserRole)) in self.positive_keys
            item.setHidden(not allowed or text not in content.lower())

    def _accept(self):
        if self.selected():
            self.accept()

    def selected(self):
        return [dict(self.list.topLevelItem(index).data(0,Qt.UserRole), exclude=self.negative)
                for index in range(self.list.topLevelItemCount())
                if self.list.topLevelItem(index).checkState(0)==Qt.Checked
                and (self.negative or self._key(self.list.topLevelItem(index).data(0,Qt.UserRole)) in self.positive_keys)]


def add_direction_buttons(layout, parent, callback, negative=False):
    row = QHBoxLayout()
    group = QButtonGroup(parent)
    group.setExclusive(True)
    for value, text in ((False, '正向条件'), (True, '反向条件')):
        button = TogglePushButton(text, parent)
        button.setCheckable(True)
        button.setChecked(value == negative)
        group.addButton(button)
        button.clicked.connect(lambda checked=False, v=value: callback(v))
        row.addWidget(button)
    layout.addLayout(row)
    return group


RULE_TEXT = '每组至少满足一项；同一词条出现在不同组别时，会提高对该词条数量的需求。'


def add_rule_help(layout, parent):
    row = QHBoxLayout()
    label = QLabel('正向组至少满足一项；反向组中的词条和官方遗物均不得出现。')
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
    if example:
        directions = add_direction_buttons(layout, dialog,
            lambda negative: browser.setHtml(negative_body if negative else body))
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
            negative = bool(group[0].get('exclude', False))
            entries = ('<br>且不得包含<br>' if negative else '<br>或<br>').join(escape(describe_requirement(x)) for x in group)
            cards.append(f'<table width="100%" cellpadding="12"><tr><td><b>条件 {i}｜{"反向：均不得出现" if negative else "正向：至少一项"}</b><p>（{entries}）</p></td></tr></table>')
        body = '<p style="color:#008c95"><b>并且</b></p>'.join(cards) or '<p>没有必备条件。</p>'
        body += '<p>正向组：'+RULE_TEXT+'</p><p>反向组：每一项均不得出现；分组或重复添加不改变效果。</p>'
    negative_body = '<p><b>反向条件 1：</b>物理攻击力＋3、物理攻击力＋4、提升大剑攻击力</p>'
    negative_body += '<p><b>反向条件 2：</b>物理攻击力＋3、强化防御反击</p>'
    negative_body += '<p>这四种词条在整套配装中都不能出现，出现任意一条就不符合条件。</p>'
    negative_body += '<p>两组重复勾选物理攻击力＋3，与只勾选一次相同。把四种词条放在同一个反向组，效果也完全相同。</p>'
    negative_body += '<p><b>例子：</b><br>包含一条物理攻击力＋3：不符合。<br>只包含强化防御反击：不符合。<br>以上四种均不包含：符合这两个反向条件。</p>'
    negative_body += '<p>也可以勾选官方遗物，例如禁止安定的遗志：该件官方遗物不能入选，其词条并不会因此被全部禁止。若另有词条禁令，官方遗物上的同名词条也必须遵守。</p>'
    browser.setHtml(body)
    layout.addWidget(browser, 1)
    bottom = QHBoxLayout()
    bottom.addStretch()
    close = PrimaryPushButton('关闭')
    close.clicked.connect(dialog.accept)
    bottom.addWidget(close)
    layout.addLayout(bottom)
    dialog.exec()
