"""Pure shared relic rules. Unknown observations never authorize destruction."""
from dataclasses import dataclass, field
from typing import Optional


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


@dataclass
class MatchResult:
    qualified: bool
    perfect: bool
    best_match: Optional[PresetMatch]
    preset_matches: list[PresetMatch]
    unknown_count: int
    destructive_action_allowed: bool
    uncertainty_reasons: list[str] = field(default_factory=list)

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


def preset_configuration_errors(general_preset, dedicated_presets, blacklist_preset=None):
    """Explain invalid active rules without depending on an OCR observation."""
    errors = []

    def strings(preset, key, label):
        value = preset.get(key, [])
        if not _strings(value):
            errors.append(f'预设「{preset.get("name", preset.get("id", "未命名"))}」：{label}格式无效')
            return set()
        return set(value)

    general = set()
    if general_preset and general_preset.get('is_active', True):
        general = strings(general_preset, 'affixes', '有效词条')
    if blacklist_preset and blacklist_preset.get('is_active', True):
        strings(blacklist_preset, 'affixes', '黑名单词条')
    candidates = (dedicated_presets.values() if isinstance(dedicated_presets, dict)
                  else dedicated_presets or [])
    for preset in candidates:
        if not preset.get('is_active', True):
            continue
        name = preset.get('name', preset.get('id', '未命名'))
        available = strings(preset, 'affixes', '有效词条') | general
        strings(preset, 'blacklist_exceptions', '黑名单例外')
        _, required, valid = _required_groups(preset)
        if not valid:
            errors.append(f'预设「{name}」：必须词条组格式无效')
        elif set(required) - available:
            errors.append(f'预设「{name}」：必须词条未包含在专用或已启用通用预设的有效词条中：'
                          + '、'.join(sorted(set(required) - available)))
    return errors


def match_relic(observation, general_preset, dedicated_presets, blacklist_preset=None,
                threshold=2, general_fallback='no_active') -> MatchResult:
    """Fallback: repository=no_active; shop=always (only if no dedicated qualifies).

    Known positive subsets can justify keeping an uncertain relic. Perfect status
    requires a complete observation, since unseen negatives may invalidate it.
    Invalid rule configuration also blocks destructive decisions.
    """
    if general_fallback not in ('no_active', 'always', 'never'):
        raise ValueError('Unknown general fallback policy')
    if threshold < 1:
        raise ValueError('Threshold must be positive')
    affixes = observation.get('affixes') or []
    known = [a for a in affixes if a.get('cleaned_text') and not a.get('is_unknown')
             and isinstance(a.get('is_positive'), bool)]
    positives = {a['cleaned_text'] for a in known if a['is_positive']}
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
            _required_groups(preset) if dedicated else ([], [], True)
        )
        required = set(required_flat)
        exceptions, exceptions_valid = values(preset, 'blacklist_exceptions') if dedicated else (set(), True)
        available = useful | (general if dedicated and general_preset
                              and general_preset.get('is_active', True) else set())
        valid = useful_valid and required_valid and exceptions_valid and required <= available
        invalid_config |= not valid
        exceptions &= blacklist
        matched = sorted(positives & (general | useful) - blacklist)
        missing_groups = [group for group in required_groups
                          if not (set(group) & positives)]
        missing = [" 或 ".join(group) for group in missing_groups]
        hits = sorted(all_known & (blacklist - exceptions))
        qualified = valid and not missing_groups and not hits and len(matched) >= threshold
        return PresetMatch(str(preset.get('id', preset.get('name', ''))), preset.get('name', ''),
                           qualified, len(matched), matched,
                           sorted(required & positives), missing,
                           hits, sorted(all_known & exceptions),
                           qualified and dedicated and len(matched) >= 3 and observation_certain,
                           dedicated, valid, required_groups, missing_groups)

    for p in active:
        matches.append(evaluate(p))
    if (general and not any(m.qualified for m in matches)
            and (general_fallback == 'always' or (general_fallback == 'no_active' and not active))):
        matches.append(evaluate(general_preset, False))
    if invalid_config:
        reasons.extend(preset_configuration_errors(
            general_preset, dedicated_presets, blacklist_preset))
    qualified = [m for m in matches if m.qualified]
    best = max(qualified, key=lambda m: m.effective_count, default=None)
    return MatchResult(bool(qualified), any(m.perfect for m in qualified), best, matches,
                       unknown_count, not reasons, reasons)


def log_match(result, index, log):
    """One shared, detailed log format for both controllers."""
    if result.qualified:
        log(f'[{index}] 合格遗物；最佳预设: {result.best_match.preset_name}', 'SUCCESS')
        for match in result.qualified_matches:
            log(f'匹配预设: {match.preset_name}；有效词条: {match.effective_count}'
                + (' ★ PERFECT' if match.perfect else ''), 'SUCCESS')
            log('必须词条: ' + ('、'.join(match.required_matches) or '无') + ' ✓', 'INFO')
            log('匹配词条: ' + '、'.join(match.matched_affixes), 'INFO')
            log('黑名单例外: ' + ('、'.join(match.blacklist_exceptions_used) or '无'), 'INFO')
        if result.perfect:
            log('★★★★★ 检测到完美遗物 ★★★★★', 'SUCCESS')
    else:
        log(f'[{index}] 不合格遗物', 'INFO')
    for reason in result.uncertainty_reasons:
        log(f'{reason}；保留，禁止售出/取消收藏', 'WARNING')
