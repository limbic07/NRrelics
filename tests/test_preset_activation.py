import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
from ui.pages.page_shop import PageShop as ShopPage
from ui.pages.page_repo import RepoPage

class ActivationTests(unittest.TestCase):
    def test_single_does_not_rebuild(self):
        for cls in (ShopPage,RepoPage):
            page=SimpleNamespace(mode_combo=Mock(),preset_manager=Mock(),preset_activation_changed=Mock())
            page.mode_combo.currentIndex.return_value=0
            cls._toggle_preset(page,'a')
            page.preset_manager.toggle_preset_active.assert_called_once_with('normal','a')
            page.preset_activation_changed.emit.assert_called_once_with('normal')

    def test_batch_saves_once_and_noop_does_not_save(self):
        for cls in (ShopPage,RepoPage):
            presets={'a':{'is_active':True},'b':{'is_active':True}}
            page=SimpleNamespace(mode_combo=Mock(),preset_manager=Mock(),preset_activation_changed=Mock())
            page.mode_combo.currentIndex.return_value=1
            page.preset_manager.get_dedicated_presets.return_value=presets
            with patch('ui.pages.page_repo.sync_preset_activation') as sync:
                cls._set_all_presets_active(page,False)
                self.assertTrue(all(not p['is_active'] for p in presets.values()))
                page.preset_manager.save_presets.assert_called_once()
                sync.assert_called_once_with(page,'deepnight')
                cls._set_all_presets_active(page,False)
                page.preset_manager.save_presets.assert_called_once()

    def test_unrelated_settings_do_not_rebuild(self):
        for cls in (ShopPage,RepoPage):
            page=SimpleNamespace(_presets_loaded=True,_displayed_score_enabled=True,_refresh_presets=Mock())
            cls.refresh_scoring_display(page,{'scoring':{'enabled':True},'steam_path':'changed'})
            page._refresh_presets.assert_not_called()
            cls.refresh_scoring_display(page,{'scoring':{'enabled':False}})
            page._refresh_presets.assert_called_once()

    def test_unchanged_inventory_only_updates_filter(self):
        from ui.pages.page_relics import RelicPage
        items=[{'id':1,'affixes':['a']}]
        page=SimpleNamespace(inventory=Mock(),_table_items=items,table=Mock(),affix_filter='b')
        page.inventory.list_owned.return_value=items
        RelicPage.refresh(page)
        page.table.setRowCount.assert_not_called()
        page.table.setItem.assert_not_called()
        page.table.setRowHidden.assert_called_once_with(0,True)

if __name__=='__main__':unittest.main()

