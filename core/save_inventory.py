"""Read a stable save snapshot and map effect IDs to the application's vocabulary.

Save parser and reference data are adapted from limbic07/NRrelics PR #9;
see data/relic_validation/LICENSE-MIT.txt. No game-save writes are performed.
"""
import csv
import hashlib
import json
import re
import unicodedata
import xml.etree.ElementTree as ET
from pathlib import Path

from core.utils import get_resource_path
from core.relic_validation import ReadOnlySaveReader, RuleData, SaveReadError
from core.official_relics import load_official_relics, identify_official_relic


def _normalize(text):
    text = text.split('※', 1)[0]
    return re.sub(r'[\s，,。、“”"：:；;]', '', unicodedata.normalize('NFKC', text))


def read_save_inventory(path):
    path = Path(path).resolve()
    before = path.stat()
    with path.open('rb') as stream:
        raw = stream.read(ReadOnlySaveReader.MAX_SAVE_BYTES + 1)
    after = path.stat()
    if len(raw) > ReadOnlySaveReader.MAX_SAVE_BYTES:
        raise SaveReadError('存档过大')
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise SaveReadError('游戏正在保存，请稍后重试')
    root = Path(get_resource_path('data/relic_validation'))
    rules = RuleData.load(root)
    reader = ReadOnlySaveReader(rules)
    payloads = reader._read_bnd4_entries(raw)
    with (root/'AttachEffectParam.csv').open(encoding='utf-8-sig', newline='') as stream:
        params = {int(r['ID']): r for r in csv.DictReader(stream)}
    with (root/'EquipParamAntique.csv').open(encoding='utf-8-sig', newline='') as stream:
        types = {int(r['ID']): r for r in csv.DictReader(stream)}
    catalog = json.loads(Path(get_resource_path('data/affix_catalog.json')).read_text(encoding='utf-8'))
    names = {int(e['id']): e['name'] for e in catalog['effects']}
    game_names = {}
    for filename in ('AttachEffectName.fmg.xml', 'AttachEffectName_dlc01.fmg.xml'):
        for entry in ET.parse(root/filename).findall('./entries/text'):
            if entry.text and entry.text != '%null%':
                game_names[int(entry.attrib['id'])] = entry.text
    pools = {}
    for pool, files in (('normal', ('normal.txt','normal_special.txt')), ('deepnight',('deepnight_pos.txt',)), ('negative',('deepnight_neg.txt',))):
        index = {}
        for filename in files:
            for name in Path(get_resource_path('data/'+filename)).read_text(encoding='utf-8-sig').splitlines():
                if name.strip(): index[_normalize(name)] = name.strip()
        pools[pool] = index
    officials = load_official_relics()
    official_names = {_normalize(a): a for o in officials for a in o['affixes']}
    unique_ids = reader._unique_ids()
    colors = {'Red':'红','Blue':'蓝','Yellow':'黄','Green':'绿'}
    slots = []
    for slot, payload in payloads.items():
        records = reader._read_relics(payload, f'USERDATA_{slot}')
        if not records: continue
        converted, errors = [], []
        for record in records:
            meta = types.get(record.relic_id)
            if not meta or record.color not in colors:
                errors.append(f'遗物 {record.index+1} 的类型或颜色未知（ID {record.relic_id}）');continue
            mode = 'deepnight' if meta['isDeepRelic']=='1' else 'normal'
            affixes = []
            for i, eid in enumerate(record.effects):
                if eid in reader.EMPTY_EFFECTS: continue
                index = pools['negative' if i>=3 else mode]
                candidates = (names.get(eid,''), game_names.get(int(params.get(eid,{}).get('attachTextId',-1)),''), game_names.get(eid,''))
                name = next((index[_normalize(n)] for n in candidates if n and _normalize(n) in index), None)
                # 普通官方遗物也可以包含仅在深夜库中提供的词条。
                if name is None and i < 3 and record.relic_id in unique_ids:
                    other = pools['deepnight' if mode == 'normal' else 'normal']
                    name = next((other[_normalize(n)] for n in candidates if n and _normalize(n) in other), None)
                # 官方专用词条允许使用已经校对过的官方目录名称。
                if name is None and record.relic_id in unique_ids:
                    name = next((official_names[_normalize(n)] for n in candidates if n and _normalize(n) in official_names), None)
                if name is None: errors.append(f'遗物 {record.index+1} 的词条ID {eid} 不在当前词条库')
                else: affixes.append(name)
            item = dict(relic_type=mode,color=colors[record.color],affixes=affixes,
                        handle=record.handle,acquisition=record.acquisition,game_id=record.relic_id,
                        favorite=record.favorite,name='')
            if record.relic_id in unique_ids:
                item['official_id'] = identify_official_relic(item)
                if item['official_id'] is not None:
                    item['name'] = next(o['name'] for o in officials if o['id']==item['official_id'])
            converted.append(item)
        slots.append(dict(slot=f'USERDATA_{slot}',name=records[0].player_name,items=converted,errors=errors))
    if not slots: raise SaveReadError('未读取到有遗物的存档槽位，当前库存未更改')
    return dict(source=str(path), digest=hashlib.sha256(raw).hexdigest(),slots=slots)
