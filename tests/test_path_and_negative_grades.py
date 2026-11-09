"""Regression checks for Unicode templates and per-build negative grades."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import numpy as np
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from core.relic_detector import RelicDetector
from core.relic_matcher import match_relic
from core.relic_scoring import normalize_scoring, normalize_affix_tiers
from core.preset_manager import PresetManager
from ui.dialogs.preset_edit_dialog import PresetEditDialog

class RegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_unicode_template(self):
        import cv2
        with tempfile.TemporaryDirectory(prefix='遗物模板', dir=Path(__file__).resolve().parent) as folder:
            path=Path(folder)/'中文图标.png'
            path.write_bytes(cv2.imencode('.png', np.full((20,20,3), 128, dtype=np.uint8))[1].tobytes())
            detector=RelicDetector.__new__(RelicDetector)
            with patch('core.relic_detector.get_resource_path', side_effect=lambda p:p):
                self.assertEqual(detector._load_template(str(path)).shape, (20,20))
                path.write_bytes(b'broken')
                self.assertIsNone(detector._load_template(str(path)))

    def test_missing_templates_stop_before_game_actions(self):
        from core.repo_cleaner import RepoCleaner
        from unittest.mock import Mock
        cleaner=RepoCleaner.__new__(RepoCleaner)
        cleaner.settings={}
        cleaner.repository_filter=SimpleNamespace()
        cleaner.relic_detector=SimpleNamespace(template_cup=None,template_bookmark=None)
        cleaner._reset_stats=Mock()
        cleaner._find_game_window=Mock()
        messages=[]
        cleaner.start_cleaning('normal','sell',0,False,True,
                               log_callback=lambda message, level:messages.append(message))
        cleaner._find_game_window.assert_not_called()
        self.assertEqual(cleaner.stop_reason,'error')
        self.assertFalse(cleaner.is_running)
        self.assertTrue(messages)

    def test_dark_dialogs_and_table(self):
        from PySide6.QtGui import QPalette
        from PySide6.QtWidgets import QTableWidget
        from ui.main_window import MainWindow
        from ui.dialogs.optimizer_constraint_dialog import ConstraintGroupDialog
        from ui.pages.page_relics import EditRelicDialog
        with patch('ui.main_window.THEME_CONFIG', {'theme':'dark'}), patch.object(MainWindow, '_init_pages'), patch('ui.main_window.PresetManager'):
            window=MainWindow()
        self.assertFalse(window.isMicaEffectEnabled())
        self.assertEqual(window.backgroundColor.alpha(),255)
        self.assertLess(window.backgroundColor.lightness(),100)
        dialogs=[PresetEditDialog(['test']), ConstraintGroupDialog([{'kind':'affix','name':'test'}]), EditRelicDialog()]
        table=QTableWidget(1,1)
        for widget in dialogs+[table]:
            widget.ensurePolished()
            self.assertLess(widget.palette().color(QPalette.Base).lightness(),100)
            self.assertGreater(widget.palette().color(QPalette.Text).lightness(),180)
            widget.close()
        window.close()

    def test_light_background_after_dark(self):
        from PySide6.QtGui import QPalette
        from PySide6.QtWidgets import QScrollArea, QWidget
        from ui.main_window import MainWindow
        for theme, expected in [('dark','#202020'),('light','#f5f5f5')]:
            with patch('ui.main_window.THEME_CONFIG', {'theme':theme}), patch.object(MainWindow, '_init_pages'), patch('ui.main_window.PresetManager'):
                window=MainWindow()
            scroll=QScrollArea()
            content=QWidget()
            scroll.setWidget(content)
            self.assertEqual(content.palette().color(QPalette.Window).name(),expected)
            if theme=='light':
                self.assertEqual(content.palette().color(QPalette.Text).name(),'#202020')
                self.assertEqual(content.palette().color(QPalette.Base).name(),'#ffffff')
            scroll.close()
            window.close()

    def test_negative_positive_in_both_modes(self):
        for mode in ('normal','deepnight'):
            for tier, points in [('harmful',-4),('unacceptable',-12),('negligible',0)]:
                p=dict(id='test', name='test', affixes=['甲','乙','丙'],
                       affix_tiers={'甲':'core','乙':'core','丙':tier},is_active=True)
                self.assertTrue(normalize_affix_tiers(p)[1])
                observation={'success':True,'affixes':[{'cleaned_text':n,'is_positive':True} for n in p['affixes']]}
                result=match_relic(observation,None,[p],threshold=3,
                                  scoring_config={'enabled':True},mode=mode)
                self.assertEqual(result.candidate_match.score,20+points)
                self.assertEqual(result.candidate_match.effective_count,2)
                self.assertFalse(result.qualified)
                result=match_relic(observation,None,[p],threshold=3,mode=mode)
                self.assertFalse(result.qualified)

    def test_editor_negative_order_and_save(self):
        for mode in ('normal','deepnight'):
            dialog=PresetEditDialog(['甲','乙'],mode=mode,exception_vocabulary=['原生负面'])
            dialog._switch_tier('harmful')
            names=[dialog.vocab_list.item(i).data(Qt.UserRole) for i in range(dialog.vocab_list.count())]
            self.assertEqual(names[0], '原生负面' if mode=='deepnight' else '甲')
            dialog.vocab_list.item(names.index('甲')).setCheckState(Qt.Checked)
            self.assertEqual(dialog.get_affix_tiers()['甲'],'harmful')
            self.assertEqual(PresetManager._checked_tiers(['甲'],dialog.get_affix_tiers())['甲'],'harmful')
            dialog.close()

    def test_optimizer_cannot_avoid_penalty(self):
        from core.loadout_optimizer import optimize, load_catalog
        builds,vessels=load_catalog()
        build=next(b for b in builds if b['id']=='C17')
        vessel=next(v for v in vessels if v['hero_en']=='Wylder')
        colors={'Red':'红','Blue':'蓝','Green':'绿','Yellow':'黄','White (any colour)':'红'}
        p=dict(id='test',affixes=['甲','乙'],affix_tiers={'甲':'core','乙':'harmful'})
        presets=SimpleNamespace(normal_general={'affixes':[]},deepnight_general={'affixes':[]},
                                normal_dedicated={'test':p},deepnight_whitelist_dedicated={})
        relics=[dict(id=i+1,relic_type='normal',color=colors[c.strip()],affixes=['甲','乙'],name='')
                for i,c in enumerate(vessel['normal_en'].split(','))]
        result=optimize(build,relics,[vessel],presets,normalize_scoring({'enabled':True}),
                        normal_preset_id='test',deepnight_preset_id='none',time_limit=5)
        self.assertIsNotNone(result)
        self.assertEqual(result['score'],-2)  # one positive effect; three penalties
        self.assertEqual(sum(r['score_contribution'] for r in result['relics']),-2)

if __name__=='__main__':unittest.main()
