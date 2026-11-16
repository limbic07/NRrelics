from types import SimpleNamespace
from unittest.mock import Mock

from core.loadout_optimizer import _prefilter_candidates, optimize


def cup(name, normal, deep='Red, Red, Red'):
    return dict(name_en=name,hero_en='Ironeye',normal_en=normal,deep_en=deep)


def item(i, color, affixes=(), mode='normal', official_id=None):
    return dict(id=i,color=color,affixes=list(affixes),relic_type=mode,official_id=official_id)


def test_colors_wildcards_and_inactive_mode():
    items=[item(1,'红'),item(2,'红'),item(3,'蓝'),item(4,'绿')]
    cups=[cup('impossible','Red, Red, Red'),
          cup('wild','Red, Red, White (any colour)','Yellow, Yellow, Yellow')]
    kept,vessels=_prefilter_candidates(items,cups,['normal'],[])
    assert vessels==[cups[1]] and kept==items  # zero-score fillers and wildcard colors survive
    items+= [item(5,'红',mode='deepnight'),item(6,'红',mode='deepnight'),item(7,'红',mode='deepnight')]
    assert _prefilter_candidates(items,cups,['normal','deepnight'],[])==([],[])


def test_conditions_and_official_identity():
    items=[item(i,'红',['需求']) for i in range(3)]+[item(i,'蓝',official_id=42 if i==3 else None) for i in range(3,6)]
    cups=[cup('red','Red, Red, Red'),cup('blue','Blue, Blue, Blue')]
    kept,vessels=_prefilter_candidates(items,cups,['normal'],[[dict(kind='official',id=42)]])
    assert vessels==[cups[1]] and [r['id'] for r in kept]==[3,4,5]
    kept,vessels=_prefilter_candidates(items,cups,['normal'],[[dict(kind='affix',name='需求')]])
    assert vessels==[cups[0]] and [r['id'] for r in kept]==[0,1,2]


def test_small_complete_search_matches_without_prefilter(monkeypatch):
    name='提升物理攻击力'
    p=SimpleNamespace(normal_general={'affixes':[]},deepnight_general={'affixes':[]},
                      normal_dedicated={'test':{'affixes':[name]}},deepnight_whitelist_dedicated={})
    items=[item(i,'红',[name] if i==0 else []) for i in range(4)]
    items += [item(i,'蓝',[]) for i in range(4,7)] + [item(7,'绿',[name])]
    cups=[cup('red','Red, Red, Red'),cup('blue','Blue, Blue, Blue'),cup('green','Green, Green, Green')]
    args=({'hero':'铁之眼'},items,cups,p,{})
    for groups in ([],[[dict(kind='affix',name=name)]]):
        kwargs=dict(normal_preset_id='test',deepnight_preset_id='none',page_size=30,min_ratio=0,
                    required_groups=groups,time_limit=2)
        filtered=optimize(*args,**kwargs)
        with monkeypatch.context() as context:
            context.setattr('core.loadout_optimizer._prefilter_candidates',lambda c,v,m,g:(c,v))
            original=optimize(*args,**kwargs)
        signature=lambda result:{(frozenset(r['id'] for r in s['relics']),s['score']) for s in result['solutions']}
        assert signature(filtered)==signature(original)
        assert filtered['score']==original['score'] and not filtered['has_more']


def test_completion_flushes_live_pruning():
    from ui.pages.page_relics import RelicPage
    for requested,error,count,more,expected in [
        (False,False,300,True,True), (False,True,300,True,True),
        (False,False,20,False,True), (True,True,20,True,True)]:
        page=SimpleNamespace(worker=Mock(),deep_search=True,stop_search=Mock(),
            deep_dialog=Mock(),optimization_mode=Mock(),solve=Mock(),next_results=Mock(),deep_stop_requested=requested,
            search_error=error,page_offset=count,deep_limit_value=300,deep_more=more,_update_deep_resume=Mock())
        RelicPage._search_finished(page)
        assert page.deep_dialog.prune_dominated.called==expected
        if expected and not requested and not error and more:
            page.deep_dialog.prune_dominated.assert_called_once_with('达到搜索上限')


def test_resume_excludes_previous_combinations_and_keeps_original_threshold():
    name='提升物理攻击力'
    p=SimpleNamespace(normal_general={'affixes':[]},deepnight_general={'affixes':[]},
                      normal_dedicated={'test':{'affixes':[name]}},deepnight_whitelist_dedicated={})
    args=({'hero':'铁之眼'},[item(i,'红',[name] if i<2 else []) for i in range(5)],
          [cup('red','Red, Red, Red')],p,{})
    kwargs=dict(normal_preset_id='test',deepnight_preset_id='none',min_ratio=.5,time_limit=2)
    original=optimize(*args,**kwargs,page_size=30)
    first=optimize(*args,**kwargs,page_size=2)
    excluded=[sorted(r['id'] for r in s['relics']) for s in first['solutions']]
    resumed=optimize(*args,**kwargs,page_size=30,excluded_combinations=excluded,anchor_score=first['score'])
    keys=lambda solutions:{frozenset(r['id'] for r in s['relics']) for s in solutions}
    assert not keys(first['solutions']) & keys(resumed['solutions'])
    assert keys(first['solutions']+resumed['solutions'])==keys(original['solutions'])
    assert resumed['min_score']==original['min_score'] and resumed['score']==original['score']
