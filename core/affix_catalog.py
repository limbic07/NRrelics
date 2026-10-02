"""Optional, data-driven affix metadata.

The catalog is advisory only. Matching and manually entered requirement groups
continue to work when the generated catalog is absent or incomplete.
"""
import json
import sys
import unicodedata
from pathlib import Path
from functools import lru_cache
import xml.etree.ElementTree as ET


@lru_cache(maxsize=1)
def validation_affix_names():
    """Chinese display names only; never used to decide relic legality."""
    catalog = AffixCatalog()
    names = {}
    for effect in catalog.effects:
        try:
            names[int(effect["id"])] = effect["name"]
        except (KeyError, TypeError, ValueError):
            continue
    root = catalog.path.parent / "relic_validation"
    for filename in ("AttachEffectName.fmg.xml", "AttachEffectName_dlc01.fmg.xml"):
        try:
            for entry in ET.parse(root / filename).findall("./entries/text"):
                text = (entry.text or "").strip()
                if text and text != "%null%":
                    names.setdefault(int(entry.attrib["id"]), text)
        except (OSError, ET.ParseError, KeyError, ValueError):
            continue
    return names


def normalize_name(value):
    return unicodedata.normalize("NFKC", value) if isinstance(value, str) else ""


class AffixCatalog:
    def __init__(self, path=None):
        self.path = Path(path) if path else self._default_path()
        self.effects = []
        self._by_name = {}
        self._load()

    @staticmethod
    def _default_path():
        roots = [Path(getattr(sys, "_MEIPASS", ""))] if getattr(sys, "_MEIPASS", "") else []
        roots.append(Path(__file__).resolve().parent.parent)
        for root in roots:
            candidate = root / "data" / "affix_catalog.json"
            if candidate.exists():
                return candidate
        return roots[-1] / "data" / "affix_catalog.json"

    def _load(self):
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                return
            effects = data.get("effects", [])
            if not isinstance(effects, list):
                return
            self.effects = [e for e in effects if isinstance(e, dict)
                            and isinstance(e.get("name"), str)]
            for effect in self.effects:
                self._by_name.setdefault(normalize_name(effect["name"]), []).append(effect)
        except (OSError, ValueError, TypeError):
            self.effects = []

    def lookup(self, name):
        matches = self._by_name.get(normalize_name(name), [])
        return list(matches) if len(matches) == 1 else []

    def alternatives(self, name):
        matches = self.lookup(name)
        if (not matches or matches[0].get("verified") is not True
                or matches[0].get("is_positive") is not True):
            return []
        family_id = matches[0].get("family_id")
        if type(family_id) is not int or family_id < 0:
            return []
        return [e["name"] for e in self.effects
                if e.get("verified") is True and e.get("is_positive") is True
                and e.get("family_id") == family_id]

    def compatibility_warnings(self, groups):
        """Warn only for proven cross-group incompatibility.

        Missing/ambiguous metadata produces no warning, never a hard failure.
        """
        def category(name):
            rows = self.lookup(name)
            if not rows:
                return None
            row = rows[0]
            value = row.get("compatibility_id")
            if (row.get("verified") is not True or row.get("is_positive") is not True
                    or type(value) is not int or value < 0):
                return None
            return value

        warnings = []
        for index, left in enumerate(groups):
            for other_index in range(index + 1, len(groups)):
                right = groups[other_index]
                if not left or not right:
                    continue
                if {normalize_name(a) for a in left} & {normalize_name(b) for b in right}:
                    continue  # One observed affix can satisfy both groups.
                pairs = [(category(a), category(b)) for a in left for b in right]
                if all(a is not None and b is not None and a == b for a, b in pairs):
                    warnings.append((index + 1, other_index + 1))
        return warnings
