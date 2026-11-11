"""Order-free relic optimization with user-defined AND/OR requirements."""
import itertools
import json
import math

import numpy as np

from core.official_relics import identify_official_relic
from core.relic_scoring import normalize_scoring, normalize_affix_tiers
from core.utils import get_resource_path

COLORS = {'Red': '红', 'Blue': '蓝', 'Green': '绿', 'Yellow': '黄'}
HEROES = {'追踪者':'Wylder','守护者':'Guardian','铁之眼':'Ironeye','女爵':'Duchess',
          '无赖':'Raider','复仇者':'Revenant','隐士':'Recluse','执行者':'Executor',
          '学者':'Scholar','送葬者':'Undertaker'}
# Same-name effects confirmed stackable in the 1.03.5 reference table.
REPEATABLE = {
    '减少专注值消耗',
    '减少专注值消耗+1',
    '减少专注值消耗+2',
    '出击时，会持有小型随身包包',
    '出击时，会持有振奋香',
    '受到损伤时，会累积催眠量表',
    '受到损伤时，会累积冻伤量表',
    '受到损伤时，会累积出血量表',
    '受到损伤时，会累积发狂量表',
    '强化卡利亚剑的魔法',
    '强化巨人火焰的祷告',
    '强化挖石的魔法',
    '强化狩猎神祇的祷告',
    '强化王城古龙信仰的祷告',
    '强化癫火的祷告',
    '强化祷告',
    '强化祷告+1',
    '强化祷告+2',
    '强化结晶人的魔法',
    '强化荆棘的魔法',
    '强化轻攻击的第一记攻击',
    '强化辉剑的魔法',
    '强化重力的魔法',
    '强化野兽的祷告',
    '强化防御反击',
    '强化防御反击+1',
    '强化防御反击+2',
    '强化隐形的魔法',
    '强化魔法',
    '强化魔法+1',
    '强化魔法+2',
    '强化黄金律法基本主义的祷告',
    '强化龙飨的祷告',
    '提升刀的攻击力',
    '提升双头剑的攻击力',
    '提升圣属性攻击力',
    '提升圣属性攻击力+1',
    '提升圣属性攻击力+2',
    '提升圣属性攻击力+3',
    '提升圣属性攻击力+4',
    '提升大剑的攻击力',
    '提升大槌的攻击力',
    '提升大矛的攻击力',
    '提升属性减伤率',
    '提升属性减伤率+1',
    '提升属性减伤率+2',
    '提升属性攻击力',
    '提升属性攻击力+1',
    '提升属性攻击力+2',
    '提升弓的攻击力',
    '提升戟的攻击力',
    '提升投掷壶的攻击力',
    '提升投掷壶的攻击力+1',
    '提升拳头的攻击力',
    '提升曲剑的攻击力',
    '提升火属性攻击力',
    '提升火属性攻击力+1',
    '提升火属性攻击力+2',
    '提升火属性攻击力+3',
    '提升火属性攻击力+4',
    '提升物理减伤率+1',
    '提升物理减伤率+2',
    '提升物理攻击力',
    '提升物理攻击力+1',
    '提升物理攻击力+2',
    '提升物理攻击力+3',
    '提升物理攻击力+4',
    '提升特大剑的攻击力',
    '提升特大武器的攻击力',
    '提升直剑的攻击力',
    '提升矛的攻击力',
    '提升短剑的攻击力',
    '提升雷属性攻击力',
    '提升雷属性攻击力+1',
    '提升雷属性攻击力+2',
    '提升雷属性攻击力+3',
    '提升雷属性攻击力+4',
    '提升魔力属性攻击力',
    '提升魔力属性攻击力+1',
    '提升魔力属性攻击力+2',
    '提升魔力属性攻击力+3',
    '提升魔力属性攻击力+4',
    '血量偏低时，能提升减伤率',
    '血量没有全满时，累积中毒量表',
    '血量没有全满时，累积猩红腐败量表',
    '降低对所有异常状态的抵抗力',
}
DEEP_REPEATABLE = {
    '提升专注值上限',
    '提升精力上限',
    '提升血量上限',
}

def _is_repeatable(mode, affix):
    return affix in REPEATABLE or (mode == "deepnight" and affix in DEEP_REPEATABLE)

VAMP = ('受到损伤的当下，能通过攻击恢复部分血量',
        '受到损伤的当下，能通过攻击恢复部分血量+1',
        '受到损伤的当下，能通过攻击恢复部分血量+2')


def _initial_kind(name):
    for kind in ('战技', '魔法', '祷告'):
        if name.startswith('出击时，武器' + kind + '改为'):
            return kind
    return None


