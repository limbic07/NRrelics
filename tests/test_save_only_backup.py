"""存档备份还原不再联动遗物数据库。"""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from core.save_manager import SaveManager

class SaveOnlyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=Path(__file__).parent)
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.manager = SaveManager.__new__(SaveManager)
        self.manager.SAVE_DIR_BASE = str(root / 'game')
        self.manager.BACKUP_DIR = str(root / 'backups')
        self.save = Path(self.manager.get_save_path('user'))
        self.save.parent.mkdir(parents=True)
        self.save.write_bytes(b'original')

    def test_backup_without_database_and_ignore_legacy_companion(self):
        self.assertTrue(self.manager.backup_save('user', 'one')[0])
        backup = Path(self.manager.get_backups('user')[0]['path'])
        self.assertEqual(list(backup.parent.iterdir()), [backup])
        legacy = backup.with_suffix('.relic_inventory.sqlite3')
        legacy.write_bytes(b'legacy inventory')
        self.save.write_bytes(b'current')
        self.assertTrue(self.manager.restore_save('user', str(backup))[0])
        self.assertEqual(self.save.read_bytes(), b'original')
        self.assertEqual(Path(str(self.save)+'.bak').read_bytes(), b'current')
        self.assertEqual(legacy.read_bytes(), b'legacy inventory')
        self.assertTrue(self.manager.rename_backup(str(backup), 'two')[0])
        self.assertTrue(self.manager.delete_backup(str(backup.with_name('two.sl2')))[0])
        self.assertEqual(legacy.read_bytes(), b'legacy inventory')

    def test_failed_copy_leaves_current_save_and_no_temporary_file(self):
        self.assertTrue(self.manager.backup_save('user', 'one')[0])
        backup = self.manager.get_backups('user')[0]['path']
        self.save.write_bytes(b'current')
        with patch('core.save_manager.shutil.copy2', side_effect=OSError('copy failed')):
            self.assertFalse(self.manager.restore_save('user', backup)[0])
        self.assertEqual(self.save.read_bytes(), b'current')
        self.assertFalse(list(self.save.parent.glob('.nrrelic_backup_*')))

if __name__ == '__main__': unittest.main()
