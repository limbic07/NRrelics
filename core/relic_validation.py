"""Read-only Nightreign PC save inventory parsing.

This module intentionally has no save writer, mmap, or editor dependency.  It
reads a bounded copy of a PC BND4 save into memory, decrypts only the profile
entries and reads inventory records. Adapted from NRrelics PR #9;
see data/relic_validation/LICENSE-MIT.txt.
"""

from __future__ import annotations

import csv
import struct
from dataclasses import dataclass, field
from pathlib import Path

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes


@dataclass(frozen=True)
class RelicRecord:
    index: int
    relic_id: int
    effects: tuple[int, ...]
    color: str
    name: str
    favorite: bool
    equipped: bool
    handle: int = 0
    acquisition: int = 0
    slot: str = ""
    player_name: str = ""


@dataclass
class RuleData:
    relics: dict[int, dict[str, object]] = field(default_factory=dict)

    @classmethod
    def load(cls, root: Path | None = None) -> "RuleData":
        root = root or Path(__file__).resolve().parents[1] / "data" / "relic_validation"
        data = cls()
        with (root / "EquipParamAntique.csv").open(encoding="utf-8-sig", newline="") as stream:
            for row in csv.DictReader(stream):
                relic_id = int(row["ID"])
                data.relics[relic_id] = {
                    "name": row.get("Name", "") or f"Relic {relic_id}",
                    "color": _color_name(row.get("relicColor")),
                }
        return data


class SaveReadError(ValueError):
    """The save cannot be safely parsed as a supported PC save."""


class ReadOnlySaveReader:
    MAX_SAVE_BYTES = 128 * 1024 * 1024
    BND4_HEADER = 64
    BND4_ENTRY = 32
    INVENTORY_SLOTS = range(10)
    STATE_OFFSET = 0x14
    STATE_COUNT = 5120
    ENTRY_COUNT = 3065
    RELIC_TYPE = 0xC0000000
    GOODS_TYPE = 0xB0000000
    EMPTY_EFFECTS = {0, 0xFFFFFFFF}
    SAVE_KEY = bytes.fromhex("18f6326605bd178a5524523ac0a0c609")
    UNIQUE_RANGES = (range(1000, 2101), range(10000, 20000))

    def __init__(self, rule_data: RuleData | None = None):
        self.rule_data = rule_data or RuleData.load()


    def _read_bnd4_entries(self, raw: bytes) -> dict[int, bytes]:
        if len(raw) < self.BND4_HEADER or raw[:4] != b"BND4":
            raise SaveReadError("不是受支持的 PC BND4 存档")
        count = struct.unpack_from("<I", raw, 12)[0]
        if count < 10 or count > 4096:
            raise SaveReadError("BND4 条目数量不包含完整玩家槽位")
        header_end = self.BND4_HEADER + count * self.BND4_ENTRY
        if header_end > len(raw):
            raise SaveReadError("BND4 条目表超出文件边界")
        payloads = {}
        for index in self.INVENTORY_SLOTS:
            pos = self.BND4_HEADER + index * self.BND4_ENTRY
            if raw[pos:pos + 8] != b"\x40\x00\x00\x00\xff\xff\xff\xff":
                raise SaveReadError(f"缺少 USERDATA_{index} 条目")
            size, _unknown, offset, _name, _footer = struct.unpack_from("<5i", raw, pos + 8)
            if size < 32 or offset < header_end or offset + size > len(raw):
                raise SaveReadError(f"USERDATA_{index} 条目边界无效")
            encrypted = raw[offset:offset + size]
            if len(encrypted) < 32 or (len(encrypted) - 16) % 16:
                raise SaveReadError(f"USERDATA_{index} 加密数据长度无效")
            try:
                decryptor = Cipher(algorithms.AES(self.SAVE_KEY), modes.CBC(encrypted[:16])).decryptor()
                payloads[index] = decryptor.update(encrypted[16:]) + decryptor.finalize()
            except Exception as exc:
                raise SaveReadError(f"USERDATA_{index} 解密失败：{exc}") from exc
        return payloads


    def _read_relics(self, payload: bytes, slot: str = "") -> list[RelicRecord]:
        states: dict[int, tuple[int, bytes]] = {}
        cursor = self.STATE_OFFSET
        for _ in range(self.STATE_COUNT):
            if cursor + 8 > len(payload):
                raise SaveReadError("物品状态区超出边界")
            ga_handle, item_id = struct.unpack_from("<II", payload, cursor)
            type_bits = ga_handle & 0xF0000000
            size = {0: 8, self.GOODS_TYPE: 8, 0x80000000: 88,
                    0x90000000: 16, self.RELIC_TYPE: 80}.get(type_bits)
            if size is None or cursor + size > len(payload):
                raise SaveReadError("发现未知物品类型或损坏的状态记录")
            if ga_handle:
                states[ga_handle] = (item_id & 0x00FFFFFF, payload[cursor:cursor + size])
            cursor += size
        cursor += 0x94
        if cursor + 32 > len(payload):
            raise SaveReadError("角色名称区超出边界")
        raw_name = payload[cursor:cursor + 32]
        end = next((offset for offset in range(0, 32, 2)
                    if raw_name[offset:offset + 2] == b"\0\0"), 32)
        try:
            player_name = raw_name[:end].decode("utf-16-le").strip()
        except UnicodeDecodeError:
            player_name = ""
        cursor += 0x5B8
        if cursor + 4 + self.ENTRY_COUNT * 14 > len(payload):
            raise SaveReadError("物品条目区超出边界")
        cursor += 4
        relics = []
        for index in range(self.ENTRY_COUNT):
            entry = payload[cursor:cursor + 14]
            cursor += 14
            ga_handle, _amount, _acquisition = struct.unpack_from("<III", entry)
            if (ga_handle & 0xF0000000) != self.RELIC_TYPE:
                continue
            state = states.get(ga_handle)
            if state is None or len(state[1]) < 80:
                raise SaveReadError("遗物条目缺少状态记录")
            relic_id, state_data = state
            effects = tuple(struct.unpack_from("<I", state_data, offset)[0]
                            for offset in (16, 20, 24, 56, 60, 64))
            meta = self.rule_data.relics.get(relic_id, {})
            relics.append(RelicRecord(
                index=index, relic_id=relic_id, effects=effects,
                handle=ga_handle, acquisition=_acquisition,
                color=str(meta.get("color", "Unknown")),
                name=str(meta.get("name", f"Relic {relic_id}")),
                favorite=bool(entry[12]), equipped=False, slot=slot, player_name=player_name))
        return relics


    def _unique_ids(self) -> set[int]:
        return {value for span in self.UNIQUE_RANGES for value in span}


def _color_name(value: str | None) -> str:
    return {"0": "Red", "1": "Blue", "2": "Yellow", "3": "Green", "4": "White"}.get(
        value or "", "Unknown")
