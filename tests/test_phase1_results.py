import sqlite3

from core.relic_inventory import RelicInventory
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


def test_inventory_keeps_identical_relics_as_distinct_scan_rows(tmp_path):
    db = RelicInventory(str(tmp_path / 'inventory.sqlite3'))
    item = {'mode': 'normal', 'color': '蓝', 'color_confidence': .92,
            'affixes': [{'cleaned_text': '甲'}], 'decision': '保留',
            'action': '保留未动', 'action_confirmed': True, 'owned_verified': True,
            'scoring_enabled': True, 'score': 12, 'score_details': [('甲', 12)],
            'effective_count': 1, 'preset_id': 'p', 'preset_name': '测试'}
    db.record('scan-a', 1, item, {'scoring': {}})
    db.record('scan-a', 2, item, {'scoring': {}})
    with sqlite3.connect(db.path) as connection:
        assert connection.execute('SELECT COUNT(*) FROM relics').fetchone()[0] == 2
        assert connection.execute('SELECT COUNT(*) FROM scans WHERE owned_verified=1').fetchone()[0] == 2


def test_read_only_rescan_reuses_each_owned_copy_once(tmp_path):
    db = RelicInventory(str(tmp_path / 'rescan.sqlite3'))
    item = {'mode': 'normal', 'color': '蓝', 'color_confidence': .92,
            'affixes': [{'cleaned_text': '甲'}], 'decision': '淘汰',
            'action': '保留未动', 'action_confirmed': True,
            'owned_verified': True, 'inventory_scan': True,
            'scoring_enabled': True, 'score': 3, 'score_details': [('甲', 3)],
            'effective_count': 1, 'preset_id': 'p', 'preset_name': '测试'}
    for scan in ('scan-a', 'scan-b'):
        db.record(scan, 1, item, {'scoring': {}})
        db.record(scan, 2, item, {'scoring': {}})
    with sqlite3.connect(db.path) as connection:
        assert connection.execute('SELECT COUNT(*) FROM relics').fetchone()[0] == 2
        assert connection.execute('SELECT COUNT(*) FROM scans').fetchone()[0] == 4
