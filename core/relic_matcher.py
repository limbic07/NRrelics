"""Pure shared relic rules. Unknown observations never authorize destruction."""
from dataclasses import dataclass, field
from typing import Optional
from core.relic_scoring import (normalize_scoring, normalize_affix_tiers,
                                normalize_preset_negative_tiers, POSITIVE_TIERS)


@dataclass
class PresetMatch:
    preset_id: str
    preset_name: str
    qualified: bool
    effective_count: int
    matched_affixes: list[str]
    required_matches: list[str]
    missing_required: list[str]
    blacklist_hits: list[str]
    blacklist_exceptions_used: list[str]
    perfect: bool
    is_dedicated: bool = True
    configuration_valid: bool = True
    required_affix_groups: list[list[str]] = field(default_factory=list)
    missing_required_groups: list[list[str]] = field(default_factory=list)
    score: int = 0
    score_grade: str = ""
    score_details: list[tuple[str, int]] = field(default_factory=list)


@dataclass
class MatchResult:
    qualified: bool
    perfect: bool
    best_match: Optional[PresetMatch]
    preset_matches: list[PresetMatch]
    unknown_count: int
    destructive_action_allowed: bool
    uncertainty_reasons: list[str] = field(default_factory=list)
    candidate_match: Optional[PresetMatch] = None
    candidate_failure_reasons: list[str] = field(default_factory=list)

    @property
    def qualified_matches(self):
        return [m for m in self.preset_matches if m.qualified]


def _strings(value):
    return isinstance(value, (list, tuple, set)) and all(isinstance(a, str) and a for a in value)


def _required_groups(preset):
    """Return (groups, flattened, valid), retaining legacy flat semantics."""
    if "required_affix_groups" in preset:
        value = preset["required_affix_groups"]
        if not isinstance(value, list):
            return [], [], False
        groups = []
        for group in value:
            if not isinstance(group, list) or not _strings(group):
                return [], [], False
            group = list(dict.fromkeys(group))
            if not group:
                return [], [], False
            groups.append(group)
        return groups, [a for group in groups for a in group], True
    value = preset.get("required_affixes", [])
    if not _strings(value):
        return [], [], False
    flat = list(dict.fromkeys(value))
    return ([[a] for a in flat], flat, True)


