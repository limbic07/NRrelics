import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import unittest
from types import SimpleNamespace
from unittest.mock import Mock,patch
from PySide6.QtCore import QCoreApplication,QEvent,QTimer
from PySide6.QtWidgets import QApplication,QWidget
from ui.pages.page_relics import RelicPage,LoadoutResultDialog,SolveWorker
class LifetimeTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
 def test_dialogs(self):
  page=QWidget()
  relics=[dict(id=i,relic_type='normal' if i<3 else 'deepnight',color='红',slot_index=i%3,affixes=['提升物理攻击力'],score_contribution=10) for i in range(6)]
  page.latest_result=dict(score=60,min_score=45,min_ratio=.75,solutions=[dict(vessel='test',score=60,relics=relics) for _ in range(10)])
  page.search_snapshot=(None,None,{i:i+1 for i in range(6)})
  for _ in range(30):
   QTimer.singleShot(0,lambda:self.app.activeModalWidget().accept())
   RelicPage._open_result(page)
   QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete)
   self.assertEqual(page.findChildren(LoadoutResultDialog),[])
  page.deleteLater()
  QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete)
 def test_history(self):
  page=SimpleNamespace(pending_next=False,page_offset=0,result_pages=[],_display_page=Mock())
  for i in range(50):
   RelicPage._show_result(page,dict(solutions=[{}],excluded_combinations=[[j] for j in range(i+1)]))
   page.pending_next=True
  self.assertEqual(len(page.seen_combinations),50)
  self.assertTrue(all('excluded_combinations' not in r for r in page.result_pages))
 def test_worker_inputs(self):
  for error in [None,RuntimeError('test')]:
   w=SolveWorker((object(),),{'payload':object()})
   with patch('ui.pages.page_relics.optimize',return_value={},side_effect=error):w.run()
   self.assertEqual((w.args,w.kwargs),((),{}))
   w.deleteLater()
  QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete)
 def test_running_worker_blocks_duplicate_requests(self):
  page=SimpleNamespace(worker=object())
  RelicPage._solve(page)
  RelicPage._next_page(page)
 def test_finished_worker(self):
  w=Mock();page=SimpleNamespace(worker=w,solve=Mock(),result_pages=[])
  RelicPage._search_finished(page)
  self.assertIsNone(page.worker);w.deleteLater.assert_called_once()
if __name__=='__main__':unittest.main()
