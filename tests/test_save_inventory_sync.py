import unittest,tempfile
from pathlib import Path
from core.relic_inventory import RelicInventory

class SaveSyncTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=Path(__file__).parent)
        self.addCleanup(self.temp.cleanup)
        self.db=RelicInventory(str(Path(self.temp.name)/'inventory.sqlite3'))
        self.snapshot={'source':'save.sl2','digest':'abc'}
        self.item=dict(relic_type='normal',color='红',affixes=['提升物理攻击力'],handle=1,acquisition=1)

    def test_replace_duplicates_repeat_and_remove(self):
        self.db.save_manual(None,'normal','蓝',['提升精力上限'])
        slot={'slot':'USERDATA_0','errors':[],'items':[self.item,dict(self.item,handle=2)]}
        self.db.sync_save(self.snapshot,slot)
        rows=self.db.list_owned()
        self.assertEqual(len(rows),2)
        ids={r['id'] for r in rows}
        self.db.sync_save(self.snapshot,slot)
        self.assertEqual({r['id'] for r in self.db.list_owned()},ids)
        slot['items']=[self.item]
        self.db.sync_save(self.snapshot,slot)
        self.assertEqual(len(self.db.list_owned()),1)
        slot['errors']=['unknown ID']
        with self.assertRaises(ValueError):self.db.sync_save(self.snapshot,slot)
        self.assertEqual(len(self.db.list_owned()),1)

    def test_transaction_failure_keeps_previous_inventory(self):
        original=self.db.save_manual(None,'normal','红',['提升物理攻击力'])
        broken=dict(self.item,handle=2)
        del broken['color']
        with self.assertRaises(KeyError):
            self.db.sync_save(self.snapshot,{'slot':'USERDATA_0','errors':[],'items':[self.item,broken]})
        self.assertEqual([r['id'] for r in self.db.list_owned()],[original])

    def test_official_only_if_present(self):
        self.assertEqual(self.db.list_owned(),[])
        item=dict(self.item,official_id=1,name='官方遗物')
        self.db.sync_save(self.snapshot,{'slot':'USERDATA_0','errors':[],'items':[item]})
        self.assertEqual(self.db.list_owned()[0]['official_id'],1)
        with self.assertRaises(ValueError):self.db.delete_owned([self.db.list_owned()[0]['id']])

if __name__=='__main__':unittest.main()
