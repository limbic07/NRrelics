from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication


def test_presets_load_only_when_their_page_is_open(monkeypatch):
    from ui.pages import page_repo, page_shop
    from ui.main_window import MainWindow

    app = QApplication.instance() or QApplication([])
    loaded = []

    def mark_loaded(page):
        loaded.append(page.objectName())
        page._presets_loaded = True

    monkeypatch.setattr(page_shop.PageShop, '_refresh_presets', mark_loaded)
    monkeypatch.setattr(page_repo.RepoPage, '_refresh_presets', mark_loaded)
    window = MainWindow()
    assert loaded == []

    window.show()
    QTest.qWait(150)
    assert loaded == ['PageShop']

    window.switchTo(window.repo_page)
    QTest.qWait(500)
    assert loaded == ['PageShop', 'RepoPage']
    window.close()
    assert app is not None


def test_collapsed_preset_card_builds_affix_labels_on_first_expand():
    from ui.pages.page_repo import PresetCard

    app = QApplication.instance() or QApplication([])
    preset = {'id': 'sample', 'name': '测试预设', 'type': 'normal_whitelist',
              'affixes': ['词条甲', '词条乙'],
              'negative_tiers': {'负面丙': 'harmful'}}
    card = PresetCard(preset, score_enabled=True)
    assert card._affix_labels == []
    card._toggle_expand()
    assert [label.text() for label in card._affix_labels] == [
        '• 【次要】词条甲', '• 【次要】词条乙', '• 【很伤】负面丙']
    labels = list(card._affix_labels)
    card._toggle_expand()
    card._toggle_expand()
    assert card._affix_labels == labels
    card.close()
    assert app is not None


def test_create_and_delete_update_both_visible_lists_without_rebuilding(monkeypatch):
    from core.preset_manager import PresetManager
    from ui.main_window import MainWindow
    from ui.pages import page_repo

    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(PresetManager, 'save_presets', lambda self: None)
    window = MainWindow()
    window.show()
    QTest.qWait(150)
    window.switchTo(window.repo_page)
    QTest.qWait(250)

    def no_rebuild():
        raise AssertionError('create/delete rebuilt the complete preset list')

    monkeypatch.setattr(window.shop_page, '_refresh_presets', no_rebuild)
    monkeypatch.setattr(window.repo_page, '_refresh_presets', no_rebuild)
    before = set(window.preset_manager.get_dedicated_presets('normal'))
    window.shop_page._save_dedicated_preset('normal', '增量更新测试', ['测试词条'])
    new_ids = set(window.preset_manager.get_dedicated_presets('normal')) - before
    assert len(new_ids) == 1
    preset_id = new_ids.pop()

    def displayed_ids(page):
        layout = page.preset_container.layout
        return {layout.itemAt(i).widget().preset_data['id']
                for i in range(layout.count())}

    assert preset_id in displayed_ids(window.shop_page)
    assert preset_id in displayed_ids(window.repo_page)

    monkeypatch.setattr(page_repo.MessageBox, 'exec', lambda self: page_repo.MessageBox.Accepted)
    window.repo_page._delete_preset(preset_id)
    assert preset_id not in displayed_ids(window.shop_page)
    assert preset_id not in displayed_ids(window.repo_page)
    window.close()
    assert app is not None
