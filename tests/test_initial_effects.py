from types import SimpleNamespace
import pytest
from core.loadout_optimizer import optimize
from core.relic_scoring import DEFAULT_SCORING

@pytest.mark.parametrize('kind',['战技','魔法','祷告'])
@pytest.mark.parametrize('same_color',[False,True])
def test_only_first_initial_replacement_scores(kind,same_color):
    a,b = '出击时，武器'+kind+'改为甲','出击时，武器'+kind+'改为乙'
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
