from core.preset_manager import PresetManager


def test_existing_catalog_gains_split_builds_and_raider_affix():
    manager = object.__new__(PresetManager)
    manager.normal_general = None
    manager.deepnight_general = None
    manager.deepnight_blacklist = None
    manager.normal_dedicated = {
        'build_C27_normal': {'id': 'build_C27_normal', 'affixes': [],
                             'affix_tiers': {}, 'is_active': True},
        'build_R01_normal': {'id': 'build_R01_normal', 'affixes': [],
                             'affix_tiers': {}, 'is_active': True},
    }
    manager.deepnight_whitelist_dedicated = {
        'build_C27_deepnight': {'id': 'build_C27_deepnight', 'affixes': [],
                                'affix_tiers': {}, 'is_active': True},
        'build_R01_deepnight': {'id': 'build_R01_deepnight', 'affixes': [],
                                'affix_tiers': {}, 'is_active': True},
    }
    manager._merge_bundled_defaults()
    affix = '血量偏低时，能提升减伤率'
    assert manager.default_catalog_version == 3
    assert not manager.normal_dedicated['build_C27_normal']['is_active']
    assert not manager.deepnight_whitelist_dedicated['build_C27_deepnight']['is_active']
    assert manager.normal_dedicated['build_C27_dagger_normal']['is_active']
    assert manager.deepnight_whitelist_dedicated['build_C27_dagger_deepnight']['is_active']
    assert manager.normal_dedicated['build_R01_normal']['affix_tiers'][affix] == 'secondary'
    assert manager.deepnight_whitelist_dedicated['build_R01_deepnight']['affix_tiers'][affix] == 'secondary'
