import unittest
from unittest.mock import Mock, patch

from core.relic_matcher import match_relic, preset_configuration_errors


class PresetValidationTests(unittest.TestCase):
    def setUp(self):
        self.general = {'affixes': ['shared']}
        self.preset = {'name': 'Duchess', 'affixes': ['skill'],
                       'required_affix_groups': [['shared']]}

    def test_removed_inherited_requirement_names_preset_and_affix(self):
        self.general['affixes'] = []
        errors = preset_configuration_errors(self.general, [self.preset])
        self.assertEqual(len(errors), 1)
        self.assertIn('Duchess', errors[0])
        self.assertIn('shared', errors[0])
        observation = {'success': True, 'affixes': [
            {'cleaned_text': 'other', 'is_positive': True}]}
        result = match_relic(observation, self.general, [self.preset])
        self.assertFalse(result.destructive_action_allowed)
        self.assertEqual(result.uncertainty_reasons, errors)

    def test_enabled_general_requirement_valid_disabled_general_invalid(self):
        self.assertEqual(preset_configuration_errors(self.general, [self.preset]), [])
        self.general['is_active'] = False
        self.assertTrue(preset_configuration_errors(self.general, [self.preset]))
        self.preset['affixes'].append('shared')
        self.assertEqual(preset_configuration_errors(self.general, [self.preset]), [])

    def test_inactive_invalid_preset_is_ignored(self):
        self.preset.update(is_active=False, required_affix_groups=[[]])
        self.assertEqual(preset_configuration_errors(self.general, [self.preset]), [])

    def test_invalid_shop_configuration_stops_before_game_interaction(self):
        from core.shop_automation import ShopAutomation

        shop = object.__new__(ShopAutomation)
        shop.settings = {}
        shop.repo_filter = Mock()
        shop.qualified_relics = []
        shop._load_presets = Mock(return_value=({}, [self.preset], None))
        shop._enter_merchant_interface = Mock()
        log = Mock()
        with patch('core.shop_automation.keyboard'), patch('core.shop_automation.DEBUG_ENABLED', False):
            shop.start_shopping('normal', 'new', 10, True, log_callback=log)
        self.assertEqual(shop.stop_reason, 'error')
        self.assertFalse(shop.is_running)
        self.assertEqual(shop.stats['total_purchased'], 0)
        shop.repo_filter.refresh_window_info.assert_not_called()
        shop._enter_merchant_interface.assert_not_called()
        self.assertTrue(any('Duchess' in call.args[0] for call in log.call_args_list))


if __name__ == '__main__':
    unittest.main()
