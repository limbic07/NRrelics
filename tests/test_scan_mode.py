from types import SimpleNamespace
from unittest.mock import Mock, patch

import numpy as np

from core.repo_cleaner import RepoCleaner
from core.relic_detector import RELIC_STATE_LIGHT


def test_scan_records_rejected_relic_without_game_action():
    frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
    cleaner = object.__new__(RepoCleaner)
    cleaner.settings = {'scoring': {'enabled': True}}
    cleaner.repository_filter = Mock(scale_x=1.0, scale_y=1.0)
    cleaner.repository_filter.validate_game_resolution.return_value = True
    cleaner.repository_filter.apply_filter.return_value = True
    cleaner.repository_filter._capture_game_window.return_value = frame
    cleaner.repository_filter.extract_line_rois.return_value = [frame] * 6
    cleaner.relic_detector = Mock()
    cleaner.relic_detector.detect_state.return_value = RELIC_STATE_LIGHT
    cleaner.relic_detector._has_official_marker.return_value = False
    cleaner.ocr_engine = Mock()
    cleaner.ocr_engine.recognize_with_classification_from_lines.return_value = {
        'success': True, 'positive_count': 1, 'negative_count': 0,
        'affixes': [{'cleaned_text': '甲', 'is_positive': True}]}
    cleaner.preset_manager = Mock()
    cleaner.preset_manager.get_general_preset.return_value = {'affixes': []}
    cleaner.preset_manager.get_active_dedicated_presets.return_value = []
    cleaner.recorder = Mock()
    cleaner.inventory = Mock()
    candidate = SimpleNamespace(score=3, score_details=[('甲', 3)],
                                effective_count=1, preset_id='p', preset_name='测试')
    match = SimpleNamespace(qualified=False, destructive_action_allowed=True,
                            best_match=None, candidate_match=candidate,
                            candidate_failure_reasons=['有效词条不足'],
                            uncertainty_reasons=[])
    with patch('core.repo_cleaner.create_capture_session', return_value=None), \
         patch('core.repo_cleaner.time.sleep'), \
         patch('core.repo_cleaner.log_brightness_check'), \
         patch('core.repo_cleaner.log_match'), \
         patch('core.repo_cleaner.recognize_color', return_value=('蓝', .9)), \
         patch('core.repo_cleaner.pydirectinput.press') as press, \
         patch.object(cleaner, '_find_game_window', return_value=object()), \
         patch.object(cleaner, '_match_affixes', return_value=match):
        cleaner.start_cleaning('normal', 'scan', 1, False, True)
    assert cleaner.stop_reason == 'completed'
    assert cleaner.results[0]['decision'] == '淘汰'
    assert cleaner.results[0]['action'] == '保留未动'
    assert cleaner.results[0]['owned_verified'] is True
    cleaner.inventory.record.assert_called_once()
    press.assert_not_called()
