import unittest
from types import SimpleNamespace
from unittest.mock import Mock, call, patch

from core.relic_matcher import MatchResult, PresetMatch
from core.shop_automation import ShopAutomation, _ShopRoundTiming


class ShopTimingTests(unittest.TestCase):
    def test_relic_action_keeps_original_hold_and_shortens_release_wait(self):
        events = []
        with patch('core.shop_automation.pydirectinput.keyDown',
                   side_effect=lambda key, **kwargs: events.append(('down', key, kwargs))), \
             patch('core.shop_automation.pydirectinput.keyUp',
                   side_effect=lambda key, **kwargs: events.append(('up', key, kwargs))), \
             patch('core.shop_automation.time.sleep',
                   side_effect=lambda seconds: events.append(('sleep', seconds))):
            ShopAutomation._press_relic_action('right')

        self.assertEqual(events, [
            ('down', 'right', {'_pause': False}),
            ('sleep', 0.1),
            ('up', 'right', {'_pause': False}),
            ('sleep', 0.08),
        ])

    def test_relic_action_releases_key_if_hold_is_interrupted(self):
        with patch('core.shop_automation.pydirectinput.keyDown') as down, \
             patch('core.shop_automation.pydirectinput.keyUp') as up, \
             patch('core.shop_automation.time.sleep', side_effect=RuntimeError('interrupted')):
            with self.assertRaises(RuntimeError):
                ShopAutomation._press_relic_action('3')
        down.assert_called_once_with('3', _pause=False)
        up.assert_called_once_with('3', _pause=False)

    def test_one_navigation_key_per_processed_relic_and_timing_breakdown(self):
        shop = object.__new__(ShopAutomation)
        shop.is_running = True
        shop.stats = {'total_purchased': 10, 'qualified': 0, 'unqualified': 0, 'sold': 0}
        shop.settings = {}
        shop.qualified_relics = []
        shop.ocr_debug_session = None
        shop.recorder = SimpleNamespace(record=Mock(return_value=True))
        observation = {'success': True, 'affixes': [], 'recognition_time': 0.0}
        shop.ocr_engine = SimpleNamespace(
            recognize_with_classification_from_lines=Mock(return_value=observation))
        shop._capture_shop_line_rois = Mock(return_value=[])
        qualified_preset = PresetMatch('one', 'preset', True, 2, [], [], [], [], [], False)
        qualified = MatchResult(True, False, qualified_preset, [qualified_preset], 0, True)
        unqualified = MatchResult(False, False, None, [], 0, True)
        shop._match_affixes = Mock(side_effect=[qualified] + [unqualified] * 9)

        timing = _ShopRoundTiming(enabled=True)
        with patch.object(shop, '_press_relic_action') as action:
            shop._process_purchased_relics('normal', True, None, [], None,
                                           Mock(), None, timing)

        self.assertEqual(action.call_args_list, [call('right')] + [call('3')] * 9)
        self.assertEqual(timing.items, 10)
        self.assertIn('截图', timing.summary(10, True))
        self.assertIn('筛选按键', timing.summary(10, True))
        self.assertEqual(shop.stats['qualified'], 1)
        self.assertEqual(shop.stats['sold'], 9)

    def test_timing_off_does_not_measure(self):
        timing = _ShopRoundTiming(enabled=False)
        with patch('core.shop_automation.time.perf_counter') as clock:
            with timing.measure('ocr'):
                pass
        clock.assert_not_called()
        self.assertEqual(timing.parts, {})

    def test_round_summary_follows_timing_setting(self):
        for enabled in (False, True):
            with self.subTest(enabled=enabled):
                shop = object.__new__(ShopAutomation)
                shop.settings = {'timing_debug': enabled}
                shop.repo_filter = SimpleNamespace(
                    settings=None, refresh_window_info=Mock(),
                    validate_game_resolution=Mock(return_value=True))
                shop.qualified_relics = []
                shop._load_presets = Mock(return_value=(None, [], None))
                shop._enter_merchant_interface = Mock(return_value=True)
                shop._find_relic = Mock(return_value=True)

                def purchase(*args):
                    shop.stats['total_purchased'] += 10
                    return True

                def process(*args):
                    args[-1].items = 10

                shop._execute_first_purchase = Mock(side_effect=purchase)
                shop._process_purchased_relics = Mock(side_effect=process)
                messages = []
                with patch('core.shop_automation.create_capture_session', return_value=None), \
                     patch('core.shop_automation.keyboard.add_hotkey'), \
                     patch('core.shop_automation.keyboard.remove_hotkey'), \
                     patch('core.shop_automation.time.sleep'), \
                     patch('core.shop_automation.pydirectinput.press',
                           side_effect=lambda key: setattr(shop, 'is_running', False)), \
                     patch('core.shop_automation.DEBUG_ENABLED', False):
                    shop.start_shopping('normal', 'new', 0, True,
                                        log_callback=lambda message, level: messages.append(message))

                summaries = [message for message in messages if message.startswith('[性能]')]
                self.assertEqual(len(summaries), int(enabled))
                if enabled:
                    self.assertIn('第 1-10 个遗物（完成）', summaries[0])
                    self.assertIn('购买', summaries[0])
                    self.assertIn('确认', summaries[0])


if __name__ == '__main__':
    unittest.main()
