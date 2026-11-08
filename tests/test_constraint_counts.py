from types import SimpleNamespace
from itertools import combinations_with_replacement
from core.loadout_optimizer import optimize
from core.relic_scoring import DEFAULT_SCORING


def solve(affixes, groups):
    relics = [dict(id=i+1, relic_type='normal', color='红', affixes=x) for i,x in enumerate(affixes)]
    presets = SimpleNamespace(normal_general={'affixes': []},deepnight_general={'affixes': []},
                              normal_dedicated={},deepnight_whitelist_dedicated={})
    vessel = dict(hero_en='Wylder',name_en='test',normal_en='Red, Red, Red',deep_en='Blue, Blue, Blue')
    return optimize({'hero':'追踪者'},relics,[vessel],presets,DEFAULT_SCORING,
                    normal_preset_id='general',deepnight_preset_id='none',
                    required_groups=[[dict(kind='affix',name=x) for x in g] for g in groups],
                    max_alternatives=0,time_limit=5)


def test_all_example_pairs():
    allowed = {('a','a'),('a','b'),('a','c'),('a','d'),('b','b'),('b','c'),('b','d'),('c','d')}
    for pair in combinations_with_replacement('abcd',2):
        assert bool(solve([[pair[0]],[pair[1]],[]],[['a','b','c'],['a','b','d']])) == (pair in allowed)


def test_single_occurrence_cannot_cover_two_groups():
    assert solve([['a'],[],[]],[['a'],['a']]) is None
    assert solve([['a'],['a'],[]],[['a'],['a']]) is not None


def test_distinct_affixes_on_same_relic_can_cover_two_groups():
    assert solve([['a','c'],[],[]],[['a','c'],['a','d']]) is not None
