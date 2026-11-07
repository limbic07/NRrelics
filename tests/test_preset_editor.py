"""Behavior of the tier-first editor without starting game automation."""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from ui.dialogs.preset_edit_dialog import PresetEditDialog
from ui.pages.page_settings import SettingsPage


class PresetEditorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_selected_tiers_visible_and_sorted(self):
        dialog = PresetEditDialog(["物理攻击", "回血"], is_general=True)
        dialog._switch_tier("core")
        self._check(dialog, "物理攻击")
        dialog._switch_tier("bonus")
        self._check(dialog, "回血")
        self.assertEqual(dialog.get_affix_tiers(), {"物理攻击": "core", "回血": "bonus"})
        self.assertEqual([tier for tier, _, _ in dialog._selected_rows()], ["core", "bonus"])
        dialog.close()

    def test_dedicated_inherits_and_overrides_negative(self):
        dialog = PresetEditDialog(
            ["物理攻击"], is_general=False, mode="deepnight",
            exception_vocabulary=["持续减少血量"],
            inherited_vocabulary=["物理攻击"], inherited_tiers={"物理攻击": "core"},
            default_negative_tiers={"持续减少血量": "unacceptable"},
        )
        self.assertEqual(dialog._positive_tier("物理攻击"), "core")
        dialog._switch_tier("secondary")
        self._check(dialog, "物理攻击")
        dialog._switch_tier("core")
        self._check(dialog, "持续减少血量")
        self.assertEqual(dialog.get_affix_tiers()["物理攻击"], "secondary")
        self.assertEqual(dialog.local_negative["持续减少血量"], "core")
        self.assertFalse(hasattr(dialog, "required_groups_list"))
        dialog.close()

    def test_normal_settings_have_no_negative_score_fields(self):
        original = SettingsPage._load_settings
        try:
            SettingsPage._load_settings = lambda self: self._default_settings()
            page = SettingsPage()
            self.assertFalse(any(mode == "normal" and sign == "negative"
                                 for mode, sign, _ in page.score_inputs))
            page.close()
        finally:
            SettingsPage._load_settings = original

    @staticmethod
    def _check(dialog, name):
        for i in range(dialog.vocab_list.count()):
            item = dialog.vocab_list.item(i)
            if item.data(Qt.UserRole) == name:
                item.setCheckState(Qt.Checked)
                return
        raise AssertionError(f"Missing entry: {name}")


if __name__ == "__main__":
    unittest.main()