def match_relic(observation, general_preset, dedicated_presets, blacklist_preset=None,
                threshold=2, general_fallback='no_active', scoring_config=None,
                mode='normal') -> MatchResult:
    """Fallback: repository=no_active; shop=always (only if no dedicated qualifies).

    Known positive subsets can justify keeping an uncertain relic. Perfect status
    requires a complete observation, since unseen negatives may invalidate it.
    Invalid rule configuration also blocks destructive decisions.
    """
    if general_fallback not in ('no_active', 'always', 'never'):
        raise ValueError('Unknown general fallback policy')
    if threshold < 1:
        raise ValueError('Threshold must be positive')
    scoring = normalize_scoring(scoring_config)
    score_enabled = scoring['enabled']
    if mode not in ('normal', 'deepnight'):
        raise ValueError('Unknown relic mode')
    affixes = observation.get('affixes') or []
    known = [a for a in affixes if a.get('cleaned_text') and not a.get('is_unknown')
             and isinstance(a.get('is_positive'), bool)]
    positives = {a['cleaned_text'] for a in known if a['is_positive']}
    negatives = {a['cleaned_text'] for a in known if not a['is_positive']}
    all_known = {a['cleaned_text'] for a in known}
    unknown_count = max(int(observation.get('unknown_count', 0)),
                        len(observation.get('correction_failed_affixes') or [])
                        + len(affixes) - len(known)
                        + int(observation.get('failed_line_count', 0)))
    reasons = []
    if not observation.get('success', False):
        reasons.append('OCR识别失败')
    if not known:
        reasons.append('没有可靠词条')
    if unknown_count:
        reasons.append(f'未知或识别失败词条/行: {unknown_count}')
    if observation.get('ocr_incomplete', False):
        reasons.append('OCR不完整')
    observation_certain = not reasons
    invalid_config = False

    def values(preset, key):
        nonlocal invalid_config
        value = preset.get(key, [])
        if not _strings(value):
            invalid_config = True
            return set(), False
        return set(value), True

    general = set()
    if general_preset and general_preset.get('is_active', True):
        general, _ = values(general_preset, 'affixes')
    blacklist = set()
    if blacklist_preset and blacklist_preset.get('is_active', True):
        blacklist, _ = values(blacklist_preset, 'affixes')
    candidates = dedicated_presets.values() if isinstance(dedicated_presets, dict) else (dedicated_presets or [])
    active = [p for p in candidates if p.get('is_active', True)]
    matches = []

    def evaluate(preset, dedicated=True):
        nonlocal invalid_config
        useful, useful_valid = values(preset, 'affixes')
        required_groups, required_flat, required_valid = (
            _required_groups(preset) if dedicated and not score_enabled else ([], [], True))
        required = set(required_flat)
        exceptions, exceptions_valid = (values(preset, 'blacklist_exceptions')
                                        if dedicated and not score_enabled else (set(), True))
        excluded, excluded_valid = (values(preset, 'excluded_affixes')
                                    if dedicated and score_enabled else (set(), True))
        available = (useful | (general if dedicated and general_preset
                               and general_preset.get('is_active', True) else set())) - excluded
        valid = useful_valid and required_valid and exceptions_valid and required <= available
        valid = valid and excluded_valid and not (excluded & useful)
        invalid_config |= not valid
        exceptions &= blacklist
        matched = sorted(positives & available - blacklist)
        missing_groups = [group for group in required_groups
                          if not (set(group) & positives)]
        missing = [" 或 ".join(group) for group in missing_groups]
        hits = sorted(all_known & (blacklist - exceptions))
        score = 0
        grade = ""
        score_details = []
        if score_enabled:
            general_tiers, general_valid = normalize_affix_tiers(
                general_preset or {'affixes': []})
            useful_tiers, tiers_valid = normalize_affix_tiers(preset)
            general_negative, general_negative_valid = normalize_preset_negative_tiers(
                general_preset or {})
            local_negative, local_negative_valid = normalize_preset_negative_tiers(preset)
            valid = (valid and tiers_valid and general_valid and general_negative_valid
                     and local_negative_valid)
            invalid_config |= not valid
            # Dedicated choices override inherited general choices, without
            # counting one recognized affix twice.
            tiers = {**general_tiers, **useful_tiers} if dedicated else useful_tiers
            negative_tiers = dict(scoring['negative_tiers'])
            if dedicated and general_preset and general_preset.get('is_active', True):
                negative_tiers.update(general_negative)
            negative_tiers.update(local_negative)
            reclassified = (sorted(name for name in negatives
                                   if negative_tiers.get(name) in POSITIVE_TIERS)
                            if mode == 'deepnight' else [])
            penalized = [name for name in matched if tiers.get(name) not in POSITIVE_TIERS]
            for name in penalized:
                points = scoring['deepnight']['negative'][tiers[name]]
                score += points
                score_details.append((name, points))
            matched = sorted((set(matched) - set(penalized)) | set(reclassified))
            for name in matched:
                tier = negative_tiers[name] if name in reclassified else tiers[name]
                points = scoring[mode]['positive'][tier]
                score += points
                score_details.append((name, points))
            if mode == 'deepnight':
                for name in sorted(negatives - set(reclassified)):
                    tier = negative_tiers.get(name, 'negligible')
                    points = scoring['deepnight']['negative'][tier]
                    score += points
                    score_details.append((name, points))
            if score >= scoring[mode]['keep_min']:
                grade = 'keep'
            elif score >= scoring[mode]['backup_min']:
                grade = 'backup'
            else:
                grade = 'reject'
            hard_hits = sorted(set(hits) - set(reclassified))
            qualified = (valid and not missing_groups and len(matched) >= threshold
                         and grade != 'reject'
                         and (not scoring['hard_blacklist'] or not hard_hits))
            perfect = (qualified and dedicated and len(matched) >= 3
                       and grade == 'keep' and observation_certain
                       and not any(negative_tiers.get(name) == 'unacceptable'
                                   for name in negatives))
        else:
            inherited_tiers, _ = normalize_affix_tiers(general_preset or {})
            local_tiers, _ = normalize_affix_tiers(preset)
            effective_tiers = {**inherited_tiers, **local_tiers} if dedicated else local_tiers
            matched = [name for name in matched if effective_tiers.get(name, 'secondary') in POSITIVE_TIERS]
            qualified = valid and not missing_groups and not hits and len(matched) >= threshold
            perfect = qualified and dedicated and len(matched) >= 3 and observation_certain
        return PresetMatch(str(preset.get('id', preset.get('name', ''))), preset.get('name', ''),
                           qualified, len(matched), matched,
                           sorted(required & positives), missing,
                           hits, sorted(all_known & exceptions),
                           perfect, dedicated, valid, required_groups, missing_groups,
                           score, grade, score_details)

    for p in active:
        matches.append(evaluate(p))
    general_negative, _ = normalize_preset_negative_tiers(general_preset or {})
    general_has_positive_rule = bool(general) or (score_enabled and mode == 'deepnight' and
        any(tier in POSITIVE_TIERS for tier in general_negative.values()))
    general_candidate = None
    if (general_has_positive_rule and not any(m.qualified for m in matches)
            and (general_fallback == 'always' or (general_fallback == 'no_active' and not active))):
        matches.append(evaluate(general_preset, False))
    elif general_has_positive_rule and score_enabled:
        general_candidate = evaluate(general_preset, False)
    if invalid_config:
        reasons.append('预设配置无效，请检查必须词条和例外')
    qualified = [m for m in matches if m.qualified]
    best = max(qualified, key=(lambda m: (m.score, m.effective_count)) if score_enabled
               else (lambda m: m.effective_count), default=None)
    candidate = max(matches + ([general_candidate] if general_candidate else []), key=(lambda m: (m.score, m.effective_count)) if score_enabled
                    else (lambda m: m.effective_count), default=None)
    failure = []
    if candidate and not candidate.qualified:
        if not candidate.configuration_valid:
            failure.append('预设配置无效')
        if candidate.missing_required_groups:
            failure.append('缺少必须词条')
        if candidate.effective_count < threshold:
            failure.append(f'有效词条不足：{candidate.effective_count}/{threshold}')
        if score_enabled and candidate.score_grade == 'reject':
            failure.append('分数低于备选线')
        if candidate.blacklist_hits:
            failure.append('命中黑名单')
    return MatchResult(bool(qualified), any(m.perfect for m in qualified), best, matches,
                       unknown_count, not reasons, reasons, candidate, failure)


