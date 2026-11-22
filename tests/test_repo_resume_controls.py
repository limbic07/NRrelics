from unittest.mock import Mock

from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication


def test_pause_offers_mouse_and_keyboard_resume(monkeypatch):
    from ui.pages.page_repo import RepoPage

    app = QApplication.instance() or QApplication([])
    page = RepoPage(preset_manager=Mock())
    cleaner = Mock(is_running=True, is_paused=True, game_window=None)
    page.repo_cleaner = cleaner
    page.cleaning_thread = Mock()
    page.cleaning_thread.isRunning.return_value = True
    monkeypatch.setattr(page, '_start_cleaning', Mock(side_effect=AssertionError('restarted run')))
    try:
        page._show_pause_prompt('测试原因', 'item')
        assert page.start_btn.text() == '继续清理'
        page.start_btn.click()
        assert not page.pause_dialog.isVisible()
        assert page.resume_timer.interval() == 1000
        assert page.resume_seconds == 5
        page._on_start_shortcut()
        for _ in range(4):
            page._tick_resume()
        cleaner.resume_cleaning.assert_not_called()
        cleaner.game_in_foreground.return_value = False
        page._tick_resume()
        assert page.pause_dialog.isVisible() and page.start_btn.isEnabled()
        cleaner.resume_cleaning.assert_not_called()

        cleaner.game_in_foreground.return_value = True
        page.start_btn.click()
        for _ in range(5):
            page._tick_resume()
        cleaner.resume_cleaning.assert_called_once()
        assert page.pause_dialog is None and not page.start_btn.isEnabled()

        page._show_pause_prompt('测试原因', 'item')
        page.pause_dialog.hide()
        page._on_start_shortcut()
        assert cleaner.resume_cleaning.call_count == 2
        page._show_pause_prompt('测试原因', 'item')
        page.start_btn.click()
        page._stop_cleaning()
        assert not page.resume_timer.isActive()
        assert cleaner.resume_cleaning.call_count == 2
    finally:
        page._dismiss_pause_prompt()
        page.close()


def test_registered_hotkey_reaches_background_window(monkeypatch):
    import pytest
    import win32con
    import win32gui
    from ui.main_window import MainWindow

    app = QApplication.instance() or QApplication([])
    if app.platformName() != 'windows':
        pytest.skip('Requires a native Windows message queue')
    window = MainWindow()
    try:
        page = window.repo_page
        page.start_btn.setEnabled(True)
        start = Mock()
        monkeypatch.setattr(page, '_start_cleaning', start)
        window.stackedWidget.setAnimationEnabled(False)
        window.stackedWidget.setCurrentWidget(page)
        assert not window.isVisible()
        assert win32con.VK_F10 in window._repo_hotkeys
        win32gui.PostMessage(int(window.winId()), win32con.WM_HOTKEY, win32con.VK_F10,
                             win32con.VK_F10 << 16)
        QTest.qWait(100)
        start.assert_called_once()
        window.stackedWidget.setCurrentWidget(window.shop_page)
        assert not window._repo_hotkeys
    finally:
        window.close()
