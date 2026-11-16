from types import SimpleNamespace
import pytest
from core.loadout_metrics import Metrics

POISON_ROT = '周围人物陷入中毒、腐败时，能提升攻击力'
STATUS = '出现异常状态量表时，能缓慢提升攻击力'
COUNTER = '防御反击成功时，能依照自己目前的血量提升伤害'
DETECTORS = ['提升物理攻击力', '强化防御反击', '对陷入中毒的敌人，能强化攻击',
             '对陷入猩红腐败的敌人，能强化攻击', '对陷入冻伤的敌人，能强化攻击']


def metrics(names, officials=None):
    p = SimpleNamespace(normal_general={'affixes': []}, deepnight_general={'affixes': []},
                        normal_dedicated={'test': dict(name='铁之眼｜测试',affixes=names,
                            official_scores=officials or {})}, deepnight_whitelist_dedicated={})
    return Metrics(p, {}, 'test', 'none', '铁之眼')


def evaluate(m, names, official=None):
    return m.evaluate(dict(relics=[dict(relic_type='normal',affixes=names,
                                      official_id=official,affix_points={})]))


def test_secondary_bonuses_do_not_detect_scenes_even_on_officials():
    for m in (metrics(['提升物理攻击力',POISON_ROT,COUNTER]),
              metrics(['提升物理攻击力'],{'103':10,'98':10})):
        assert all(not any(key in label for key in ('中毒目标','腐败目标','防御反击'))
                   for label,_ in m.scenarios)
        assert evaluate(m,[POISON_ROT,COUNTER])['damage'] == [0.0]*len(m.scenarios)


def test_poison_rot_bonus_only_in_existing_target_scenes():
    m=metrics(DETECTORS,{'103':10})
    result=evaluate(m,[POISON_ROT],103)
    assert not result['pending'] and result['functions']==0
    for (label,_),value in zip(m.scenarios,result['damage']):
        expected=12 if '中毒目标' in label or '腐败目标' in label else 0
        assert value==pytest.approx(expected)
    # An ordinary relic cannot borrow eligibility from the official score.
    assert evaluate(m,[POISON_ROT])['damage']==[0.0]*len(m.scenarios)


def test_counter_bonus_only_in_counter_scenes_and_multiplies():
    m=metrics(DETECTORS,{'98':10})
    result=evaluate(m,[COUNTER],98)
    for (label,_),value in zip(m.scenarios,result['damage']):
        assert value==pytest.approx(65 if label.startswith('防御反击／') else 0)
    combined=evaluate(m,[COUNTER,'强化防御反击'],98)
    assert all(value==pytest.approx(94.7) for (label,_),value in zip(m.scenarios,combined['damage'])
               if label.startswith('防御反击／'))


def test_status_bonus_is_universal_and_obeys_eligibility():
    m=metrics(DETECTORS+[STATUS])
    result=evaluate(m,[STATUS])
    assert all(v==pytest.approx(22.5) for v in result['damage'])
    assert result['pending']==[] and result['functions']==0
    inactive=metrics(DETECTORS)
    assert evaluate(inactive,[STATUS])['damage']==[0.0]*len(inactive.scenarios)
    official=metrics(DETECTORS,{'111':10})
    assert all(v==pytest.approx(22.5) for v in evaluate(official,[STATUS],111)['damage'])


def test_three_bonuses_multiply_in_their_own_scopes():
    m=metrics(DETECTORS+[POISON_ROT,COUNTER,STATUS])
    result=evaluate(m,[POISON_ROT,COUNTER,STATUS])
    for (label,_),value in zip(m.scenarios,result['damage']):
        multiplier=1.225
        if '中毒目标' in label or '腐败目标' in label:multiplier*=1.12
        if label.startswith('防御反击／'):multiplier*=1.65
        assert value==pytest.approx((multiplier-1)*100)


def test_generic_branches_coexist_with_specialized_and_inherit_targets():
    names=DETECTORS+['提升战技攻击力','强化魔法','强化祷告','提升属性攻击力',
                     '提升魔力属性攻击力','强化重力的魔法','强化野兽的祷告',STATUS]
    m=metrics(names);scenes=dict(m.scenarios)
    for branch in ('通用战技','通用法术','通用属性祷告'):
        for target in ('无指定目标状态','中毒目标','腐败目标','冻伤目标'):
            assert f'{branch}／{target}／基础' in scenes
    assert any(label.startswith('物理战技／') for label in scenes)
    assert any(label.startswith('属性战技／') for label in scenes)
    assert any(label.startswith('法术／重力／') for label in scenes)
    assert any(label.startswith('祷告／野兽／') for label in scenes)
    assert scenes['通用法术／无指定目标状态／基础']=={'spell','魔力','element','all',''}
    assert scenes['通用属性祷告／无指定目标状态／基础']=={'prayer','element','all',''}
    result=evaluate(m,names)
    values=dict(zip(scenes,result['damage']))
    assert values['通用法术／无指定目标状态／基础']==pytest.approx((1.05*1.045*1.05*1.225-1)*100)
    assert values['通用属性祷告／中毒目标／基础']==pytest.approx((1.05*1.05*1.225*1.1-1)*100)
    assert values['通用战技／无指定目标状态／基础']==pytest.approx((1.15*1.225-1)*100)
    inactive=metrics(['强化重力的魔法','强化野兽的祷告'])
    assert not any(label.startswith(('通用法术','通用属性祷告','通用战技')) for label,_ in inactive.scenarios)


