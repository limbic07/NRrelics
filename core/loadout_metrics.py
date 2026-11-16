"""Display-only loadout metrics. These values never enter the solver objective."""
import math
import re
from pathlib import Path
from collections import Counter

from core.loadout_optimizer import _find_preset, _score_map, _is_repeatable, _initial_kind, VAMP
from core.official_relics import load_official_relics
from core.relic_scoring import normalize_scoring, normalize_affix_tiers, NEGATIVE_TIERS, POSITIVE_TIERS
from core.utils import get_resource_path


SURVIVAL_SCENARIOS = {
    'survival_physical': ('物理抗伤／未触发蓝泪', {'hp', 'mitigation', 'physical_mitigation'}),
    'survival_element': ('属性抗伤／未触发蓝泪', {'hp', 'mitigation', 'element_mitigation'}),
    'survival_physical_blue': ('物理抗伤／触发蓝泪', {'hp', 'mitigation', 'physical_mitigation', 'blue_tear'}),
    'survival_element_blue': ('属性抗伤／触发蓝泪', {'hp', 'mitigation', 'element_mitigation', 'blue_tear'}),
}
SURVIVAL_TAGS = set().union(*(scopes for _, scopes in SURVIVAL_SCENARIOS.values()))


def effect(name):
    """Return (scope, multiplier/rate). Unknown numerical effects stay explicit."""
    if name.startswith('【'):
        return ('function', 0)
    base = re.sub(r'\+\d+$', '', name)
    level = int(name.rsplit('+', 1)[1]) if re.search(r'\+\d+$', name) else 0
    series = {
        '提升物理攻击力': ('physical', [4, 5, 6, 10.5, 12]),
        '提升属性攻击力': ('element', [5, 8, 10]),
        '强化魔法': ('spell', [5, 8.5, 10]),
        '强化祷告': ('prayer', [5, 8.5, 10]),
        '强化防御反击': ('counter', [18, 25, 29]),
        '强化致命一击': ('critical', [18, 23]),
        '提升投掷壶的攻击力': ('pot', [15, 30]),
        '对陷入中毒的敌人，能强化攻击': ('poison', [10, 16, 20]),
        '对陷入猩红腐败的敌人，能强化攻击': ('rot', [10, 16, 20]),
        '对陷入冻伤的敌人，能强化攻击': ('frost', [10, 16, 20]),
        '提升物理减伤率': ('physical_mitigation', [10, 10.5, 12]),
        '提升属性减伤率': ('element_mitigation', [6, 10.5, 12]),
        '生命力': ('hp', [0, 2, 4, 6]),
        '周围陷入催眠时，提升攻击力': ('all', [12, 22]),
        '周围陷入发狂时，提升攻击力': ('all', [12, 22]),
        '涂抹油脂类道具时，能额外提升物理攻击力': ('physical', [10, 17, 20]),
    }
    for element in ('魔力', '火', '雷', '圣'):
        series['提升' + element + '属性攻击力'] = (element, [4.5, 5.5, 6.5, 10.5, 12])
        series['提升' + element + '属性减伤率'] = ('ignored', [0, 0, 0])
    if base in series:
        tag, values = series[base]
        return (tag, values[level] / 100) if level < len(values) else ('pending', 0)
    fixed = {
        '每次打倒黑夜入侵者，能提升攻击力': ('all', .175),
        '每次打倒封印监牢里的囚犯，能提升攻击力': ('all', .10),
        # Secondary bonuses participate only in scenes detected by other effects.
        '周围人物陷入中毒、腐败时，能提升攻击力': ('poison_rot_bonus', .12),
        '出现异常状态量表时，能缓慢提升攻击力': ('all', .225),
        '防御反击成功时，能依照自己目前的血量提升伤害': ('counter_bonus', .65),
        '强化轻攻击的第一记攻击': ('first', .15),
        '连续攻击时，提升攻击力': ('combo', .22),
        '提升近战攻击力': ('melee', .06),
        '提升战技攻击力': ('skill', .15),
        '提升血量上限': ('hp', .10),
        '受到攻击时，能提升攻击力': ('all', .15),
        '出击时的武器，附加圣属性攻击力': ('function', 0),
        '每次打倒大教堂的强敌，能提升血量上限': ('hp', .075),
        '减伤率降低时，偶尔会让敌人攻击失效': ('mitigation', .20),
        '涂抹油脂类道具时，能额外提升攻击力': ('physical', .10),
        '切换武器时，能提升物理攻击力': ('physical', .10),
        '附加属性攻击力时，能提升属性攻击力': ('element', .10),
        '血量偏低时，能提升减伤率': ('blue_tear', .16),
        '受到损伤并被弹飞时，能提升强韧度与减伤率': ('mitigation', .20),
    }
    if name in fixed:
        return fixed[name]
    if name.startswith('装备三把以上类别为'):
        if name.endswith('能提升攻击力'):
            return ('all', .10 if '类别为弓的' in name else .20)
        if name.endswith('能提升血量上限'):
            return ('hp', .20)
    if name.startswith('强化') and name.endswith(('的魔法', '的祷告')):
        return ('school:' + name, .12)
    match = re.fullmatch('提升(.+)的攻击力', name)
    if match and match[1] in '短剑 直剑 大剑 特大剑 曲剑 大曲剑 刀 双头剑 刺剑 重刺剑 斧 大斧 槌 大槌 连枷 矛 长矛 大矛 戟 镰刀 拳头 钩爪 软鞭 特大武器 弓 大弓'.split():
        return ('weapon:' + match[1], .06 if match[1] == '弓' else .09)
    # Do not silently report an unknown numerical damage/survival effect as zero.
    if any(word in name for word in ('攻击力', '提升伤害', '减伤率', '血量上限')):
        return ('pending', 0)
    return ('function', 0)


