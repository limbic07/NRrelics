"""The same tier-first editor for general and dedicated relic presets."""
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                               QListWidget, QListWidgetItem, QPushButton, QAbstractItemView)
from qfluentwidgets import LineEdit, PrimaryPushButton, PushButton, MessageBox

from core.relic_scoring import POSITIVE_TIERS, NEGATIVE_TIERS, DEFAULT_NEGATIVE_TIERS
from ui.dialogs.official_relic_score_dialog import OfficialRelicScoreDialog


TIER_NAMES = {
    "core": "重要", "secondary": "次要", "bonus": "锦上添花",
    "unacceptable": "不可接受", "harmful": "很伤", "negligible": "几乎无负面",
}
TIER_ORDER = POSITIVE_TIERS + NEGATIVE_TIERS


class PresetEditDialog(QDialog):
    """Selecting a tier first makes every checkbox's meaning unambiguous."""

    preset_saved = Signal(str, str, list)  # Legacy global-blacklist editor.
    graded_saved = Signal(str, str, list, dict, dict, list, dict)

    def __init__(self, vocabulary, preset_data=None, is_general=False, parent=None,
                 mode="normal", exception_vocabulary=None, inherited_vocabulary=None,
                 inherited_tiers=None, inherited_negative_tiers=None,
                 default_negative_tiers=None, new_character=None, suggested_name=''):
        super().__init__(parent)
        self.preset_data = preset_data or {}
        self.new_character = new_character
        self.suggested_name = suggested_name
        self.is_general = is_general
        self.is_blacklist = self.preset_data.get("type") == "deepnight_blacklist"
        self.mode = mode
        self.positive_vocabulary = list(dict.fromkeys(
            list(vocabulary) + list(self.preset_data.get("affixes", []))
            + list(inherited_vocabulary or [])))
        self.negative_vocabulary = (list(dict.fromkeys(exception_vocabulary or []))
                                    if mode == "deepnight" and not self.is_blacklist else [])
        self.inherited_positive = {
            name: (inherited_tiers or {}).get(name, "secondary")
            for name in inherited_vocabulary or []
        }
        self.inherited_negative = dict(inherited_negative_tiers or {})
        self.default_negative = dict(DEFAULT_NEGATIVE_TIERS)
        self.default_negative.update(default_negative_tiers or {})
        old_positive = self.preset_data.get("affix_tiers", {})
        self.local_positive = {
            name: old_positive.get(name, "secondary")
            for name in self.preset_data.get("affixes", [])
        }
        self.local_positive.update({
            name: tier for name, tier in old_positive.items()
            if name in self.inherited_positive and name not in self.local_positive
        })
        self.local_negative = dict(self.preset_data.get("negative_tiers", {}))
        self.excluded = set(self.preset_data.get("excluded_affixes", []))
        self.official_scores = dict(self.preset_data.get('official_scores', {}))
        self.blacklist_selected = set(self.preset_data.get("affixes", [])) if self.is_blacklist else set()
        self.current_tier = "core"
        self._loading = False

        self.setWindowTitle("编辑预设" if preset_data else "创建预设")
        self.resize(820, 690)
        self.setMinimumSize(700, 560)
        self.setStyleSheet('''
            QDialog { background: #f5f5f5; }
            QListWidget { background: white; border: 1px solid #d8d8d8;
                          border-radius: 9px; padding: 4px; }
            QListWidget::item { min-height: 30px; padding: 4px 8px; }
            QListWidget::item:selected { background: #dceffc; color: #111; border-radius: 5px; }
            QPushButton#tierButton { min-height: 30px; }
            QPushButton#tierButton:checked { background: #009eaa; color: white;
                border: 1px solid #009eaa; border-radius: 5px; }
        ''')
        self._build_ui()
        self._render_choices()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(8)

        if not self.is_general:
            name_row = QHBoxLayout()
            name_row.addWidget(QLabel("流派名称" if self.new_character else "预设名称"))
            self.name_input = LineEdit()
            self.name_input.setPlaceholderText("输入预设名称")
            self.name_input.setText(self.preset_data.get("name", self.suggested_name))
            name_row.addWidget(self.name_input)
            layout.addLayout(name_row)
        else:
            layout.addWidget(QLabel("深夜黑名单" if self.is_blacklist else "通用预设"))

        if not self.is_blacklist:
            layout.addWidget(QLabel("先选择词条等级，再在下方勾选词条"))
            self.tier_buttons = {}
            positive_row = QHBoxLayout()
            for tier in POSITIVE_TIERS:
                button = QPushButton(TIER_NAMES[tier])
                button.setObjectName('tierButton')
                button.setFixedWidth(120)
                button.setCheckable(True)
                button.clicked.connect(lambda checked=False, value=tier: self._switch_tier(value))
                positive_row.addWidget(button)
                self.tier_buttons[tier] = button
            positive_row.addStretch()
            layout.addLayout(positive_row)
            if self.mode == "deepnight":
                layout.addWidget(QLabel("深夜负面词条也可在上方选为正面效果；或在这里指定扣分等级"))
                negative_row = QHBoxLayout()
                for tier in NEGATIVE_TIERS:
                    button = QPushButton(TIER_NAMES[tier])
                    button.setObjectName('tierButton')
                    button.setFixedWidth(120)
                    button.setCheckable(True)
                    button.clicked.connect(lambda checked=False, value=tier: self._switch_tier(value))
                    negative_row.addWidget(button)
                    self.tier_buttons[tier] = button
                negative_row.addStretch()
                layout.addLayout(negative_row)
            self._update_tier_buttons()

        search_row = QHBoxLayout()
        search_row.addWidget(QLabel("搜索"))
        self.search_input = LineEdit()
        self.search_input.setPlaceholderText("输入关键词搜索词条")
        self.search_input.textChanged.connect(self._render_choices)
        search_row.addWidget(self.search_input)
        layout.addLayout(search_row)

        batch_row = QHBoxLayout()
        for title, handler in (("全选可见", self._select_visible),
                               ("全不选可见", self._clear_visible)):
            button = PushButton(title)
            button.clicked.connect(handler)
            batch_row.addWidget(button)
        batch_row.addStretch()
        layout.addLayout(batch_row)

        self.list_label = QLabel()
        layout.addWidget(self.list_label)
        self.vocab_list = QListWidget()
        self.vocab_list.setSelectionMode(QAbstractItemView.NoSelection)
        self.vocab_list.itemChanged.connect(self._on_item_changed)
        layout.addWidget(self.vocab_list, 1)
        layout.addWidget(QLabel('右键词条所在行可勾选或取消勾选。'))

        if self.mode == 'normal' and not self.is_blacklist:
            official_row = QHBoxLayout()
            official_button = PushButton('官方遗物分数…')
            official_button.clicked.connect(self._edit_official_scores)
            official_row.addWidget(official_button)
            self.official_count = QLabel()
            official_row.addWidget(self.official_count)
            official_row.addStretch()
            layout.addLayout(official_row)
            self._update_official_count()

        bottom_row = QHBoxLayout()
        self.view_button = PushButton("查看已选择词条")
        self.view_button.clicked.connect(self._show_selected)
        bottom_row.addWidget(self.view_button)
        self.count_label = QLabel()
        bottom_row.addWidget(self.count_label)
        bottom_row.addStretch()
        cancel = PushButton("取消")
        cancel.clicked.connect(self.reject)
        bottom_row.addWidget(cancel)
        save = PrimaryPushButton("保存")
        save.clicked.connect(self._save)
        bottom_row.addWidget(save)
        layout.addLayout(bottom_row)

    def _switch_tier(self, tier):
        self.current_tier = tier
        self._update_tier_buttons()
        self._render_choices()

    def _update_tier_buttons(self):
        for tier, button in self.tier_buttons.items():
            button.setChecked(tier == self.current_tier)

    def _positive_tier(self, name):
        if name in self.excluded:
            return None
        return self.local_positive.get(name, self.inherited_positive.get(name))

    def _negative_tier(self, name):
        return self.local_negative.get(
            name, self.inherited_negative.get(name,
                                              self.default_negative.get(name, "negligible")))

    def _render_choices(self, *_):
        self._loading = True
        self.vocab_list.clear()
        search = self.search_input.text().strip().lower()
        if self.is_blacklist:
            names = self.positive_vocabulary
            label = "黑名单词条"
        elif self.current_tier in NEGATIVE_TIERS:
            names = self.negative_vocabulary
            label = f"{TIER_NAMES[self.current_tier]}：选择深夜负面词条"
        else:
            names = self.positive_vocabulary + self.negative_vocabulary
            label = f"{TIER_NAMES[self.current_tier]}：选择正面词条"
        names = [name for name in dict.fromkeys(names) if search in name.lower()]
        self.list_label.setText(f"{label}（当前显示 {len(names)} 条）")
        for name in names:
            if self.is_blacklist:
                selected = name in self.blacklist_selected
                suffix = ""
            elif name in self.negative_vocabulary:
                current = self._negative_tier(name)
                explicit = name in self.local_negative or name in self.inherited_negative
                selected = explicit and current == self.current_tier
                source = "已选" if explicit else "默认"
                suffix = f"  · {source}：{TIER_NAMES[current]}"
            else:
                current = self._positive_tier(name)
                selected = current == self.current_tier
                suffix = (f"  · 已选：{TIER_NAMES[current]}" if current
                          else "  · 已排除通用" if name in self.excluded else "")
            item = QListWidgetItem(name + suffix)
            item.setData(Qt.UserRole, name)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked if selected else Qt.Unchecked)
            self.vocab_list.addItem(item)
        self._loading = False
        self._update_count()

    def _on_item_changed(self, item):
        if self._loading:
            return
        name = item.data(Qt.UserRole)
        checked = item.checkState() == Qt.Checked
        if self.is_blacklist:
            (self.blacklist_selected.add if checked else self.blacklist_selected.discard)(name)
        elif name in self.negative_vocabulary:
            if checked:
                self.local_negative[name] = self.current_tier
            elif self._negative_tier(name) == self.current_tier:
                if name in self.inherited_negative:
                    self.local_negative[name] = self.default_negative.get(name, "negligible")
                else:
                    self.local_negative.pop(name, None)
        else:
            if checked:
                self.local_positive[name] = self.current_tier
                self.excluded.discard(name)
            elif self._positive_tier(name) == self.current_tier:
                self.local_positive.pop(name, None)
                if name in self.inherited_positive:
                    self.excluded.add(name)
        self._render_choices()

    def _batch(self, action):
        choices = [(self.vocab_list.item(i).data(Qt.UserRole),
                    self.vocab_list.item(i).checkState() == Qt.Checked)
                   for i in range(self.vocab_list.count())]
        for name, checked in choices:
            desired = action == "select"
            if desired == checked:
                continue
            if self.is_blacklist:
                (self.blacklist_selected.add if desired else self.blacklist_selected.discard)(name)
            elif name in self.negative_vocabulary:
                if desired:
                    self.local_negative[name] = self.current_tier
                elif name in self.inherited_negative:
                    self.local_negative[name] = self.default_negative.get(name, "negligible")
                else:
                    self.local_negative.pop(name, None)
            elif desired:
                self.local_positive[name] = self.current_tier
                self.excluded.discard(name)
            else:
                self.local_positive.pop(name, None)
                if name in self.inherited_positive:
                    self.excluded.add(name)
        self._render_choices()

    def _select_visible(self):
        self._batch("select")

    def _clear_visible(self):
        self._batch("clear")

    def _selected_rows(self):
        rows = []
        for name in set(self.inherited_positive) | set(self.local_positive):
            tier = self._positive_tier(name)
            if tier:
                rows.append((tier, name, "通用继承" if name in self.inherited_positive else "本预设"))
        for name in set(self.local_negative) | set(self.inherited_negative):
            tier = self._negative_tier(name)
            rows.append((tier, name, "通用继承" if name in self.inherited_negative
                         and name not in self.local_negative else "本预设"))
        for name in self.excluded:
            rows.append(("excluded", name, "已排除通用"))
        return sorted(rows, key=lambda row: (TIER_ORDER.index(row[0])
                                             if row[0] in TIER_ORDER else len(TIER_ORDER), row[1]))

    def _update_count(self):
        count = len(self.blacklist_selected) if self.is_blacklist else len(self._selected_rows())
        self.count_label.setText(f"已选择：{count} 条")

    def _show_selected(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("已选择词条")
        dialog.resize(720, 520)
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel("按重要性从高到低排列；专属预设显示继承与覆盖后的结果"))
        selected_list = QListWidget()
        layout.addWidget(selected_list)

        def refresh():
            selected_list.clear()
            if self.is_blacklist:
                rows = [("blacklist", name, "") for name in sorted(self.blacklist_selected)]
            else:
                rows = self._selected_rows()
            for tier, name, source in rows:
                label = "黑名单" if tier == "blacklist" else TIER_NAMES.get(tier, "已排除")
                item = QListWidgetItem(f"【{label}】{name}" + (f"  · {source}" if source else ""))
                item.setData(Qt.UserRole, (tier, name))
                selected_list.addItem(item)

        refresh()
        row = QHBoxLayout()
        remove_button = PushButton("移除选中项")

        def remove():
            item = selected_list.currentItem()
            if not item:
                return
            tier, name = item.data(Qt.UserRole)
            if tier == "blacklist":
                self.blacklist_selected.discard(name)
            elif tier == "excluded":
                self.excluded.discard(name)
            elif name in self.negative_vocabulary:
                if name in self.inherited_negative:
                    self.local_negative[name] = self.default_negative.get(name, "negligible")
                else:
                    self.local_negative.pop(name, None)
            else:
                self.local_positive.pop(name, None)
                if name in self.inherited_positive:
                    self.excluded.add(name)
            refresh()
            self._render_choices()

        remove_button.clicked.connect(remove)
        row.addWidget(remove_button)
        row.addStretch()
        close = PushButton("关闭")
        close.clicked.connect(dialog.accept)
        row.addWidget(close)
        layout.addLayout(row)
        dialog.exec()

    def get_selected_affixes(self):
        return sorted(self.blacklist_selected) if self.is_blacklist else sorted(
            name for name in self.local_positive if name not in self.inherited_positive)

    def get_affix_tiers(self):
        return self.local_positive.copy()

    def _update_official_count(self):
        self.official_count.setText(f"已指定 {len(self.official_scores)} 件官方遗物的分数")

    def _edit_official_scores(self):
        dialog = OfficialRelicScoreDialog(self.official_scores, self)
        if dialog.exec() == QDialog.Accepted:
            self.official_scores = dialog.scores()
            self._update_official_count()

    def _save(self):
        name = self.name_input.text().strip() if not self.is_general else "通用预设"
        if not name:
            MessageBox("错误", "请输入预设名称", self).exec()
            return
        if self.new_character:
            name = f'{self.new_character}｜{name.split("｜", 1)[-1].strip()}'
        identifier = self.preset_data.get("id", "")
        if self.is_blacklist:
            self.preset_saved.emit(identifier, name, sorted(self.blacklist_selected))
        else:
            self.graded_saved.emit(identifier, name, self.get_selected_affixes(),
                                   self.get_affix_tiers(), self.local_negative.copy(),
                                   sorted(self.excluded), self.official_scores.copy())
        self.accept()
