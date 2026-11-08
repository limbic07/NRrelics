import unittest
from unittest.mock import Mock
from core.ocr_engine import EntryCorrector, correct_entries, correct_entries_with_info

class RegressionTests(unittest.TestCase):
    def test_wrapped_affix_consumes_tail(self):
        prefix='【送葬者】使用祷告将辅助效果附加在自己身上时'
        tail='提升物理攻击力'
        full=prefix+tail
        c=EntryCorrector([full,tail,'提升刺剑的攻击力','强化狩猎神祇的祷告'])
        rows=[prefix,tail,'提升刺剑的攻击力','强化狩猎神祇的祷告']
        expected=[full,*rows[2:]]
        self.assertEqual(correct_entries(rows,c),expected)
        self.assertEqual([r['text'] for r in correct_entries_with_info(rows,c)],expected)
        self.assertEqual([r['text'] for r in correct_entries_with_info([full,tail],c)],[full,tail])

    def test_rejected_merge_stays_unknown(self):
        c=Mock()
        c.correct_entry.side_effect=lambda text: (text, .7 if text=='甲乙' else .6, False)
        self.assertTrue(all(not r['is_corrected'] for r in correct_entries_with_info(['甲','乙'],c)))


if __name__=='__main__':unittest.main()