def load_catalog():
    with open(get_resource_path('data/build_requirements.json'), encoding='utf-8') as f:
        builds = json.load(f)['builds']
    with open(get_resource_path('data/vessels.json'), encoding='utf-8') as f:
        vessels = json.load(f)
    return builds, vessels


def _slots(text):
    return [COLORS.get(part.strip(), '*') for part in text.split(',')]


def _score_map(preset, general, scoring, mode):
    inherited, _ = normalize_affix_tiers(general or {'affixes': []})
    local, _ = normalize_affix_tiers(preset or {'affixes': []})
    tiers = {**inherited, **local}
    for name in (preset or {}).get('excluded_affixes', []):
        tiers.pop(name, None)
    return {name: (scoring[mode]['positive'][tier] if tier in scoring[mode]['positive']
                   else scoring['deepnight']['negative'][tier]) for name, tier in tiers.items()}


def _find_preset(presets, mode, identifier):
    general = presets.normal_general if mode == 'normal' else presets.deepnight_general
    dedicated = (presets.normal_dedicated if mode == 'normal'
                 else presets.deepnight_whitelist_dedicated)
    return general if identifier in (None, 'general') else dedicated.get(identifier)


def _satisfies(relic, entry):
    if entry.get('kind') == 'official':
        return (relic['relic_type'] == 'normal' and
                relic.get('official_id') == entry.get('id'))
    return (entry.get('kind') == 'affix' and
            entry.get('name') in relic['affixes'])


