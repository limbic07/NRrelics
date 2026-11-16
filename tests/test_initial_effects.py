from types import SimpleNamespace
import pytest
from core.loadout_optimizer import optimize
from core.relic_scoring import DEFAULT_SCORING

def names(kind):
    prefix='通过潜在能力，能比较容易找到' if kind=='武器池' else '出击时，武器'+kind+'改为'
    return prefix+'大剑',prefix+'刀'


@pytest.mark.parametrize('kind',['战技','魔法','祷告','武器池'])
@pytest.mark.parametrize('same_color',[False,True])
def test_only_first_initial_replacement_scores(kind,same_color):
    a,b = names(kind)
    relics=[dict(id=1,relic_type='normal',color='红',affixes=[a]),
            dict(id=2,relic_type='normal',color='红' if same_color else '蓝',affixes=[b]),
            dict(id=3,relic_type='normal',color='黄',affixes=[])]
    p={'affixes':[a,b],'affix_tiers':{a:'secondary',b:'core'}}
    presets=SimpleNamespace(normal_general=p,deepnight_general={},normal_dedicated={},deepnight_whitelist_dedicated={})
    v=dict(hero_en='Wylder',name_en='test',normal_en='Red, '+('Red' if same_color else 'Blue')+', Yellow',deep_en='Red, Red, Red')
    result=optimize({'hero':'追踪者'},relics,[v],presets,DEFAULT_SCORING,
                    normal_preset_id='general',deepnight_preset_id='none',max_alternatives=0,time_limit=10)
    assert result['score']==(10 if same_color else 6)
    assert result['relics'][0]['id']==(2 if same_color else 1)


@pytest.mark.parametrize('kind',['战技','魔法','祷告','武器池'])
@pytest.mark.parametrize('scored',[False,True])
def test_required_replacement_must_be_active_even_if_unscored(kind,scored):
    a,b=names(kind)
    relics=[dict(id=1,relic_type='normal',color='红',affixes=[a]),
            dict(id=2,relic_type='normal',color='蓝',affixes=[b]),
            dict(id=3,relic_type='normal',color='黄',affixes=['其他需求'])]
    presets=SimpleNamespace(normal_general={'affixes':[], 'affix_tiers':{b:'core'} if scored else {}},
        deepnight_general={},normal_dedicated={},deepnight_whitelist_dedicated={})
    cup=dict(hero_en='Wylder',name_en='fixed',normal_en='Red, Blue, Yellow',deep_en='Red, Blue, Yellow')
    kwargs=dict(normal_preset_id='general',deepnight_preset_id='none',max_alternatives=0,time_limit=2)
    def solve(groups):
        return optimize({'hero':'追踪者'},relics,[cup],presets,DEFAULT_SCORING,
                        required_groups=[[dict(kind='affix',name=n) for n in g] for g in groups],**kwargs)
    # An unscored left effect still covers the required right effect.
    unconstrained=solve([])
    assert unconstrained['score']==0
    assert unconstrained['relics'][1]['affix_points'].get(b,0)==0
    if kind=='武器池':
        from core.loadout_metrics import Metrics
        evaluated=Metrics(presets,{},'general','none','追踪者').evaluate(unconstrained)
        assert b not in evaluated['functional_terms']
    assert solve([[b]]) is None
    assert solve([[b,'其他需求']]) is not None  # OR alternatives remain usable.
    cup['normal_en']='Blue, Red, Yellow'
    result=solve([[b]])
    assert result is not None and result['score']==(10 if scored else 0)
    assert result['relics'][0]['initial_effect_status'][b]=='生效'
    assert '被左侧覆盖' in result['relics'][1]['initial_effect_status'][a]
    assert solve([[a],[b]]) is None  # Two different winners of one kind are impossible.
    # Same-color slots can be reordered to satisfy the condition.
    relics[1]['color']='红';cup['normal_en']='Red, Red, Yellow'
    result=solve([[b]])
    assert result['relics'][0]['id']==2
    relics[0]['affixes']=[b]
    assert solve([[b],[b]]) is None  # Two copies still provide only one active instance.


@pytest.mark.parametrize('kind',['战技','魔法','祷告','武器池'])
def test_normal_replacement_covers_deep_required_replacement(kind):
    a,b=names(kind)
    relics=[dict(id=i,relic_type='normal' if i<3 else 'deepnight',color='红',
                 affixes=[a] if i==0 else [b] if i==3 else []) for i in range(6)]
    p=SimpleNamespace(normal_general={'affixes':[]},deepnight_general={'affixes':[b]},
                      normal_dedicated={},deepnight_whitelist_dedicated={})
    cup=dict(hero_en='Wylder',name_en='both',normal_en='Red, Red, Red',deep_en='Red, Red, Red')
    result=optimize({'hero':'追踪者'},relics,[cup],p,DEFAULT_SCORING,normal_preset_id='general',
                    deepnight_preset_id='general',required_groups=[[dict(kind='affix',name=b)]],
                    max_alternatives=0,time_limit=2)
    assert result is None


def test_different_override_kinds_can_all_satisfy_required_groups():
    terms=[names(k)[1] for k in ('战技','魔法','祷告','武器池')]
    relics=[dict(id=i,relic_type='normal',color='红',affixes=affixes)
            for i,affixes in enumerate([terms[:2],terms[2:],[]])]
    p=SimpleNamespace(normal_general={'affixes':[]},deepnight_general={},normal_dedicated={},deepnight_whitelist_dedicated={})
    cup=dict(hero_en='Wylder',name_en='independent',normal_en='Red, Red, Red',deep_en='Red, Red, Red')
    result=optimize({'hero':'追踪者'},relics,[cup],p,DEFAULT_SCORING,normal_preset_id='general',
                    deepnight_preset_id='none',required_groups=[[dict(kind='affix',name=n)] for n in terms],
                    max_alternatives=0,time_limit=2)
    assert result is not None
    assert all(status=='生效' for r in result['relics'] for status in r['initial_effect_status'].values())
