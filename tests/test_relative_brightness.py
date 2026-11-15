import unittest
import cv2
import numpy as np
from core.automation import RepositoryFilter


class RelativeBrightnessTests(unittest.TestCase):
    def detector(self, enabled=None):
        obj = object.__new__(RepositoryFilter)
        obj.settings = {} if enabled is None else {"experimental_relative_brightness": enabled}
        return obj

    def test_default_and_disabled_preserve_legacy_threshold(self):
        for level in (0, 58, 85, 86, 99, 145, 255):
            image = np.full((33, 33, 3), level, np.uint8)
            for enabled in (None, False):
                self.assertEqual(self.detector(enabled)._is_checkbox_checked(image), level > 85)

    def test_flat_background_is_never_a_check(self):
        for level in (0, 58, 85, 99, 145, 220, 255):
            self.assertFalse(self.detector(True)._is_checkbox_checked(np.full((33, 33, 3), level, np.uint8)))

    def test_mark_at_different_exposures_and_sizes(self):
        for size in (25, 33, 50):
            for background, foreground in ((20, 80), (60, 160), (100, 220), (170, 250)):
                image = np.full((size, size, 3), background, np.uint8)
                pts = np.array([(int(size*.25), int(size*.48)), (int(size*.44), int(size*.65)), (int(size*.75), int(size*.25))])
                cv2.polylines(image, [pts], False, (foreground,)*3, max(2, size//10))
                self.assertTrue(self.detector(True)._is_checkbox_checked(image))

    def test_weak_contrast_is_not_a_check(self):
        image = np.full((33, 33, 3), 100, np.uint8)
        cv2.line(image, (10, 20), (22, 10), (110,)*3, 3)
        self.assertFalse(self.detector(True)._is_checkbox_checked(image))


if __name__ == "__main__":
    unittest.main()
