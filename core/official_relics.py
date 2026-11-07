"""Bundled fixed official relic catalog and inventory identification."""
import json
from functools import lru_cache

from core.utils import get_resource_path


@lru_cache(maxsize=1)
def load_official_relics():
    with open(get_resource_path('data/official_relics.json'), encoding='utf-8') as f:
        return json.load(f)['relics']


def identify_official_relic(relic):
    """Prefer an explicit ID; otherwise require a unique color/effect match."""
    explicit = relic.get('official_id')
    if explicit is not None:
        return int(explicit)
    if relic.get('relic_type') != 'normal':
        return None
    effects = sorted(relic.get('affixes') or [])
    matches = [entry['id'] for entry in load_official_relics()
               if entry['color'] == relic.get('color') and
               sorted(entry['affixes']) == effects]
    return matches[0] if len(matches) == 1 else None
