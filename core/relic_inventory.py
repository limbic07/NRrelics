"""Append-only scan evidence with a separate, verified inventory flag."""
import hashlib
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

from core.utils import get_user_data_path


class RelicInventory:
    def __init__(self, path=None):
        self.path = path or get_user_data_path('data/relic_inventory.sqlite3')
        with self._connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS relics (
                    id INTEGER PRIMARY KEY, fingerprint TEXT NOT NULL,
                    relic_type TEXT NOT NULL, color TEXT NOT NULL,
                    affixes_json TEXT NOT NULL, confidence REAL NOT NULL,
                    first_seen TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS scans (
                    id INTEGER PRIMARY KEY, scan_id TEXT NOT NULL,
                    relic_id INTEGER NOT NULL REFERENCES relics(id),
                    scanned_at TEXT NOT NULL, ordinal INTEGER NOT NULL,
                    decision TEXT NOT NULL, action TEXT NOT NULL,
                    action_confirmed INTEGER NOT NULL DEFAULT 0,
                    owned_verified INTEGER NOT NULL DEFAULT 0,
                    reason TEXT NOT NULL DEFAULT '',
                    UNIQUE(scan_id, ordinal)
                );
                CREATE TABLE IF NOT EXISTS score_snapshots (
                    scan_id TEXT NOT NULL, ordinal INTEGER NOT NULL,
                    scoring_enabled INTEGER NOT NULL, score INTEGER,
                    details_json TEXT NOT NULL, effective_count INTEGER NOT NULL,
                    preset_id TEXT, preset_name TEXT,
                    settings_hash TEXT NOT NULL,
                    PRIMARY KEY(scan_id, ordinal)
                );
                CREATE INDEX IF NOT EXISTS scans_relic ON scans(relic_id);
                CREATE TABLE IF NOT EXISTS manual_relic_names(
                    relic_id INTEGER PRIMARY KEY REFERENCES relics(id), name TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS inventory_hidden(
                    relic_id INTEGER PRIMARY KEY REFERENCES relics(id));
            ''')
            if 'official_id' not in {row[1] for row in db.execute('PRAGMA table_info(relics)')}:
                db.execute('ALTER TABLE relics ADD COLUMN official_id INTEGER')
        if path is None:
            self.ensure_official_owned()

    def ensure_official_owned(self):
        """Add every bundled official relic once and keep its canonical data locked."""
        from core.official_relics import load_official_relics
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as db:
            for official in load_official_relics():
                identifier = official['id']
                affixes = official['affixes']
                fingerprint = hashlib.sha256(json.dumps(
                    ['normal', official['color'], sorted(affixes)],
                    ensure_ascii=False).encode()).hexdigest()
                existing = db.execute('SELECT id FROM relics WHERE official_id=? ORDER BY id LIMIT 1',
                                      (identifier,)).fetchone()
                if existing:
                    relic_id = existing[0]
                    db.execute('''UPDATE relics SET fingerprint=?,relic_type='normal',color=?,
                        affixes_json=?,confidence=1.0 WHERE id=?''',
                        (fingerprint, official['color'], json.dumps(affixes, ensure_ascii=False), relic_id))
                    db.execute('DELETE FROM inventory_hidden WHERE relic_id=?', (relic_id,))
                else:
                    cursor = db.execute('''INSERT INTO relics
                        (fingerprint,relic_type,color,affixes_json,confidence,first_seen,official_id)
                        VALUES(?,'normal',?,?,1.0,?,?)''',
                        (fingerprint, official['color'], json.dumps(affixes, ensure_ascii=False),
                         now, identifier))
                    relic_id = cursor.lastrowid
                db.execute('INSERT OR REPLACE INTO manual_relic_names(relic_id,name) VALUES(?,?)',
                           (relic_id, official['name']))
                db.execute('''INSERT OR IGNORE INTO scans
                    (scan_id,relic_id,scanned_at,ordinal,decision,action,action_confirmed,
                     owned_verified,reason) VALUES(?,?,?,?,?,?,?,?,?)''',
                    (f'official:{identifier}', relic_id, now, 1, '保留', '保留未动',
                     1, 1, '内置官方遗物'))

    @contextmanager
    def _connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def record(self, scan_id, ordinal, result, settings):
        now = datetime.now(timezone.utc).isoformat()
        affixes = [str(a.get('cleaned_text') or '') for a in result.get('affixes', [])]
        normalized = sorted(affixes)
        fingerprint = hashlib.sha256(json.dumps([result['mode'], result['color'], normalized], ensure_ascii=False).encode()).hexdigest()
        settings_hash = hashlib.sha256(json.dumps(settings.get('scoring', {}), sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        with self._connect() as db:
            relic_id = None
            if result.get('inventory_scan') and result.get('owned_verified'):
                # 同一轮中每件实物只能复用一次；两件完全相同的遗物仍保留两行。
                existing = db.execute('''SELECT r.id FROM relics r
                    WHERE r.fingerprint=?
                      AND EXISTS(SELECT 1 FROM scans s WHERE s.relic_id=r.id AND s.owned_verified=1)
                      AND NOT EXISTS(SELECT 1 FROM inventory_hidden h WHERE h.relic_id=r.id)
                      AND NOT EXISTS(SELECT 1 FROM scans s WHERE s.relic_id=r.id AND s.scan_id=?)
                    ORDER BY r.id LIMIT 1''', (fingerprint, scan_id)).fetchone()
                if existing:
                    relic_id = existing[0]
            if relic_id is None:
                cursor = db.execute('INSERT INTO relics(fingerprint,relic_type,color,affixes_json,confidence,first_seen) VALUES(?,?,?,?,?,?)',
                    (fingerprint, result['mode'], result['color'], json.dumps(affixes, ensure_ascii=False), result['color_confidence'], now))
                relic_id = cursor.lastrowid
            db.execute('INSERT INTO scans(scan_id,relic_id,scanned_at,ordinal,decision,action,action_confirmed,owned_verified,reason) VALUES(?,?,?,?,?,?,?,?,?)',
                (scan_id, relic_id, now, ordinal, result['decision'], result['action'],
                 int(result.get('action_confirmed', False)), int(result.get('owned_verified', False)), result.get('reason', '')))
            db.execute('INSERT INTO score_snapshots VALUES(?,?,?,?,?,?,?,?,?)',
                (scan_id, ordinal, int(result['scoring_enabled']), result['score'],
                 json.dumps(result['score_details'], ensure_ascii=False), result['effective_count'],
                 result.get('preset_id'), result.get('preset_name'), settings_hash))

    def update_action(self, scan_id, ordinal, action, confirmed=False, owned=False):
        with self._connect() as db:
            db.execute('UPDATE scans SET action=?, action_confirmed=?, owned_verified=? WHERE scan_id=? AND ordinal=?',
                       (action, int(confirmed), int(owned), scan_id, ordinal))

    def list_owned(self):
        """Return distinct physical relic rows confirmed as owned, including manual entries."""
        with self._connect() as db:
            rows = db.execute('''SELECT r.id,r.relic_type,r.color,r.affixes_json,r.confidence,
                COALESCE(m.name,''),r.official_id FROM relics r LEFT JOIN manual_relic_names m ON m.relic_id=r.id
                WHERE EXISTS(SELECT 1 FROM scans s WHERE s.relic_id=r.id AND s.owned_verified=1)
                  AND NOT EXISTS(SELECT 1 FROM inventory_hidden h WHERE h.relic_id=r.id)
                ORDER BY r.id DESC''').fetchall()
        return [dict(id=row[0], relic_type=row[1], color=row[2],
                     affixes=json.loads(row[3]), confidence=row[4], name=row[5],
                     official_id=row[6]) for row in rows]

    def delete_owned(self, relic_ids):
        """Remove selected physical relics from owned inventory, preserving scan history."""
        ids = list(dict.fromkeys(int(value) for value in relic_ids))
        with self._connect() as db:
            for relic_id in ids:
                row = db.execute('SELECT official_id FROM relics WHERE id=?', (relic_id,)).fetchone()
                if not row:
                    raise ValueError(f'遗物不存在：{relic_id}')
                if row[0] is not None:
                    raise ValueError('内置官方遗物不可删除')
                db.execute('INSERT OR IGNORE INTO inventory_hidden(relic_id) VALUES(?)', (relic_id,))
        return len(ids)

    def save_manual(self, relic_id, relic_type, color, affixes, name='', official_id=None):
        """Create or edit one owned physical relic without rewriting scan evidence."""
        if official_id is not None:
            raise ValueError('官方遗物已内置，不可手动添加或修改')
        if relic_type not in ('normal', 'deepnight') or color not in ('红', '蓝', '绿', '黄'):
            raise ValueError('遗物类型或颜色无效')
        if not isinstance(affixes, list) or not affixes or any(not isinstance(a,str) or not a.strip() for a in affixes):
            raise ValueError('请填写至少一条词条')
        affixes = [a.strip() for a in affixes]
        now = datetime.now(timezone.utc).isoformat()
        fingerprint = hashlib.sha256(json.dumps([relic_type,color,sorted(affixes)],ensure_ascii=False).encode()).hexdigest()
        with self._connect() as db:
            if relic_id is None:
                cursor=db.execute('INSERT INTO relics(fingerprint,relic_type,color,affixes_json,confidence,first_seen,official_id) VALUES(?,?,?,?,?,?,?)',
                    (fingerprint,relic_type,color,json.dumps(affixes,ensure_ascii=False),1.0,now,official_id))
                relic_id=cursor.lastrowid
                db.execute('INSERT INTO scans(scan_id,relic_id,scanned_at,ordinal,decision,action,action_confirmed,owned_verified,reason) VALUES(?,?,?,?,?,?,?,?,?)',
                    ('manual:'+str(relic_id),relic_id,now,1,'保留','保留未动',1,1,'手动添加'))
            else:
                existing = db.execute('SELECT official_id FROM relics WHERE id=?',(relic_id,)).fetchone()
                if not existing:
                    raise ValueError('遗物不存在')
                if existing[0] is not None:
                    raise ValueError('内置官方遗物不可修改')
                db.execute('UPDATE relics SET fingerprint=?,relic_type=?,color=?,affixes_json=?,confidence=1.0,official_id=? WHERE id=?',
                    (fingerprint,relic_type,color,json.dumps(affixes,ensure_ascii=False),official_id,relic_id))
            db.execute('INSERT OR REPLACE INTO manual_relic_names VALUES(?,?)',(relic_id,name.strip()))
        return relic_id
