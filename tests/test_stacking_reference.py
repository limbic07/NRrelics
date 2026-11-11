"""Reference stacking and user exceptions, including displayed contributions."""
from types import SimpleNamespace
import pytest
from core.loadout_optimizer import optimize, VAMP
from core.relic_scoring import DEFAULT_SCORING


def solve(normal, deep, required_groups=None):
    names = set(sum(normal + deep, []))
    preset = dict(affixes=list(names), affix_tiers={n: 'core' for n in names})
    presets = SimpleNamespace(normal_general={}, deepnight_general={},
        normal_dedicated={'n': preset}, deepnight_whitelist_dedicated={'d': preset})
    relics = [dict(id=i+1, relic_type=mode, color='红', affixes=a)
              for i, (mode, a) in enumerate(
                  [('normal', a) for a in normal] + [('deepnight', a) for a in deep])]
    vessel = dict(hero_en='Wylder', normal_en='Red,Red,Red', deep_en='Red,Red,Red',
                  name='test', name_en='test', name_zh='测试', id='test')
    result = optimize({'hero': '追踪者', 'id': 'test'}, relics, [vessel], presets,
        DEFAULT_SCORING, normal_preset_id='n', deepnight_preset_id='d', page_size=1, required_groups=required_groups)
    if result is None or not result['solutions']:
        return None
    best = result['solutions'][0]
    assert sum(r['score_contribution'] for r in best['relics']) == best['score']
    return best['score']


@pytest.mark.parametrize('name', ['提升物理攻击力+4', '提升大剑的攻击力',
    '强化卡利亚剑的魔法', '减少专注值消耗'])
def test_repeat_same_name(name):
    assert solve([[name]]*3, [[name]]*3) == 60


@pytest.mark.parametrize('name', ['提升血量上限','提升专注值上限','提升精力上限'])
def test_upper_limits_by_mode(name):
    assert solve([[name]]*3, [[name]]*3) == 40


@pytest.mark.parametrize('name', ['出击时，会持有召咒魂铃',
    '每次打倒黑夜入侵者，能提升攻击力','【女爵】提升技艺造成的伤害'])
def test_nonstacking(name):
    assert solve([[name]]*3, [[name]]*3) == 10


def test_vamp_and_tiers():
    assert solve([[VAMP[0]]]*3, [[VAMP[1]], [VAMP[2]], [VAMP[0]]]) == 20
    assert solve([['攻击命中时，能恢复精力']]*3,
                 [['攻击命中时，能恢复精力+1']]*3) == 20


def test_three_weapon_policy():
    a='装备三把以上类别为大剑的武器，能提升攻击力'
    b='装备三把以上类别为刀的武器，能提升攻击力'
    assert solve([[a]]*3, [[b]]*3) == 10


def test_negative_group_excludes_any_and_duplicates_are_idempotent():
    a, b = '提升物理攻击力+4', '提升大剑的攻击力'
    normal = [[a], [b], [], []]
    deep = [[], [], []]
    forbidden = dict(kind='affix', name=a, exclude=True)
    assert solve(normal, deep, [[forbidden]]) == 10
    assert solve(normal, deep, [[forbidden], [forbidden]]) == 10
    assert solve(normal, deep, [[forbidden, dict(kind='affix',name=b,exclude=True)]]) is None
    assert solve(normal, deep, [[dict(kind='affix',name=a)], [forbidden]]) is None


def test_mixed_group_rejected():
    with pytest.raises(ValueError, match='混合'):
        solve([[],[],[]], [[],[],[]], [[dict(kind='affix',name='a'),dict(kind='affix',name='b',exclude=True)]])