def log_match(result, index, log):
    """One shared, detailed log format for both controllers."""
    if result.qualified:
        log(f'[{index}] 合格遗物；最佳预设: {result.best_match.preset_name}', 'SUCCESS')
        for match in result.qualified_matches:
            log(f'匹配预设: {match.preset_name}；有效词条: {match.effective_count}'
                + (f'；评分: {match.score}；等级: {"保留" if match.score_grade == "keep" else "备选"}'
                   if match.score_grade else '')
                + (' ★ PERFECT' if match.perfect else ''), 'SUCCESS')
            if match.score_grade:
                log('评分明细: ' + '、'.join(f'{name} {points:+d}' for name, points in match.score_details), 'INFO')
            log('必须词条: ' + ('、'.join(match.required_matches) or '无') + ' ✓', 'INFO')
            log('匹配词条: ' + '、'.join(match.matched_affixes), 'INFO')
            log('黑名单例外: ' + ('、'.join(match.blacklist_exceptions_used) or '无'), 'INFO')
        if result.perfect:
            log('★★★★★ 检测到完美遗物 ★★★★★', 'SUCCESS')
    else:
        log(f'[{index}] 不合格遗物', 'INFO')
        for match in result.preset_matches:
            if match.score_grade:
                log(f'预设: {match.preset_name}；有效词条: {match.effective_count}；'
                    f'评分: {match.score}；分数等级: {match.score_grade}；'
                    f'缺少必须组: {len(match.missing_required_groups)}', 'INFO')
    for reason in result.uncertainty_reasons:
        log(f'{reason}；保留，禁止售出/取消收藏', 'WARNING')


def preset_configuration_errors(general_preset, dedicated_presets, blacklist_preset=None,
                                scoring_config=None, mode="normal"):
    """Validate before purchasing, using the same rules as actual matching."""
    result = match_relic({'success': True, 'affixes': []}, general_preset,
                         dedicated_presets, blacklist_preset, general_fallback='always',
                         scoring_config=scoring_config, mode=mode)
    invalid = [m for m in result.preset_matches if not m.configuration_valid]
    if result.candidate_match and not result.candidate_match.configuration_valid and result.candidate_match not in invalid:
        invalid.append(result.candidate_match)
    errors = [f'预设「{m.preset_name}」配置无效，请检查词条等级、继承排除及旧版必须词条组' for m in invalid]
    if not errors and any('配置无效' in r or '格式' in r for r in result.uncertainty_reasons):
        errors = list(result.uncertainty_reasons)
    return errors
