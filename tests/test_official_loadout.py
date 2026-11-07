"""Regression checks for manual requirements and official whole-relic scores."""
from types import SimpleNamespace

from core.loadout_optimizer import optimize
from core.official_relics import load_official_relics
from core.relic_scoring import DEFAULT_SCORING


def _fixture():
    official = load_official_relics()[0]
    vessel = {'hero_en': 'Wylder', 'name_en': 'Test cup',
              'normal_en': 'White (any colour), White (any colour), White (any colour)',
              'deep_en': 'White (any colour), White (any colour), White (any colour)'}
    relics = [dict(id=1, relic_type='normal', color=official['color'],
                   affixes=official['affixes'], official_id=official['id'], name=official['name'])]
    relics += [dict(id=i, relic_type='normal', color='红', affixes=['测试词条'] if i == 2 else [],
                    name='') for i in (2, 3, 4)]
    relics += [dict(id=i, relic_type='deepnight', color='蓝', affixes=[], name='')
               for i in (5, 6, 7)]
    normal = {'affixes': ['测试词条'], 'affix_tiers': {'测试词条': 'core'},
              'official_scores': {str(official['id']): 30}}
    deep = {'affixes': []}
    presets = SimpleNamespace(normal_general={'affixes': []},
                              deepnight_general={'affixes': []},
                              normal_dedicated={'normal_test': normal},
                              deepnight_whitelist_dedicated={'deep_test': deep})
    kwargs = dict(normal_preset_id='normal_test', deepnight_preset_id='deep_test',
                  time_limit=2)
    return official, relics, [vessel], presets, kwargs


def test_official_score_and_ratio():
    official, relics, vessels, presets, kwargs = _fixture()
    result = optimize({'hero': '追踪者'}, relics, vessels, presets, DEFAULT_SCORING,
                      min_ratio=.75, **kwargs)
    assert result['score'] == 40
    assert result['min_score'] == 30
    assert sum(relic['score_contribution'] for relic in result['relics']) == result['score']
    assert [relic['slot_index'] for relic in result['relics'] if relic['relic_type']=='normal'] == [0,1,2]
    assert all(item['score'] >= 30 for item in result['alternatives'])
    assert any(r['official_id'] == official['id'] for r in result['relics'])


def test_manual_and_or_requirements_replace_default_build_rules():
    official, relics, vessels, presets, kwargs = _fixture()
    required = [[{'kind': 'official', 'id': official['id']}],
                [{'kind': 'affix', 'mode': 'normal', 'name': '测试词条'},
                 {'kind': 'affix', 'mode': 'deepnight', 'name': '另一词条'}]]
    result = optimize({'hero': '追踪者'}, relics, vessels, presets, DEFAULT_SCORING,
                      required_groups=required, max_alternatives=0, **kwargs)
    assert result['score'] == 40
    impossible = [[{'kind': 'affix', 'mode': 'deepnight', 'name': '不存在'}]]
    assert optimize({'hero': '追踪者'}, relics, vessels, presets, DEFAULT_SCORING,
                    required_groups=impossible, **kwargs) is None


def test_paged_results_are_ranked_and_continue_without_duplicates():
    official, relics, vessels, presets, kwargs = _fixture()
    first = optimize({'hero': '追踪者'}, relics, vessels, presets, DEFAULT_SCORING,
                     page_size=2, **kwargs)
    assert first['solutions'][0]['score'] == 40
    assert first['solutions'][0]['score'] >= first['solutions'][1]['score']
    assert first['has_more']
    second = optimize({'hero': '追踪者'}, relics, vessels, presets, DEFAULT_SCORING,
                      page_size=2, anchor_score=first['score'],
                      excluded_combinations=first['excluded_combinations'], **kwargs)
    assert all(item['score'] <= first['solutions'][-1]['score']
               for item in second['solutions'])
    assert not ({frozenset(r['id'] for r in item['relics']) for item in first['solutions']}
                & {frozenset(r['id'] for r in item['relics']) for item in second['solutions']})


def test_bundled_catalog_and_presets_are_complete():
    import json
    from core.utils import get_resource_path
    data = json.load(open(get_resource_path('data/default_presets.json'), encoding='utf-8'))
    assert len(load_official_relics()) == 118
    assert len(data['normal_dedicated']) == len(data['deepnight_whitelist_dedicated']) == 207
    assert sum(len(p.get('official_scores', {})) for p in data['normal_dedicated'].values()) == 1068
