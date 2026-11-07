import json
import sys
from pathlib import Path
import random
import time
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.loadout_optimizer import load_catalog, optimize


def test_order_free_optimization():
    builds, vessels = load_catalog()
    build = next(b for b in builds if b['id'] == 'C17')
    with open('data/build_requirements.json', encoding='utf-8') as f:
        assert len(json.load(f)['builds']) == 207
    from core.relic_scoring import DEFAULT_SCORING
    normal = dict(id='build_C17_normal', affixes=build['common_required_affixes'],
                  affix_tiers={a:'core' for a in build['common_required_affixes']})
    deep = dict(id='build_C17_deepnight', affixes=[], affix_tiers={})
    presets = SimpleNamespace(normal_general={'affixes':[]},deepnight_general={'affixes':[]},
                              normal_dedicated={'build_C17_normal':normal},
                              deepnight_whitelist_dedicated={'build_C17_deepnight':deep})
    vessel=next(v for v in vessels if v['hero_en']=='Wylder')
    colors={'Red':'红','Blue':'蓝','Green':'绿','Yellow':'黄',
            'White (any colour)':'红'}
    nc=[colors[c.strip()] for c in vessel['normal_en'].split(',')]
    dc=[colors[c.strip()] for c in vessel['deep_en'].split(',')]
    needed=build['common_required_affixes']
    relics=[]
    for i in range(3):
        relics.append(dict(id=i+1,relic_type='normal',color=nc[i],
                           affixes=[needed[i % len(needed)]],name=''))
        relics.append(dict(id=i+4,relic_type='deepnight',color=dc[i],
                           affixes=[build['additional_any_of_affixes'][-1][0]],name=''))
    result=optimize(build,relics,vessels,presets,DEFAULT_SCORING,time_limit=2)
    assert result is not None and len(result['relics'])==6
    assert len({r['id'] for r in result['relics']})==6
    assert result['status']=='optimal'
    normal_only=optimize(build,relics,vessels,presets,DEFAULT_SCORING,
                         normal_preset_id='build_C17_normal',deepnight_preset_id='none',
                         time_limit=2)
    deep_only=optimize(build,relics,vessels,presets,DEFAULT_SCORING,
                       normal_preset_id='none',deepnight_preset_id='build_C17_deepnight',
                       time_limit=2)
    assert normal_only is not None and len(normal_only['relics'])==3
    assert all(r['relic_type']=='normal' for r in normal_only['relics'])
    assert deep_only is not None and len(deep_only['relics'])==3
    assert all(r['relic_type']=='deepnight' for r in deep_only['relics'])
    assert normal_only['score'] == optimize(
        build,[r for r in relics if r['relic_type']=='normal'],vessels,presets,
        DEFAULT_SCORING,normal_preset_id='build_C17_normal',deepnight_preset_id='none',
        time_limit=2)['score']
    assert deep_only['score'] == optimize(
        build,[r for r in relics if r['relic_type']=='deepnight'],vessels,presets,
        DEFAULT_SCORING,normal_preset_id='none',deepnight_preset_id='build_C17_deepnight',
        time_limit=2)['score']
    # A bad colour inventory cannot be accepted by a vessel.
    impossible=[dict(r,color='紫') for r in relics]
    assert optimize(build,impossible,vessels,presets,DEFAULT_SCORING) is None


def benchmark_inventory_size():
    builds,vessels=load_catalog()
    build=next(b for b in builds if b['id']=='C17')
    from core.relic_scoring import DEFAULT_SCORING
    all_affixes=list(build['common_required_affixes'])+build['additional_any_of_affixes'][-1]
    preset=dict(affixes=all_affixes,affix_tiers={a:'core' for a in all_affixes})
    presets=SimpleNamespace(normal_general={'affixes':[]},deepnight_general={'affixes':[]},
        normal_dedicated={'build_C17_normal':preset},
        deepnight_whitelist_dedicated={'build_C17_deepnight':preset})
    vessel=next(v for v in vessels if v['hero_en']=='Wylder')
    colors={'Red':'红','Blue':'蓝','Green':'绿','Yellow':'黄','White (any colour)':'红'}
    normal=[colors[c.strip()] for c in vessel['normal_en'].split(',')]
    deep=[colors[c.strip()] for c in vessel['deep_en'].split(',')]
    rng=random.Random(4)
    relics=[]
    for i in range(160):
        mode='normal' if i%2==0 else 'deepnight'
        palette=normal if mode=='normal' else deep
        relics.append(dict(id=i+1,relic_type=mode,color=palette[i%3],
            affixes=[all_affixes[i%len(all_affixes)],rng.choice(all_affixes)],name=''))
    start=time.perf_counter()
    result=optimize(build,relics,vessels,presets,DEFAULT_SCORING,time_limit=2)
    duration=time.perf_counter()-start
    assert result is not None
    print(f'160 relics / all vessels: {duration:.2f}s, score {result["score"]}')


if __name__ == '__main__':
    test_order_free_optimization()
    benchmark_inventory_size()
    print('loadout optimizer smoke test passed')
