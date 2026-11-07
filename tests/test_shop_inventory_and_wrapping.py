import unittest
from unittest.mock import Mock, patch
from core.ocr_engine import EntryCorrector, correct_entries, correct_entries_with_info
from core.shop_automation import ShopAutomation

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

    def test_shop_records_color_and_duplicate_physical_items(self):
        shop=ShopAutomation.__new__(ShopAutomation)
        shop.settings={'scoring':{'enabled':True}}
        shop.inventory=Mock();shop.scan_id='round'
        candidate=Mock(score=16,score_details=[('虚血',10),('大盾',6)],effective_count=2,
                       preset_id='a',preset_name='肉鸟',score_grade='keep')
        match=Mock(best_match=candidate,destructive_action_allowed=True)
        with patch('core.shop_automation.recognize_color',return_value=('黄',.99)) as color:
            for ordinal in (1,2):
                shop._record_kept_relic('normal',ordinal,{'affixes':[]},match,'screen',Mock())
            color.assert_called_with('screen',layout='shop')
        self.assertEqual(shop.inventory.record.call_count,2)
        args=shop.inventory.record.call_args.args
        self.assertEqual(args[1],2)
        self.assertTrue(args[2]['owned_verified'])
        self.assertEqual(args[2]['score'],16)
        match.destructive_action_allowed=False
        shop._record_kept_relic('normal',3,{'affixes':[]},match,None,Mock())
        self.assertFalse(shop.inventory.record.call_args.args[2]['owned_verified'])

if __name__=='__main__':unittest.main()
