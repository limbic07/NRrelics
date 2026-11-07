"""存档和遗物库存必须成对备份与还原。"""

import os
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from core.save_manager import SaveManager


class SaveInventoryBackupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=Path(__file__).parent)
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.manager = SaveManager.__new__(SaveManager)
        self.manager.SAVE_DIR_BASE = str(root / "game")
        self.manager.BACKUP_DIR = str(root / "backups")
        self.manager.INVENTORY_PATH = str(root / "data" / "relic_inventory.sqlite3")
        self.save = Path(self.manager.get_save_path("user"))
        self.save.parent.mkdir(parents=True)
        self.save.write_bytes(b"original save")
        Path(self.manager.INVENTORY_PATH).parent.mkdir(parents=True)
        with closing(sqlite3.connect(self.manager.INVENTORY_PATH)) as db:
            db.execute("CREATE TABLE relics (value TEXT)")
            db.execute("INSERT INTO relics VALUES ('original inventory')")
            db.commit()

    def _inventory_value(self):
        with closing(sqlite3.connect(self.manager.INVENTORY_PATH)) as db:
            return db.execute("SELECT value FROM relics").fetchone()[0]

    def test_backup_and_restore_both_files(self):
        ok, _ = self.manager.backup_save("user", "one")
        self.assertTrue(ok)
        backup = self.manager.get_backups("user")[0]
        self.assertTrue(backup["has_inventory"])
        self.save.write_bytes(b"new save")
        with closing(sqlite3.connect(self.manager.INVENTORY_PATH)) as db:
            db.execute("UPDATE relics SET value='new inventory'")
            db.commit()
        ok, _ = self.manager.restore_save("user", backup["path"])
        self.assertTrue(ok)
        self.assertEqual(self.save.read_bytes(), b"original save")
        self.assertEqual(self._inventory_value(), "original inventory")
        self.assertEqual(Path(self.manager.INVENTORY_PATH + ".bak").exists(), True)
        # 重复还原会更新 .bak，不应阻塞下一次恢复。
        ok, _ = self.manager.restore_save("user", backup["path"])
        self.assertTrue(ok)

    def test_legacy_backup_keeps_inventory(self):
        old = Path(self.manager.BACKUP_DIR) / "user" / "old.sl2"
        old.parent.mkdir(parents=True)
        old.write_bytes(b"old save")
        ok, message = self.manager.restore_save("user", str(old))
        self.assertTrue(ok)
        self.assertIn("不含遗物库存", message)
        self.assertEqual(self._inventory_value(), "original inventory")

    def test_corrupt_inventory_refuses_restore(self):
        ok, _ = self.manager.backup_save("user", "one")
        self.assertTrue(ok)
        backup = self.manager.get_backups("user")[0]
        self.save.write_bytes(b"new save")
        Path(self.manager._inventory_backup_path(backup["path"])).write_bytes(b"not sqlite")
        ok, _ = self.manager.restore_save("user", backup["path"])
        self.assertFalse(ok)
        self.assertEqual(self.save.read_bytes(), b"new save")

    def test_rename_and_delete_keep_pair_together(self):
        ok, _ = self.manager.backup_save("user", "one")
        self.assertTrue(ok)
        old = self.manager.get_backups("user")[0]["path"]
        ok, _ = self.manager.rename_backup(old, "two")
        self.assertTrue(ok)
        new = self.manager.get_backups("user")[0]["path"]
        self.assertTrue(os.path.exists(self.manager._inventory_backup_path(new)))
        ok, _ = self.manager.delete_backup(new)
        self.assertTrue(ok)
        self.assertFalse(os.path.exists(self.manager._inventory_backup_path(new)))


if __name__ == "__main__":
    unittest.main()
