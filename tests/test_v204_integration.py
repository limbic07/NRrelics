from unittest.mock import Mock,patch
from core.relic_matcher import preset_configuration_errors
from core.relic_scoring import normalize_scoring
from core.shop_automation import ShopAutomation

def test_scoring_preflight_ignores_legacy_required_groups():
 p={'name':'graded','affixes':['a'],'affix_tiers':{'a':'core'},'required_affix_groups':[['old']]}
 assert not preset_configuration_errors(None,[p],scoring_config={'enabled':True})
 assert preset_configuration_errors(None,[p],scoring_config={'enabled':False})

def test_scoring_preflight_validates_grades_and_exclusions():
 p={'name':'bad','affixes':['a'],'affix_tiers':{'a':'invalid'}}
 assert preset_configuration_errors(None,[p],scoring_config={'enabled':True})
 p={'name':'conflict','affixes':['a'],'affix_tiers':{'a':'core'},'excluded_affixes':['a']}
 assert preset_configuration_errors(None,[p],scoring_config={'enabled':True})

def test_shop_constructor_and_preflight_stop_preserve_callback():
 shop=ShopAutomation(Mock(),Mock(),Mock(),{})
 shop._load_presets=Mock(return_value=(None,[{'name':'invalid','affixes':['a'],'required_affix_groups':[['missing']]}],None))
 shop._enter_merchant_interface=Mock()
 callback=Mock()
 with patch('core.shop_automation.keyboard'):
  shop.start_shopping('normal','new',10,True,triple_callback=callback)
 assert shop.stop_reason=='error'
 shop._enter_merchant_interface.assert_not_called()
 assert shop.triple_callback is callback