def test_negative_membership_uses_tiers_including_zero_not_point_sign():
    native='受到损伤时，会累积中毒量表'
    harmful='受到损伤时，会累积出血量表'
    positive='减少专注值消耗'
    p=SimpleNamespace(normal_general={'affixes':[]},deepnight_general={'affixes':[]},
        normal_dedicated={'n':{'affixes':[positive],'affix_tiers':{positive:'negligible'}}},
        deepnight_whitelist_dedicated={'d':{'affixes':[positive],'affix_tiers':{positive:'negligible'},
            'negative_tiers':{harmful:'negligible'}}})
    m=Metrics(p,{},'n','d','铁之眼')
    def result(names,mode='deepnight',points=None):
        return m.evaluate({'relics':[{'relic_type':mode,'affixes':names,'affix_points':points or {}}]})
    assert result([native,harmful,positive])['negative_terms']=={native:1,harmful:1,positive:1}
    assert result([positive],'normal')['negative_terms']=={positive:1}
    m=Metrics(p,{'deepnight':{'negative':{'negligible':99}}},'n','d','铁之眼')
    assert result([positive],'normal')['negative_terms']=={positive:1}
    assert positive not in m.allowed['normal']
    p.deepnight_whitelist_dedicated['d']['negative_tiers'][native]='bonus'
    p.deepnight_whitelist_dedicated['d']['affix_tiers'][positive]='secondary'
    m=Metrics(p,{},'n','d','铁之眼')
    assert result([native,harmful,positive],points={native:-2})['negative_terms']=={harmful:1}
    assert positive in result([positive])['functional_terms']


def test_zero_point_negative_identity_and_count_affect_dominance():
    from core.loadout_metrics import dominates
    p=SimpleNamespace(normal_general={'affixes':[]},deepnight_general={'affixes':[]},
        normal_dedicated={},deepnight_whitelist_dedicated={'d':{'affixes':[],
            'negative_tiers':{'受到损伤时，会累积出血量表':'negligible'}}})
    m=Metrics(p,{},'none','d','铁之眼')
    def row(names):
        return dict(score=20,metrics=m.evaluate({'relics':[{'relic_type':'deepnight','affixes':names}]}))
    bleed='受到损伤时，会累积出血量表';poison='受到损伤时，会累积中毒量表'
    clean,one,two,other=row([]),row([bleed]),row([bleed,bleed]),row([poison])
    assert dominates(clean,one) and dominates(one,two)
    assert not dominates(one,other) and not dominates(other,one)
    assert one['metrics']['negatives']==1 and two['metrics']['negative_terms'][bleed]==2


def test_survival_uses_actual_effects_and_separates_physical_element_and_blue():
    m=metrics(['血量偏低时，能提升减伤率'])  # Only blue tear requires preset approval.
    names=['生命力+1','生命力+2','生命力+3','提升血量上限',
           '每次打倒大教堂的强敌，能提升血量上限','提升物理减伤率+1',
           '提升属性减伤率+2','血量偏低时，能提升减伤率',
           '减伤率降低时，偶尔会让敌人攻击失效']
    value=evaluate(m,names)
    hp=1.02*1.04*1.06*1.10*1.075
    assert value['survival']==pytest.approx({
        'survival_physical':100*(hp/.895/.8-1),
        'survival_element':100*(hp/.88/.8-1),
        'survival_physical_blue':100*(hp/.895/.8/.84-1),
        'survival_element_blue':100*(hp/.88/.8/.84-1)})
    assert value['functions']==0 and not value['pending']
    assert all(v==0 for v in value['damage'])
    assert evaluate(m,['提升属性减伤率'])['survival']['survival_element']==pytest.approx(100*(1/.94-1))
    inactive=metrics([])
    result=evaluate(inactive,names)
    assert set(result['survival'])=={'survival_physical','survival_element'}
    assert result['survival']['survival_physical']==pytest.approx(value['survival']['survival_physical'])
    assert not any(tag=='blue_tear' for _,tag,_ in result['active_effects'])
    assert set(inactive.survival_scenarios)==set(result['survival'])


def test_specific_element_mitigation_is_ignored_even_if_effective():
    names=[f'提升{element}属性减伤率{suffix}' for element in ('魔力','火','雷','圣') for suffix in ('','+1','+2')]
    m=metrics(names)
    value=evaluate(m,names)
    assert not value['active_effects'] and not value['pending']
    assert all(v==0 for v in value['survival'].values())


def test_new_damage_and_function_classification_and_positive_negatives():
    attack='受到攻击时，能提升攻击力';holy='出击时的武器，附加圣属性攻击力'
    assert evaluate(metrics([]),[attack,holy])['active_effects']==[]
    result=evaluate(metrics([attack,holy]),[attack,holy])
    assert result['damage']==pytest.approx([15]) and result['functional_terms']=={holy:1}
    native='降低物理减伤率';converted='降低生命力、感应'
    p=SimpleNamespace(normal_general={},deepnight_general={},normal_dedicated={},
        deepnight_whitelist_dedicated={'d':{'negative_tiers':{converted:'secondary'}}})
    m=Metrics(p,{},'none','d','铁之眼')
    result=m.evaluate({'relics':[{'relic_type':'deepnight','affixes':[native,converted,'提升血量上限']}]})
    assert result['negative_terms']=={native:1}
    assert result['functional_terms']=={converted:1}
    assert all(v==pytest.approx(10) for v in result['survival'].values())
    assert not result['pending']
