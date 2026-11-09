"""Configurable relic scores. Preset affixes remain the source of effective affixes."""
from copy import deepcopy


POSITIVE_TIERS = ("core", "secondary", "bonus")
NEGATIVE_TIERS = ("unacceptable", "harmful", "negligible")

# These are complete vocabulary entries, rather than substring rules. A
# conversion affix mentioning reduced vigor is a positive entry and is never
# mistaken for the separate negative entry below.
DEFAULT_NEGATIVE_TIERS = {
    "降低生命力、感应": "unacceptable",
    "降低对所有异常状态的抵抗力": "unacceptable",
    "持续减少血量": "unacceptable",
    "闪避后的当下，降低减伤率": "unacceptable",
    "连续闪避时，降低减伤率": "unacceptable",
    "血量没有全满时，降低攻击力": "unacceptable",
    "降低力气、智力": "harmful",
    "降低灵巧、信仰": "harmful",
    "降低智力、灵巧": "harmful",
    "降低信仰、力气": "harmful",
    "受到损伤时，会累积出血量表": "harmful",
    "受到损伤时，会累积发狂量表": "harmful",
    "受到损伤时，会累积催眠量表": "harmful",
    "血量没有全满时，累积猩红腐败量表": "harmful",
    "濒死时，降低血量上限": "harmful",
}

DEFAULT_SCORING = {
    "enabled": False,
    "normal": {
        "positive": {"core": 10, "secondary": 6, "bonus": 2},
        "keep_min": 16,
        "backup_min": 10,
    },
    "deepnight": {
        "positive": {"core": 10, "secondary": 6, "bonus": 2},
        "negative": {"unacceptable": -12, "harmful": -4, "negligible": 0},
        "keep_min": 16,
        "backup_min": 10,
    },
    "negative_tiers": DEFAULT_NEGATIVE_TIERS,
    "hard_blacklist": False,
}


def normalize_scoring(value):
    """Supply old files with defaults; reject malformed numerical settings."""
    result = deepcopy(DEFAULT_SCORING)
    if not isinstance(value, dict):
        return result
    result["enabled"] = value.get("enabled") is True
    result["hard_blacklist"] = value.get("hard_blacklist") is True
    for mode in ("normal", "deepnight"):
        source = value.get(mode, {})
        if not isinstance(source, dict):
            continue
        score_types = (("positive", POSITIVE_TIERS),)
        if mode == "deepnight":
            score_types += (("negative", NEGATIVE_TIERS),)
        for sign, tiers in score_types:
            scores = source.get(sign, {})
            if isinstance(scores, dict):
                for tier in tiers:
                    number = scores.get(tier)
                    if isinstance(number, (int, float)) and not isinstance(number, bool):
                        result[mode][sign][tier] = max(-999, min(999, int(number)))
        for key in ("keep_min", "backup_min"):
            number = source.get(key)
            if isinstance(number, (int, float)) and not isinstance(number, bool):
                result[mode][key] = max(-999, min(999, int(number)))
        result[mode]["keep_min"] = max(result[mode]["keep_min"], result[mode]["backup_min"])
    mapping = value.get("negative_tiers", {})
    if isinstance(mapping, dict):
        result["negative_tiers"].update({name: tier for name, tier in mapping.items()
                                         if isinstance(name, str) and tier in NEGATIVE_TIERS})
    return result


def normalize_affix_tiers(preset):
    """Legacy selected affixes start at secondary; explicit grades take precedence."""
    affixes = preset.get("affixes", [])
    mapping = preset.get("affix_tiers", {})
    if not isinstance(mapping, dict):
        return {}, False
    if not isinstance(affixes, list):
        return {}, False
    if any(not isinstance(name, str) or tier not in POSITIVE_TIERS + NEGATIVE_TIERS
           for name, tier in mapping.items()):
        return {}, False
    return {**{name: "secondary" for name in affixes}, **mapping}, True


def normalize_preset_negative_tiers(preset):
    """Preset overrides may turn an OCR-negative affix into a scored positive."""
    mapping = preset.get("negative_tiers", {})
    if not isinstance(mapping, dict) or any(
            not isinstance(name, str) or tier not in POSITIVE_TIERS + NEGATIVE_TIERS
            for name, tier in mapping.items()):
        return {}, False
    return mapping.copy(), True