class Metrics:
    def __init__(self, presets, scoring, normal_id, deep_id, hero=None):
        config = normalize_scoring(scoring)
        self.maps = {}
        self.negative_names = {}
        self.converted_positive = {}
        self.official = {}
        self.official_affixes = {str(r['id']): set(r['affixes']) for r in load_official_relics()}
        self.hero = hero
        for mode, identifier in (('normal', normal_id), ('deepnight', deep_id)):
            if identifier == 'none':
                continue
            general = getattr(presets, mode + '_general')
            local = _find_preset(presets, mode, identifier) or {}
            if self.hero is None: self.hero = local.get('name', '').split('｜')[0]
            self.maps[mode] = _score_map(local, general, config, mode)
            inherited_tiers,_=normalize_affix_tiers(general or {})
            local_tiers,_=normalize_affix_tiers(local)
            tiers={**inherited_tiers,**local_tiers}
            for name in local.get('excluded_affixes',[]):tiers.pop(name,None)
            self.negative_names[mode]={name for name,tier in tiers.items() if tier in NEGATIVE_TIERS}
            if mode=='deepnight':
                # Unassigned native negatives default to negligible, not positive.
                native={line.split('→',1)[-1].strip() for line in Path(get_resource_path('data/deepnight_neg.txt')).read_text(encoding='utf-8').splitlines() if line.strip()}
                negative_tiers={**config['negative_tiers'],**(general or {}).get('negative_tiers',{}),**local.get('negative_tiers',{})}
                self.converted_positive[mode] = {name for name in native if negative_tiers.get(name) in POSITIVE_TIERS}
                for name in native | negative_tiers.keys():
                    if negative_tiers.get(name,'negligible') in POSITIVE_TIERS:self.negative_names[mode].discard(name)
                    else:self.negative_names[mode].add(name)
            if mode == 'normal':
                self.official = {**(general or {}).get('official_scores', {}), **local.get('official_scores', {})}
        self.allowed = {mode: {a for a, points in mapping.items() if points > 0 and a not in self.negative_names[mode]}
                        for mode, mapping in self.maps.items()}
        for mode, names in self.converted_positive.items():
            self.allowed.setdefault(mode, set()).update(names)
        for relic in load_official_relics():
            if self.official.get(str(relic['id']), 0) > 0:
                self.allowed.setdefault('normal', set()).update(set(relic['affixes'])-self.negative_names.get('normal',set()))
        allowed = set().union(*self.allowed.values()) if self.allowed else set()
        self.scenarios = self._scenarios(allowed)
        self.survival_scenarios = {key: scene for key, scene in SURVIVAL_SCENARIOS.items()
                                   if 'blue_tear' not in scene[1] or '血量偏低时，能提升减伤率' in allowed}
        if len(self.survival_scenarios) == 2:
            self.survival_scenarios = {key: (label.replace('未触发蓝泪', '基础'), scopes)
                                       for key, (label, scopes) in self.survival_scenarios.items()}

    def _scenarios(self, names):
        tags = {effect(a)[0] for a in names}
        # Character preferred pool plus effective pool-conversion entries. These
        # describe the evaluated weapon scenario, never add melee to spells.
        default_pool = {'追踪者': '大剑', '守护者': '戟', '铁之眼': '弓', '女爵': '短剑',
                        '无赖': '大斧', '复仇者': '圣印记', '隐士': '手杖', '执行者': '刀',
                        '学者': '刺剑', '送葬者': '槌'}
        pools = {default_pool.get(self.hero, '未知')}
        prefix = '通过潜在能力，能比较容易找到'
        pools.update(name[len(prefix):] for name in names if name.startswith(prefix))
        ranged = {'弓', '大弓', '圣印记', '手杖', '法杖', '未知'}
        melee = {'melee'} if pools - ranged else set()
        branches = []
        if 'physical' in tags:
            branches.append(('通用物理', {'physical'} | melee, True))
        if 'element' in tags:
            branches.append(('通用属性', {'element'}, False))
        for tag in sorted(tags):
            if tag.startswith('weapon:'):
                weapon = tag.split(':')[1]
                scopes = {'physical', tag}
                if weapon not in ('弓', '大弓', '圣印记', '手杖', '法杖'):
                    scopes.add('melee')
                branches.append(('普攻／' + weapon, scopes, True))
        if 'skill' in tags:
            branches.append(('通用战技', {'skill'} | melee, False))
            if 'physical' in tags:
                branches.append(('物理战技', {'skill', 'physical'} | melee, False))
            if 'element' in tags:
                branches.append(('属性战技', {'skill', 'element'} | melee, False))
        for tag, label in (('counter', '防御反击'), ('critical', '致命一击')):
            if tag in tags:
                weapons = {t for t in tags if t.startswith('weapon:')}
                bonus = {'counter_bonus'} if tag == 'counter' else set()
                branches.append((label, {tag, 'physical'} | bonus | melee | (weapons if len(weapons)==1 else set()), False))
        for kind, suffix, label in (('spell', '的魔法', '法术'), ('prayer', '的祷告', '祷告')):
            if kind not in tags:
                continue
            schools = sorted(t for t in tags if t.startswith('school:') and t.endswith(suffix))
            branches.append(('通用法术' if kind == 'spell' else '通用属性祷告',
                             {kind, 'element', '魔力'} if kind == 'spell' else {kind, 'element'}, False))
            for school in schools:
                scopes = {kind, school}
                if kind == 'spell':
                    scopes.update(('element', '魔力'))
                elif '野兽' in school:
                    scopes.add('physical')
                elif '龙飨' not in school:
                    scopes.update(('element', '雷' if '古龙' in school else '圣' if '黄金律法' in school else '火'))
                else:
                    scopes.add('element')
                branches.append((label + '／' + school[len('school:强化'):-len(suffix)], scopes, False))
        if 'pot' in tags:
            branches.append(('投掷壶', {'pot', '火', 'element'}, False))
        scenarios = []
        for label, scopes, attacks in branches:
            targets = [('', '无指定目标状态')]
            if label != '投掷壶':
                targets += [(tag, title) for tag, title in [('poison', '中毒目标'), ('rot', '腐败目标'), ('frost', '冻伤目标')] if tag in tags]
            actions = [(set(), '基础')]
            if attacks:
                if 'first' in tags: actions.append(({'first'}, '仅第一击'))
                if 'combo' in tags: actions.append(({'combo'}, '仅连击'))
                if {'first', 'combo'} <= tags: actions.append(({'first', 'combo'}, '第一击＋连击'))
            for target, title in targets:
                for action, caption in actions:
                    bonus = {'poison_rot_bonus'} if target in ('poison', 'rot') else set()
                    scenarios.append((f'{label}／{title}／{caption}', scopes | {'all', target} | action | bonus))
        return scenarios or [('通用伤害／基础', {'all'})]

    def evaluate(self, solution):
        active = []
        seen = set()
        negatives = 0
        negative_terms = Counter()
        pending = set()
        for relic in solution['relics']:
            mode = relic['relic_type']
            official = self.official.get(str(relic.get('official_id')), 0) > 0
            for name in relic['affixes']:
                tag, value = ('function', 0) if name in self.converted_positive.get(mode, set()) else effect(name)
                if name in self.negative_names.get(mode,set()):
                    negatives += 1
                    negative_terms[name] += 1
                    if tag not in SURVIVAL_TAGS:
                        continue
                if tag == 'ignored':
                    continue
                effective = (self.maps.get(mode, {}).get(name, 0) > 0
                             or name in self.converted_positive.get(mode, set()))
                # An official score is not approval of every utility effect on
                # that relic. Keep the agreed official damage/survival bonuses,
                # but utility must be explicitly effective in the selected build.
                official_bonus = (mode == 'normal' and official and tag != 'function'
                                  and name in self.official_affixes.get(str(relic.get('official_id')), set()))
                if tag == 'blue_tear' and not (effective or official_bonus):
                    continue
                if not (effective or official_bonus or tag in SURVIVAL_TAGS):
                    continue
                if '被左侧覆盖' in relic.get('initial_effect_status', {}).get(name, ''):
                    continue
                key = ('three-weapons' if name.startswith('装备三把以上') and name.endswith('能提升攻击力') else name)
                if key in seen and not _is_repeatable(mode, name):
                    continue
                if key == 'three-weapons' and key in seen:
                    continue
                seen.add(key)
                if tag == 'pending': pending.add(name)
                active.append((name, tag, value))
        if any(name in (VAMP[1], VAMP[2]) for name, _, _ in active):
            active = [a for a in active if a[0] != VAMP[0]]
        damage = [100 * (math.prod(1 + v for _, tag, v in active if tag in scopes) - 1)
                  for _, scopes in self.scenarios]
        hp = math.prod(1 + v for _, t, v in active if t == 'hp')
        survival = {key: 100 * (hp / math.prod(1 - v for _, t, v in active if t in scopes and t != 'hp') - 1)
                    for key, (_, scopes) in self.survival_scenarios.items()}
        return {'damage': damage, 'survival': survival,
                'functions': sum(t == 'function' for _, t, _ in active),
                'negatives': negatives, 'pending': sorted(pending),
                'functional_terms': dict(Counter(name for name, tag, _ in active if tag == 'function')),
                'negative_terms': dict(negative_terms), 'active_effects': active}


