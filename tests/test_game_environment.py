import tempfile
import unittest
import hashlib
import struct
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import numpy as np
from PIL import Image
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from core.automation import RepositoryFilter
from core.game_environment import inspect_game_brightness, log_brightness_check
from core.repo_cleaner import RepoCleaner
from core.shop_automation import ShopAutomation


def _sample_save(brightness):
    """Small BND4 fixture with a valid encrypted global profile entry."""
    profile = bytearray(64)
    struct.pack_into("<I", profile, 0, 0x00060010)
    profile[0x10:0x16] = bytes([5, 5, brightness, 2, 0, 5])
    profile[-28:-12] = hashlib.md5(profile[4:-28]).digest()
    profile[-12:] = bytes([12] * 12)
    iv = bytes(range(16))
    key = bytes.fromhex("18f6326605bd178a5524523ac0a0c609")
    encryptor = Cipher(algorithms.AES(key), modes.CBC(iv)).encryptor()
    encrypted = iv + encryptor.update(bytes(profile)) + encryptor.finalize()
    entry_pos = 64 + 10 * 32
    data_pos = 64 + 11 * 32
    save = bytearray(data_pos)
    save[:4] = b"BND4"
    struct.pack_into("<I", save, 12, 11)
    save[entry_pos:entry_pos + 8] = b"\x40\x00\x00\x00\xff\xff\xff\xff"
    struct.pack_into("<3i", save, entry_pos + 8, len(encrypted), 0, data_pos)
    return bytes(save) + encrypted


class GameEnvironmentTests(unittest.TestCase):
    def test_secondary_monitor_capture_uses_virtual_desktop_coordinates(self):
        controller = object.__new__(RepositoryFilter)
        with patch.object(controller, "_get_client_rect_screen_coords", return_value=(-1280, -100, 1280, 720)):
            with patch("core.automation.ImageGrab.grab", return_value=Image.new("RGB", (1280, 720), (12, 34, 56))) as grab:
                image = controller._capture_game_window()
        grab.assert_called_once_with(bbox=(-1280, -100, 0, 620), all_screens=True)
        self.assertEqual(image.shape, (720, 1280, 3))
        np.testing.assert_array_equal(image[0, 0], [56, 34, 12])

    def test_actual_client_aspect_ratio_is_required(self):
        controller = object.__new__(RepositoryFilter)
        messages = []
        log = lambda message, level: messages.append((message, level))
        with patch.object(controller, "refresh_window_info"):
            with patch.object(controller, "_get_client_rect_screen_coords", return_value=(1920, 0, 2560, 1080)):
                self.assertFalse(controller.validate_game_resolution(log))
            with patch.object(controller, "_get_client_rect_screen_coords", return_value=(-1280, 0, 1280, 720)):
                self.assertTrue(controller.validate_game_resolution(log))
            with patch.object(controller, "_get_client_rect_screen_coords", return_value=None):
                self.assertFalse(controller.validate_game_resolution(log))
        self.assertIn("2560x1080", messages[0][0])
        self.assertIn("1920x1080", messages[0][0])

    def test_brightness_is_read_fresh_from_encrypted_save(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "NR0000.sl2"
            path.write_bytes(_sample_save(5))
            self.assertEqual(inspect_game_brightness(path), (5, None))
            path.write_bytes(_sample_save(6))
            self.assertEqual(inspect_game_brightness(path), (6, None))
            damaged = bytearray(_sample_save(6))
            damaged[-20] ^= 1
            path.write_bytes(damaged)
            with patch("core.game_environment.time.sleep"):
                self.assertIsNone(inspect_game_brightness(path)[0])

    def test_missing_save_remains_unknown(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "missing.sl2"
            with patch("core.game_environment.time.sleep"):
                self.assertIsNone(inspect_game_brightness(path)[0])

    def test_unknown_brightness_warns_instead_of_claiming_success(self):
        messages = []
        with patch("core.game_environment.inspect_game_brightness", return_value=(None, "未找到 Nightreign 存档")):
            log_brightness_check(lambda message, level: messages.append((message, level)))
        self.assertEqual(messages[0][1], "WARNING")
        self.assertIn("无法核实", messages[0][0])

    def test_saved_brightness_six_warns_and_five_passes(self):
        messages = []
        with patch("core.game_environment.inspect_game_brightness", side_effect=[(6, None), (5, None)]):
            log_brightness_check(lambda message, level: messages.append((message, level)))
            log_brightness_check(lambda message, level: messages.append((message, level)))
        self.assertEqual([level for _, level in messages], ["WARNING", "INFO"])
        self.assertIn("亮度设置为 6", messages[0][0])

    def test_shop_rejects_bad_ratio_before_game_input(self):
        shop = object.__new__(ShopAutomation)
        shop.settings = {}
        shop.repo_filter = SimpleNamespace(
            settings=None, refresh_window_info=Mock(),
            validate_game_resolution=Mock(return_value=False))
        shop.preset_manager = SimpleNamespace(
            get_general_preset=Mock(return_value=None),
            get_dedicated_presets=Mock(return_value={}))
        shop.qualified_relics = []
        with patch("core.shop_automation.create_capture_session", return_value=None), \
             patch("core.shop_automation.keyboard.add_hotkey"), \
             patch("core.shop_automation.keyboard.remove_hotkey"), \
             patch("core.shop_automation.time.sleep"), \
             patch("core.shop_automation.DEBUG_ENABLED", False), \
             patch.object(shop, "_enter_merchant_interface") as enter:
            shop.start_shopping("normal", "new", 0, True)
        self.assertEqual(shop.stop_reason, "error")
        enter.assert_not_called()

    def test_repository_rejects_bad_ratio_before_filtering(self):
        cleaner = object.__new__(RepoCleaner)
        cleaner.relic_detector = Mock()
        cleaner.settings = {}
        cleaner.repository_filter = SimpleNamespace(
            settings=None, validate_game_resolution=Mock(return_value=False),
            _get_client_rect_screen_coords=Mock(return_value=(0, 0, 1024, 768)),
            apply_filter=Mock())
        cleaner.qualified_relics = []
        with patch("core.repo_cleaner.create_capture_session", return_value=None), \
             patch("core.repo_cleaner.time.sleep"), \
             patch.object(cleaner, "_find_game_window", return_value=object()), \
             patch("core.repo_cleaner.log_brightness_check") as brightness_check:
            cleaner.start_cleaning("normal", "sell", 1, False, True)
        self.assertEqual(cleaner.stop_reason, "error")
        cleaner.repository_filter.apply_filter.assert_not_called()
        brightness_check.assert_not_called()


if __name__ == "__main__":
    unittest.main()
