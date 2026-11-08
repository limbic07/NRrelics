
from core.relic_matcher import match_relic


def test_rejected_relic_keeps_highest_candidate_and_reason():
    observation = {'success': True, 'affixes': [
        {'cleaned_text': '甲', 'is_positive': True},
        {'cleaned_text': '乙', 'is_positive': True},
    ]}
    general = {'id': 'general', 'name': '通用', 'affixes': ['甲'],
               'affix_tiers': {'甲': 'core'}}
    dedicated = [{'id': 'build', 'name': '流派', 'affixes': ['甲', '乙'],
                  'affix_tiers': {'甲': 'core', '乙': 'bonus'}, 'is_active': True}]
    scoring = {'enabled': True}
    result = match_relic(observation, general, dedicated, threshold=3,
                         scoring_config=scoring)
    assert not result.qualified
    assert result.best_match is None
    assert result.candidate_match.preset_id == 'build'
    assert any('有效词条不足' in reason for reason in result.candidate_failure_reasons)






def test_screening_result_does_not_write_inventory():
    from unittest.mock import Mock
    from core.repo_cleaner import RepoCleaner
    cleaner = RepoCleaner.__new__(RepoCleaner)
    cleaner.settings = {'scoring': {'enabled': False}}
    cleaner.stats = {'total_detected': 1}
    cleaner.results = []
    log, callback = Mock(), Mock()
    cleaner._publish_result('normal', None, None, '跳过', '无法确认', log, callback)
    assert cleaner.results[0]['decision'] == '无法确认'
    assert 'color' not in cleaner.results[0]
    callback.assert_called_once()
