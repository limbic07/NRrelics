"""Choose the character before creating a dedicated preset."""

from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from qfluentwidgets import ComboBox, PrimaryPushButton, PushButton, CardWidget

from core.loadout_optimizer import HEROES


class PresetCharacterDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('选择流派角色')
        self.setFixedWidth(520)
        self.setStyleSheet('QDialog { background: palette(window); }')

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)
        title = QLabel('选择流派角色')
        title.setFont(QFont('Segoe UI', 22, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)
        card = CardWidget()
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(14, 10, 14, 10)
        card_layout.addWidget(QLabel('选择该预设所属的角色'))
        self.character_combo = ComboBox()
        for character in HEROES:
            self.character_combo.addItem(character)
        card_layout.addWidget(self.character_combo)
        layout.addWidget(card)

        buttons = QHBoxLayout()
        buttons.addStretch()
        cancel = PushButton('取消')
        cancel.clicked.connect(self.reject)
        buttons.addWidget(cancel)
        confirm = PrimaryPushButton('继续')
        confirm.clicked.connect(self.accept)
        buttons.addWidget(confirm)
        layout.addLayout(buttons)

    def selected_character(self):
        return self.character_combo.currentText()


def next_preset_title(character, presets):
    existing = {preset.get('name', '') for preset in presets.values()}
    number = 1
    while f'{character}｜自定义流派 {number}' in existing:
        number += 1
    return f'自定义流派 {number}'