def equivalence_key(solution):
    """Conservative equivalence: retain all effects, negatives and override states."""
    return (solution['score'], tuple(sorted(
        (r['relic_type'], r['color'], tuple(sorted(Counter(r['affixes']).items())),
         tuple(sorted(r.get('initial_effect_status', {}).items())),
         tuple(sorted(r.get('affix_points', {}).items())), r.get('official_adjustment', 0))
        for r in solution['relics'])))


def dominates(better, worse, columns=None):
    """Compare all scenes by default, or an explicit snapshot of selected columns."""
    a, b = better['metrics'], worse['metrics']
    if columns is None:
        if a['pending'] != b['pending']:
            return False  # Unknown numerical effects must not disappear via automatic pruning.
        if Counter(n for n,t,_ in a.get('active_effects',[]) if t=='pending') != Counter(n for n,t,_ in b.get('active_effects',[]) if t=='pending'):
            return False
        if a['survival'].keys() != b['survival'].keys() or len(a['damage']) != len(b['damage']):
            return False
        av = [better['score'], *a['damage'], *a['survival'].values()]
        bv = [worse['score'], *b['damage'], *(b['survival'][key] for key in a['survival'])]
    else:
        def numbers(row):
            metrics=row['metrics']
            return [row['score'] if key=='score' else metrics['damage'][key] if isinstance(key,int)
                    else metrics['survival'][key] for key in columns
                    if key=='score' or isinstance(key,int) or key in SURVIVAL_SCENARIOS]
        av, bv = numbers(better), numbers(worse)
    if len(av) != len(bv) or any(x < y - 1e-8 for x, y in zip(av, bv)):
        return False
    af, bf = (a.get('functional_terms', {}), b.get('functional_terms', {})) if columns is None or 'functions' in columns else ({}, {})
    an, bn = (a.get('negative_terms', {}), b.get('negative_terms', {})) if columns is None or 'negatives' in columns else ({}, {})
    if any(af.get(n, 0) < count for n, count in bf.items()):
        return False
    if any(count > bn.get(n, 0) for n, count in an.items()):
        return False
    return any(x > y + 1e-8 for x, y in zip(av, bv)) or af != bf or an != bn


def pareto_rows(rows, prefix=0, columns=None):
    """Yield between comparisons so the UI can process input during pruning."""
    frontier = list(range(prefix))
    for i in range(prefix, len(rows)):
        candidate = rows[i]
        remaining = []; rejected = False
        for j in frontier:
            if dominates(rows[j], candidate, columns):
                rejected = True
                yield None
                break
            if not dominates(candidate, rows[j], columns):
                remaining.append(j)
            yield None
        if not rejected:
            frontier = remaining + [i]
        yield None
    return frontier
