import unittest
from unittest.mock import Mock, patch

import cv2
import numpy as np

from core.repo_cleaner import RepoCleaner
from core.repo_navigation import RepositoryNavigation
from core.automation import RepositoryFilter
from core.relic_detector import (RELIC_STATE_DARK_E, RELIC_STATE_DARK_O,
                                 RELIC_STATE_LIGHT, RelicDetector)


class RepoNavigationTests(unittest.TestCase):
    def setUp(self):
        self.cleaner = object.__new__(RepoCleaner)
        self.cleaner.is_running = True
        self.cleaner.pending_sell_count = 0
        self.cleaner.stats = {"sold": 0, "favorited": 0}
        self.log = lambda message, level: None

    def test_sale_marks_once_without_requesting_right(self):
        with patch("core.repo_cleaner.pydirectinput.press") as press:
            need_right = self.cleaner._execute_action(
                RELIC_STATE_LIGHT, False, "sell", self.log)
        self.assertFalse(need_right)
        press.assert_called_once_with("f")
        self.assertEqual(self.cleaner.pending_sell_count, 1)

    def test_favorite_requests_right_after_two(self):
        with patch("core.repo_cleaner.pydirectinput.press") as press:
            need_right = self.cleaner._execute_action(
                RELIC_STATE_LIGHT, True, "favorite", self.log)
        self.assertTrue(need_right)
        press.assert_called_once_with("2")
        self.assertEqual(self.cleaner.stats["favorited"], 1)

    def test_sale_requires_cursor_even_when_details_change(self):
        nav = RepositoryNavigation()
        before = np.zeros((1080, 1920, 3), dtype=np.uint8)
        after = before.copy()
        after[770:968, 1070:1700] = 20
        nav.expect_next(before, "sale")
        detector = Mock()
        detector.detect_cursor.return_value = ((1035, 207, 99, 98), 99)
        result = nav.check(after, detector)
        self.assertTrue(result.confirmed)
        self.assertEqual(result.evidence, "光标位于预计下一格")
        detector.detect_cursor.assert_called_once()

    def test_same_text_different_detail_icon_confirms_next_relic(self):
        nav = RepositoryNavigation()
        before = np.zeros((1080, 1920, 3), dtype=np.uint8)
        after = before.copy()
        after[750:890, 930:1055] = 20
        nav.expect_next(before, "right")
        detector = Mock()
        detector.detect_cursor.return_value = ((1035, 207, 99, 98), 99)
        result = nav.check(after, detector)
        self.assertTrue(result.confirmed)
        self.assertEqual(result.evidence, "光标位于预计下一格")
        detector.detect_cursor.assert_called_once()

    def test_identical_relics_use_cursor_with_sale_amount_change(self):
        nav = RepositoryNavigation()
        before = np.zeros((1080, 1920, 3), dtype=np.uint8)
        after = before.copy()
        after[380:430, 465:545] = 20
        nav.expect_next(before, "sale")
        detector = Mock()
        detector.detect_cursor.return_value = ((1035, 207, 99, 98), 99)
        result = nav.check(after, detector)
        self.assertTrue(result.confirmed)
        self.assertEqual(result.evidence, "光标位于预计下一格")
        detector.detect_cursor.assert_called_once()

    def test_new_card_with_old_details_is_not_sent_to_ocr(self):
        nav = RepositoryNavigation()
        before = np.zeros((1080, 1920, 3), dtype=np.uint8)
        nav.expect_next(before, "sale")
        after = before.copy()
        x, y, w, h = nav.expected_box(after)
        after[y + 12:y + h - 12, x + 12:x + w - 12] = 20
        after[380:430, 465:545] = 20
        detector = Mock()
        detector.detect_cursor.return_value = ((1035, 207, 99, 98), 99)
        result = nav.check(after, detector)
        self.assertFalse(result.confirmed)
        self.assertEqual(result.evidence, "详情尚未刷新")
        self.assertTrue(result.cursor_checked)
        detector.detect_cursor.assert_called_once()

    def test_right_uses_expected_neighbor_when_details_match(self):
        nav = RepositoryNavigation()
        frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
        nav.expect_next(frame, "right")
        detector = Mock()
        detector.detect_cursor.return_value = ((1035, 207, 99, 98), 99)
        result = nav.check(frame, detector)
        self.assertTrue(result.confirmed)
        self.assertEqual(result.evidence, "光标位于预计下一格")

    def test_changed_details_do_not_override_wrong_cursor(self):
        nav = RepositoryNavigation()
        before = np.zeros((1080, 1920, 3), dtype=np.uint8)
        after = before.copy()
        after[770:968, 1070:1700] = 20
        nav.expect_next(before, "sale")
        detector = Mock()
        detector.detect_cursor.return_value = ((925, 207, 99, 98), 99)
        result = nav.check(after, detector)
        self.assertFalse(result.confirmed)
        self.assertEqual(result.evidence, "光标未到预计下一格")

    def test_no_evidence_keeps_destructive_action_blocked(self):
        nav = RepositoryNavigation()
        frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
        nav.expect_next(frame, "sale")
        detector = Mock()
        detector.detect_cursor.return_value = ((925, 207, 99, 98), 99)
        result = nav.check(frame, detector)
        self.assertFalse(result.confirmed)

    def test_grid_wrap_scrolls_after_fourth_cursor_row(self):
        nav = RepositoryNavigation()
        frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
        nav.index = 8
        self.assertEqual(nav.expected_box(frame)[:2], (928, 315))
        nav.index = 31
        self.assertEqual(nav.expected_box(frame)[:2], (1698, 527))
        nav.index = 32
        self.assertEqual(nav.expected_box(frame)[:2], (928, 527))
        nav.index = 40
        self.assertEqual(nav.expected_box(frame)[:2], (928, 527))
        nav.index = 42
        self.assertEqual(nav.expected_box(frame)[:2], (1148, 527))

    def test_final_inventory_row_uses_fifth_visible_row(self):
        frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
        nav = RepositoryNavigation(total_items=673)
        nav.index = 671  # 第 672 件仍在第 4 行末尾
        self.assertEqual(nav.expected_box(frame)[:2], (1698, 527))
        nav.index = 672  # 列表已滚到末尾，第 673 件落在第 5 行首格
        self.assertEqual(nav.expected_box(frame)[:2], (928, 633))

        nav = RepositoryNavigation(total_items=40)
        nav.index = 32
        self.assertEqual(nav.expected_box(frame)[:2], (928, 633))
        nav = RepositoryNavigation(total_items=41)
        nav.index = 32
        self.assertEqual(nav.expected_box(frame)[:2], (928, 527))
        nav.index = 40
        self.assertEqual(nav.expected_box(frame)[:2], (928, 633))

    def test_state_detection_uses_tracked_box(self):
        detector = RelicDetector()
        frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
        box = (928, 209, 92, 94)
        with patch.object(detector, "detect_cursor", side_effect=AssertionError("global cursor used")):
            with patch.object(detector, "_detect_detailed_state", return_value={
                "state": "Light", "equipped": False, "favorited": False}):
                self.assertEqual(detector.detect_state(frame, cursor_box=box), RELIC_STATE_LIGHT)

    def test_official_detail_marker_colors_override_card_brightness(self):
        detector = RelicDetector()
        box = (1258, 527, 92, 94)
        colors = {
            "red": (15, 20, 110),
            "gold": (20, 90, 115),
            "green": (30, 102, 45),
            "blue": (110, 55, 20),
        }
        for name, color in colors.items():
            with self.subTest(color=name):
                frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
                cv2.rectangle(frame, (1035, 869), (1045, 878), color, -1)
                with patch.object(detector, "_detect_detailed_state",
                                  side_effect=AssertionError("brightness used")):
                    self.assertEqual(detector.detect_state(frame, cursor_box=box),
                                     RELIC_STATE_DARK_O)
                smaller = cv2.resize(frame, (1280, 720), interpolation=cv2.INTER_AREA)
                small_box = tuple(round(v * 2 / 3) for v in box)
                self.assertEqual(detector.detect_state(smaller, cursor_box=small_box),
                                 RELIC_STATE_DARK_O)

    def test_scrolled_relic_uses_fourth_row_state(self):
        frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
        nav = RepositoryNavigation()
        nav.index = 42  # 第 43 件：真实光标在第 4 行第 3 格
        detector = RelicDetector()

        def state_for_box(_image, box, _scale):
            if box[1] == 527:
                return {"state": "Dark", "equipped": True, "favorited": False}
            return {"state": "Light", "equipped": False, "favorited": False}

        with patch.object(detector, "_detect_detailed_state", side_effect=state_for_box):
            state = detector.detect_state(frame, cursor_box=nav.expected_box(frame))
        self.assertEqual(state, RELIC_STATE_DARK_E)

    def test_line_rois_are_cut_from_supplied_screen(self):
        repository = object.__new__(RepositoryFilter)
        repository.scale_x = repository.scale_y = 1.0
        frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
        frame[810:833, 1107:1700] = 77
        with patch.object(repository, "_capture_game_window", side_effect=AssertionError("recaptured")):
            lines = repository.extract_line_rois(frame)
        self.assertEqual(len(lines), 6)
        self.assertEqual(int(lines[0].mean()), 77)
        self.assertEqual(int(lines[1].mean()), 0)

    def test_cleaning_uses_one_screen_for_state_and_ocr(self):
        frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
        lines = [frame[810:833, 1107:1700]] * 6
        repository = Mock(scale_x=1.0, scale_y=1.0)
        repository.validate_game_resolution.return_value = True
        repository.apply_filter.return_value = True
        repository._capture_game_window.return_value = frame
        repository.extract_line_rois.return_value = lines
        detector = Mock()
        detector.detect_state.return_value = RELIC_STATE_LIGHT
        engine = Mock()
        engine.recognize_with_classification_from_lines.return_value = {
            "success": True, "positive_count": 0, "negative_count": 0, "affixes": []}
        cleaner = object.__new__(RepoCleaner)
        cleaner.settings = {}
        cleaner.repository_filter = repository
        cleaner.relic_detector = detector
        cleaner.ocr_engine = engine
        cleaner.preset_manager = Mock()
        cleaner.preset_manager.get_general_preset.return_value = {"affixes": []}
        cleaner.preset_manager.get_active_dedicated_presets.return_value = []
        cleaner.recorder = Mock()
        cleaner.qualified_relics = []
        match_result = Mock(qualified=False, destructive_action_allowed=False)
        with patch("core.repo_cleaner.create_capture_session", return_value=None), \
             patch("core.repo_cleaner.time.sleep"), \
             patch("core.repo_cleaner.log_brightness_check"), \
             patch("core.repo_cleaner.log_match"), \
             patch("core.repo_cleaner.pydirectinput.press"), \
             patch.object(cleaner, "_find_game_window", return_value=object()), \
             patch.object(cleaner, "_match_affixes", return_value=match_result):
            cleaner.start_cleaning("normal", "sell", 1, False, True)
        repository._capture_game_window.assert_called_once_with()
        repository.capture_line_rois.assert_not_called()
        repository.extract_line_rois.assert_called_once()
        self.assertIs(repository.extract_line_rois.call_args.args[0], frame)
        self.assertIs(detector.detect_state.call_args.args[0], frame)
        self.assertIs(engine.recognize_with_classification_from_lines.call_args.args[0], lines)

    def test_last_official_relic_finishes_without_extra_right_key(self):
        frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
        repository = Mock(scale_x=1.0, scale_y=1.0)
        repository.validate_game_resolution.return_value = True
        repository.apply_filter.return_value = True
        repository._capture_game_window.return_value = frame
        detector = Mock()
        detector.detect_state.return_value = RELIC_STATE_DARK_O
        cleaner = object.__new__(RepoCleaner)
        cleaner.settings = {}
        cleaner.repository_filter = repository
        cleaner.relic_detector = detector
        cleaner.ocr_engine = Mock()
        cleaner.preset_manager = Mock()
        cleaner.preset_manager.get_general_preset.return_value = {"affixes": []}
        cleaner.preset_manager.get_active_dedicated_presets.return_value = []
        cleaner.recorder = Mock()
        cleaner.qualified_relics = []
        with patch("core.repo_cleaner.create_capture_session", return_value=None), \
             patch("core.repo_cleaner.time.sleep"), \
             patch("core.repo_cleaner.log_brightness_check"), \
             patch("core.repo_cleaner.pydirectinput.press") as press, \
             patch.object(cleaner, "_find_game_window", return_value=object()):
            cleaner.start_cleaning("normal", "sell", 1, False, True)
        self.assertEqual(cleaner.stop_reason, "completed")
        self.assertEqual(cleaner.stats["total_detected"], 1)
        self.assertEqual(cleaner.stats["skipped"], 1)
        cleaner.ocr_engine.recognize_with_classification_from_lines.assert_not_called()
        press.assert_not_called()

    def test_stale_detail_gets_one_extra_frame_before_ocr(self):
        before = np.zeros((1080, 1920, 3), dtype=np.uint8)
        stale = before.copy()
        stale[380:430, 465:545] = 20
        fresh = stale.copy()
        fresh[770:968, 1070:1700] = 20
        repository = Mock(scale_x=1.0, scale_y=1.0)
        repository.validate_game_resolution.return_value = True
        repository.apply_filter.return_value = True
        repository._capture_game_window.side_effect = [before, stale, fresh]
        repository.extract_line_rois.side_effect = lambda image: [image[810:833, 1107:1700]] * 6
        cleaner = object.__new__(RepoCleaner)
        cleaner.settings = {}
        cleaner.repository_filter = repository
        cleaner.relic_detector = Mock()
        cleaner.relic_detector.detect_state.return_value = RELIC_STATE_LIGHT
        cleaner.relic_detector.detect_cursor.return_value = ((1035, 207, 99, 98), 99)
        cleaner.ocr_engine = Mock()
        cleaner.ocr_engine.recognize_with_classification_from_lines.return_value = {
            "success": True, "positive_count": 0, "negative_count": 0, "affixes": []}
        cleaner.preset_manager = Mock()
        cleaner.preset_manager.get_general_preset.return_value = {"affixes": []}
        cleaner.preset_manager.get_active_dedicated_presets.return_value = []
        cleaner.recorder = Mock()
        cleaner.qualified_relics = []
        bad = Mock(qualified=False, destructive_action_allowed=True)
        good = Mock(qualified=True, destructive_action_allowed=True)
        with patch("core.repo_cleaner.create_capture_session", return_value=None), \
             patch("core.repo_cleaner.time.sleep"), \
             patch("core.repo_cleaner.log_brightness_check"), \
             patch("core.repo_cleaner.log_match"), \
             patch("core.repo_cleaner.pydirectinput.press") as press, \
             patch.object(cleaner, "_find_game_window", return_value=object()), \
             patch.object(cleaner, "_match_affixes", side_effect=[bad, good]):
            cleaner.start_cleaning("normal", "sell", 2, False, True)
        self.assertEqual(repository._capture_game_window.call_count, 3)
        self.assertEqual(repository.extract_line_rois.call_count, 2)
        self.assertIs(repository.extract_line_rois.call_args_list[0].args[0], before)
        self.assertIs(repository.extract_line_rois.call_args_list[1].args[0], fresh)
        self.assertEqual([call.args[0] for call in press.call_args_list],
                         ["f", "3", "f"])

    def test_ambiguous_sale_does_not_retry_f_or_confirm_sale(self):
        frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
        repository = Mock(scale_x=1.0, scale_y=1.0)
        repository.validate_game_resolution.return_value = True
        repository.apply_filter.return_value = True
        repository._capture_game_window.side_effect = [frame, frame, frame]
        repository.extract_line_rois.return_value = [frame[810:833, 1107:1700]] * 6
        cleaner = object.__new__(RepoCleaner)
        cleaner.settings = {}
        cleaner.repository_filter = repository
        cleaner.relic_detector = Mock()
        cleaner.relic_detector.detect_state.return_value = RELIC_STATE_LIGHT
        cleaner.relic_detector.detect_cursor.return_value = ((925, 207, 99, 98), 99)
        cleaner.ocr_engine = Mock()
        cleaner.ocr_engine.recognize_with_classification_from_lines.return_value = {
            "success": True, "positive_count": 0, "negative_count": 0, "affixes": []}
        cleaner.preset_manager = Mock()
        cleaner.preset_manager.get_general_preset.return_value = {"affixes": []}
        cleaner.preset_manager.get_active_dedicated_presets.return_value = []
        cleaner.recorder = Mock()
        cleaner.qualified_relics = []
        bad = Mock(qualified=False, destructive_action_allowed=True)
        with patch("core.repo_cleaner.create_capture_session", return_value=None), \
             patch("core.repo_cleaner.time.sleep"), \
             patch("core.repo_cleaner.log_brightness_check"), \
             patch("core.repo_cleaner.log_match"), \
             patch("core.repo_cleaner.pydirectinput.press") as press, \
             patch.object(cleaner, "_find_game_window", return_value=object()), \
             patch.object(cleaner, "_match_affixes", return_value=bad):
            cleaner.start_cleaning("normal", "sell", 2, False, True)
        self.assertEqual(cleaner.stop_reason, "error")
        self.assertEqual(repository._capture_game_window.call_count, 3)
        self.assertEqual(cleaner.ocr_engine.recognize_with_classification_from_lines.call_count, 1)
        self.assertEqual([call.args[0] for call in press.call_args_list], ["f"])

    def test_active_outer_frame_beats_lower_sale_selection_frame(self):
        image = np.zeros((1080, 1920, 3), dtype=np.uint8)
        cv2.rectangle(image, (1479, 211), (1568, 300), (255, 255, 255), 2)
        cv2.rectangle(image, (1585, 207), (1683, 304), (255, 255, 255), 2)
        cursor, _ = RelicDetector().detect_cursor(image)
        self.assertIsNotNone(cursor)
        self.assertGreater(cursor[0], 1580)

    def test_later_dim_cursor_beats_brighter_earlier_selected_frame(self):
        image = np.zeros((1080, 1920, 3), dtype=np.uint8)
        cv2.rectangle(image, (925, 207), (1023, 304), (255, 255, 255), 2)
        cv2.rectangle(image, (1039, 211), (1128, 300), (160, 160, 160), 2)
        cursor, _ = RelicDetector().detect_cursor(image)
        self.assertIsNotNone(cursor)
        self.assertGreater(cursor[0], 1030)

    def test_lower_row_cursor_beats_farther_right_selected_frame(self):
        image = np.zeros((1080, 1920, 3), dtype=np.uint8)
        cv2.rectangle(image, (1695, 207), (1793, 304), (255, 255, 255), 2)
        cv2.rectangle(image, (929, 317), (1018, 406), (160, 160, 160), 2)
        cursor, _ = RelicDetector().detect_cursor(image)
        self.assertIsNotNone(cursor)
        self.assertGreater(cursor[1], 310)


if __name__ == "__main__":
    unittest.main()