def optimize(build, relics, vessels, presets, scoring_config, *,
             normal_preset_id=None, deepnight_preset_id=None,
             required_groups=None, min_ratio=0.75, max_alternatives=5,
             time_limit=5, page_size=None, excluded_combinations=(), anchor_score=None):
    """Find the optimum and alternatives meeting a fraction of its score.

    Requirement groups are joined by AND; entries within a group use OR.
    Legacy build requirements do not constrain this search.
    """
    if page_size is None:
        # Keep the legacy return shape while using the same proven K-best search.
        page = optimize(
            build, relics, vessels, presets, scoring_config,
            normal_preset_id=normal_preset_id, deepnight_preset_id=deepnight_preset_id,
            required_groups=required_groups, min_ratio=min_ratio, time_limit=time_limit,
            page_size=max(0, max_alternatives) + 1)
        if not page or not page['solutions']:
            return None
        best, *alternatives = page['solutions']
        return dict(best, alternatives=alternatives, min_ratio=min_ratio,
                    min_score=page['min_score'], normal_preset_id=normal_preset_id,
                    deepnight_preset_id=deepnight_preset_id)
    if not 0 <= min_ratio <= 1:
        raise ValueError('最低比例须在 0% 到 100% 之间')
    from scipy.optimize import Bounds, LinearConstraint, milp
    from scipy.sparse import csr_matrix, vstack
    groups = required_groups or []
    if not isinstance(groups, list) or any(not isinstance(g, list) or not g for g in groups):
        raise ValueError('必备条件格式无效')
    if any(len({bool(e.get('exclude', False)) for e in g}) != 1 for g in groups):
        raise ValueError('同一条件组不能混合正向和反向条件')
    excluded_entries = [e for g in groups for e in g if e.get('exclude', False)]
    groups = [g for g in groups if not g[0].get('exclude', False)]
    scoring = normalize_scoring(scoring_config)
    normal_preset_id = normal_preset_id or 'build_' + build['id'] + '_normal'
    deepnight_preset_id = deepnight_preset_id or 'build_' + build['id'] + '_deepnight'
    active_modes = [mode for mode, identifier in
                    (('normal', normal_preset_id), ('deepnight', deepnight_preset_id))
                    if identifier != 'none']
    if not active_modes:
        raise ValueError('请至少选择一种遗物流派')
    candidates = [dict(r, official_id=identify_official_relic(r)) for r in relics
                  if r.get('relic_type') in active_modes and
                  r.get('color') in COLORS.values()]
    candidates = [r for r in candidates
                  if not any(_satisfies(r, e) for e in excluded_entries)]
    if any(sum(r['relic_type'] == mode for r in candidates) < 3 for mode in active_modes):
        return None
    matching_vessels = [v for v in vessels if v['hero_en'] in
                        (HEROES[build['hero']], 'Any Nightfarer')]
    general = {'normal': presets.normal_general, 'deepnight': presets.deepnight_general}
    selected_presets = {
        'normal': (_find_preset(presets, 'normal', normal_preset_id)
                   if 'normal' in active_modes else None),
        'deepnight': (_find_preset(presets, 'deepnight', deepnight_preset_id)
                      if 'deepnight' in active_modes else None),
    }
    if any(not selected_presets[mode] for mode in active_modes):
        return None
    score_maps = {mode: _score_map(selected_presets[mode], general[mode], scoring, mode)
                  for mode in active_modes}
    official_scores = dict((general['normal'] or {}).get('official_scores', {}))
    if 'normal' in active_modes:
        official_scores.update(selected_presets['normal'].get('official_scores', {}))
    negatives = dict(scoring['negative_tiers'])
    negatives.update((general['deepnight'] or {}).get('negative_tiers', {}))
    if 'deepnight' in active_modes:
        negatives.update(selected_presets['deepnight'].get('negative_tiers', {}))
    if any(not any(_satisfies(r, item) for r in candidates for item in group)
           for group in groups):
        return None

    n = len(candidates)
    effects = {}
    for i, relic in enumerate(candidates):
        mode = relic['relic_type']
        for affix in set(relic['affixes']):
            if mode == 'deepnight' and affix in negatives:
                continue
            points = score_maps[mode].get(affix)
            if points is not None and points >= 0 and not _is_repeatable(mode, affix):
                effects.setdefault((mode, affix), (points, []))[1].append(i)
    effect_keys = list(effects)
    # Each group consumes one occurrence, independently from scoring deduplication.
    allocations = []
    for g, group in enumerate(groups):
        seen = set()
        for entry in group:
            key = (entry['kind'], entry.get('id') if entry['kind'] == 'official' else entry.get('name'))
            if key not in seen:
                allocations.append((g, key, entry))
                seen.add(key)
    offset = n + len(effect_keys)
    slot_offset = offset + len(allocations)
    initial_keys = [j for j, (_,name) in enumerate(effect_keys) if _initial_kind(name)]
    initial_offset = slot_offset + 3*n
    length = initial_offset + 3*len(initial_keys)
    def slot_var(i, position):
        return slot_offset + 3*i + position

    cost = np.zeros(length)
    for j, key in enumerate(effect_keys):
        cost[n+j] = -effects[key][0]
    for i, relic in enumerate(candidates):
        mode = relic['relic_type']
        for affix in relic['affixes']:
            if _is_repeatable(mode, affix) or (score_maps[mode].get(affix, 0) < 0
                        and not (mode == 'deepnight' and affix in negatives)):
                cost[i] -= score_maps[mode].get(affix, 0)
            if mode == 'deepnight':
                tier = negatives.get(affix)
                if tier in scoring['deepnight']['positive']:
                    cost[i] -= scoring['deepnight']['positive'][tier]
                elif tier in scoring['deepnight']['negative']:
                    cost[i] -= scoring['deepnight']['negative'][tier]
        if mode == 'normal' and str(relic.get('official_id')) in official_scores:
            target = official_scores[str(relic['official_id'])]
            intrinsic = sum(score_maps['normal'].get(a, 0) for a in set(relic['affixes']))
            cost[i] -= target - intrinsic

    base_rows, base_lows, base_highs = [], [], []
    def add(rows, lows, highs, coeff, lo=-np.inf, hi=np.inf):
        rows.append(csr_matrix(coeff.reshape(1, -1))); lows.append(lo); highs.append(hi)
    for mode in active_modes:
        coeff = np.zeros(length)
        for i, relic in enumerate(candidates):
            if relic['relic_type'] == mode:
                coeff[i] = 1
        add(base_rows, base_lows, base_highs, coeff, 3, 3)
    for g in range(len(groups)):
        coeff = np.zeros(length)
        for j, (owner, _, _) in enumerate(allocations):
            if owner == g:
                coeff[offset+j] = 1
        add(base_rows, base_lows, base_highs, coeff, 1, 1)
    for key in {key for _, key, _ in allocations}:
        coeff = np.zeros(length)
        for j, (_, entry_key, _) in enumerate(allocations):
            if entry_key == key:
                coeff[offset+j] = 1
        for i, relic in enumerate(candidates):
            coeff[i] = -(relic['affixes'].count(key[1]) if key[0] == 'affix' else
                         int(relic['relic_type'] == 'normal' and relic.get('official_id') == key[1]))
        add(base_rows, base_lows, base_highs, coeff, hi=0)
    for j, key in enumerate(effect_keys):
        coeff = np.zeros(length); coeff[n+j] = 1
        for i in effects[key][1]:
            coeff[i] -= 1
        add(base_rows, base_lows, base_highs, coeff, hi=0)
    by_name = {}
    for j, (_, name) in enumerate(effect_keys):
        by_name.setdefault(name, []).append(n+j)
    for indices in by_name.values():
        if len(indices) > 1:
            coeff = np.zeros(length); coeff[indices] = 1
            add(base_rows, base_lows, base_highs, coeff, hi=1)
    for stronger in VAMP[1:]:
        indices = by_name.get(VAMP[0], []) + by_name.get(stronger, [])
        if indices:
            coeff = np.zeros(length); coeff[indices] = 1
            add(base_rows, base_lows, base_highs, coeff, hi=1)
    weapon_buffs = [j for name, indices in by_name.items()
                    if name.startswith('装备三把以上类别为') and '提升攻击力' in name
                    for j in indices]
    if len(weapon_buffs) > 1:
        coeff = np.zeros(length); coeff[weapon_buffs] = 1
        add(base_rows, base_lows, base_highs, coeff, hi=1)

    # A chosen relic occupies one compatible slot; each slot holds one relic.
    for i in range(n):
        coeff = np.zeros(length); coeff[i] = -1
        for pos in range(3): coeff[slot_var(i,pos)] = 1
        add(base_rows, base_lows, base_highs, coeff, 0, 0)
    for mode in active_modes:
        for pos in range(3):
            coeff = np.zeros(length)
            for i,r in enumerate(candidates):
                if r['relic_type'] == mode: coeff[slot_var(i,pos)] = 1
            add(base_rows, base_lows, base_highs, coeff, 1, 1)
    for k,j in enumerate(initial_keys):
        mode,name = effect_keys[j]
        kind = _initial_kind(name)
        coeff = np.zeros(length); coeff[n+j] = -1
        for pos in range(3): coeff[initial_offset+3*k+pos] = 1
        add(base_rows, base_lows, base_highs, coeff, 0, 0)
        for pos in range(3):
            z = initial_offset+3*k+pos
            coeff = np.zeros(length); coeff[z] = 1
            for i in effects[(mode,name)][1]: coeff[slot_var(i,pos)] = -1
            add(base_rows, base_lows, base_highs, coeff, hi=0)
            # Any earlier replacement of this kind, even an unscored one, blocks it.
            coeff = np.zeros(length); coeff[z] = 6
            rank = (3 if mode == 'deepnight' else 0) + pos
            for i,r in enumerate(candidates):
                if not any(_initial_kind(a)==kind for a in r['affixes']): continue
                for earlier in range(3):
                    if (3 if r['relic_type']=='deepnight' else 0)+earlier < rank:
                        coeff[slot_var(i,earlier)] = 1
            add(base_rows, base_lows, base_highs, coeff, hi=6)
    for kind in ('战技','魔法','祷告'):
        coeff = np.zeros(length)
        for j in initial_keys:
            if _initial_kind(effect_keys[j][1])==kind: coeff[n+j]=1
        add(base_rows, base_lows, base_highs, coeff, hi=1)

    def solve_vessel(vessel, excluded=(), minimum=None):
        rows = list(base_rows); lows = list(base_lows); highs = list(base_highs)
        upper = np.ones(length)
        for i,relic in enumerate(candidates):
            slots = _slots(vessel['normal_en' if relic['relic_type']=='normal' else 'deep_en'])
            for pos,color in enumerate(slots):
                if color != '*' and color != relic['color']: upper[slot_var(i,pos)] = 0
        for selected_ids in excluded:
            coeff = np.zeros(length)
            for i, relic in enumerate(candidates):
                if relic['id'] in selected_ids:
                    coeff[i] = 1
            add(rows, lows, highs, coeff, hi=3 * len(active_modes) - 1)
        if minimum is not None:
            add(rows, lows, highs, cost.copy(), hi=-minimum)
        result = milp(cost, integrality=np.ones(length), bounds=Bounds(0, upper),
                      constraints=LinearConstraint(vstack(rows, format='csc'), lows, highs),
                      options={'time_limit': time_limit, 'mip_rel_gap': 0.0})
        if result.status == 2:
            return None
        if result.status != 0 or result.x is None:
            raise RuntimeError(f"高脚杯 {vessel['name_en']} 未能证明最优：{result.message}")
        selected_indices = [i for i in range(n) if result.x[i]>0.5]
        positions = {i:next(pos for pos in range(3) if result.x[slot_var(i,pos)]>0.5)
                     for i in selected_indices}
        display_order = [candidates[i] for i in sorted(selected_indices,
                         key=lambda i:(candidates[i]['relic_type']=='deepnight',positions[i]))]
        breakdown = {i: {affix: 0 for affix in candidates[i]['affixes']}
                     for i in selected_indices}
        adjustments = {i: 0 for i in selected_indices}
        for j, (mode, affix) in enumerate(effect_keys):
            if result.x[n+j] <= 0.5:
                continue
            owner = next((i for r in display_order for i in effects[(mode, affix)][1]
                          if i in breakdown and candidates[i]['id'] == r['id']), None)
            if owner is not None:
                breakdown[owner][affix] += effects[(mode, affix)][0]
        selected = []
        for i in selected_indices:
            relic = candidates[i]
            mode = relic['relic_type']
            for affix in relic['affixes']:
                if _is_repeatable(mode, affix) or (score_maps[mode].get(affix, 0) < 0
                        and not (mode == 'deepnight' and affix in negatives)):
                    breakdown[i][affix] += score_maps[mode].get(affix, 0)
                if mode == 'deepnight':
                    tier = negatives.get(affix)
                    if tier in scoring['deepnight']['positive']:
                        breakdown[i][affix] += scoring['deepnight']['positive'][tier]
                    elif tier in scoring['deepnight']['negative']:
                        breakdown[i][affix] += scoring['deepnight']['negative'][tier]
            if mode == 'normal' and str(relic.get('official_id')) in official_scores:
                intrinsic = sum(score_maps['normal'].get(a, 0) for a in set(relic['affixes']))
                adjustments[i] = official_scores[str(relic['official_id'])] - intrinsic
            selected.append(dict(relic, affix_points=breakdown[i],
                                 official_adjustment=adjustments[i],
                                 score_contribution=sum(breakdown[i].values()) + adjustments[i]))
        # Use the feasible order that actually activates the scored initial effects.
        by_id = {item['id']: item for item in selected}
        for mode in active_modes:
            slots = _slots(vessel['normal_en' if mode == 'normal' else 'deep_en'])
            assignment = [by_id[r['id']] for r in display_order if r['relic_type'] == mode]
            for position, item in enumerate(assignment):
                item['slot_index'] = position
                item['slot_color'] = slots[position]
        first_initial = {}
        for original in display_order:
            item = by_id[original['id']]
            item['initial_effect_status'] = {}
            for name in item['affixes']:
                kind = _initial_kind(name)
                if kind:
                    item['initial_effect_status'][name] = '生效' if kind not in first_initial else '被左侧覆盖，不计分'
                    first_initial.setdefault(kind,name)
        selected.sort(key=lambda item: (item['relic_type'] == 'deepnight', item['slot_index']))
        assert sum(item['score_contribution'] for item in selected) == round(-result.fun)
        return {'score': round(-result.fun), 'vessel': vessel['name_en'],
                'vessel_name': vessel.get('name', vessel['name_en']),
                'weapon': '', 'relics': selected, 'status': 'optimal'}

    if page_size is not None:
        if page_size < 1:
            raise ValueError('每页方案数量须大于零')
        seen = {frozenset(ids) for ids in excluded_combinations}
        minimum = (math.ceil(anchor_score * min_ratio) if anchor_score is not None
                   and anchor_score >= 0 else anchor_score)
        # 每只器皿始终保留已证明的最高分候选；弹出一套后只需更新该器皿。
        frontier = {v['name_en']: solve_vessel(v, seen, minimum)
                    for v in matching_vessels}
        vessel_by_name = {v['name_en']: v for v in matching_vessels}
        solutions = []
        while len(solutions) < page_size:
            available = [item for item in frontier.values() if item is not None]
            if not available:
                break
            current = max(available, key=lambda item: item['score'])
            if anchor_score is None:
                anchor_score = current['score']
                minimum = (math.ceil(anchor_score * min_ratio)
                           if anchor_score >= 0 else anchor_score)
            if current['score'] < minimum:
                break
            key = frozenset(relic['id'] for relic in current['relics'])
            if key not in seen:
                solutions.append(current)
                seen.add(key)
            # 同一遗物组可能适配多只器皿；过期的器皿候选再次弹出时也会被跳过。
            name = current['vessel']
            frontier[name] = solve_vessel(vessel_by_name[name], seen, minimum)
        for name, item in list(frontier.items()):
            while item is not None and frozenset(r['id'] for r in item['relics']) in seen:
                item = solve_vessel(vessel_by_name[name], seen, minimum)
            frontier[name] = item
        has_more = (any(item is not None and item['score'] >= minimum
                        for item in frontier.values()) if anchor_score is not None else False)
        return {'score': anchor_score, 'min_ratio': min_ratio, 'min_score': minimum,
                'solutions': solutions, 'has_more': has_more,
                'excluded_combinations': [sorted(ids) for ids in seen],
                'normal_preset_id': normal_preset_id,
                'deepnight_preset_id': deepnight_preset_id}
