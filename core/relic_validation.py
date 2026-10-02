"""Read-only Nightreign PC save validation.

This module intentionally has no save writer, mmap, or editor dependency.  It
reads a bounded copy of a PC BND4 save into memory, decrypts only the profile
entry, and reports only rules supported by the bundled reference tables.
"""

from __future__ import annotations

import csv
import struct
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Iterable

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes


class ValidationStatus(str, Enum):
    CONFORMS = "conforms"
    VIOLATES = "violates"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class RelicRecord:
    index: int
    relic_id: int
    effects: tuple[int, ...]
    color: str
    name: str
    favorite: bool
    equipped: bool
    slot: str = ""
    player_name: str = ""


@dataclass(frozen=True)
class RelicResult:
    relic: RelicRecord
    status: ValidationStatus
    reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class ValidationReport:
    status: ValidationStatus
    results: tuple[RelicResult, ...] = ()
    reasons: tuple[str, ...] = ()
    source: str = ""


@dataclass
class RuleData:
    relics: dict[int, dict[str, object]] = field(default_factory=dict)
    effects: dict[int, dict[str, int]] = field(default_factory=dict)
    pools: dict[int, set[int]] = field(default_factory=dict)
    pool_ids: set[int] = field(default_factory=set)
    effect_pools: dict[int, set[int]] = field(default_factory=dict)

    @classmethod
    def load(cls, root: Path | None = None) -> "RuleData":
        root = root or Path(__file__).resolve().parents[1] / "data" / "relic_validation"

        def rows(name: str) -> Iterable[dict[str, str]]:
            with (root / name).open("r", encoding="utf-8-sig", newline="") as handle:
                yield from csv.DictReader(handle)

        data = cls()
        for row in rows("EquipParamAntique.csv"):
            try:
                relic_id = int(row["ID"])
            except (KeyError, TypeError, ValueError):
                continue
            data.relics[relic_id] = {
                "name": row.get("Name", "") or f"Relic {relic_id}",
                "color": _color_name(row.get("relicColor")),
                "slots": tuple(_int(row.get(key), -1) for key in (
                    "attachEffectTableId_1", "attachEffectTableId_2",
                    "attachEffectTableId_3", "attachEffectTableId_curse1",
                    "attachEffectTableId_curse2", "attachEffectTableId_curse3")),
            }
        for row in rows("AttachEffectParam.csv"):
            try:
                effect_id = int(row["ID"])
            except (KeyError, TypeError, ValueError):
                continue
            data.effects[effect_id] = {
                "conflict": _int(row.get("compatibilityId"), -1),
                "sort": _int(row.get("overrideEffectId"), effect_id),
            }
        for row in rows("AttachEffectTableParam.csv"):
            table_id = _int(row.get("ID"), -1)
            effect_id = _int(row.get("attachEffectId"), -1)
            if table_id >= 0:
                data.pool_ids.add(table_id)
            if (table_id >= 0 and effect_id >= 0
                    and (_int(row.get("chanceWeight_dlc"), -1) > 0
                         or (_int(row.get("chanceWeight"), 0) != 0
                             and _int(row.get("chanceWeight_dlc"), -1) == -1))):
                data.pools.setdefault(table_id, set()).add(effect_id)
                data.effect_pools.setdefault(effect_id, set()).add(table_id)
        return data


class SaveReadError(ValueError):
    """The save cannot be safely parsed as a supported PC save."""


class ReadOnlySaveValidator:
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
    ILLEGAL_RANGE = range(20000, 30036)
    KNOWN_RANGE = range(100, 2013323)
    UNIQUE_RANGES = (range(1000, 2101), range(10000, 20000))

    def __init__(self, rule_data: RuleData | None = None):
        self.rule_data = rule_data or RuleData.load()

    def validate_path(self, path: str | Path) -> ValidationReport:
        source = str(path)
        try:
            save_path = Path(path)
            if save_path.stat().st_size > self.MAX_SAVE_BYTES:
                raise SaveReadError("存档超过安全读取大小上限")
            with save_path.open("rb") as handle:
                raw = handle.read(self.MAX_SAVE_BYTES + 1)
            if len(raw) > self.MAX_SAVE_BYTES:
                raise SaveReadError("存档超过安全读取大小上限")
            payloads = self._read_bnd4_entries(raw)
            relics = []
            for slot, payload in payloads.items():
                relics.extend(self._read_relics(payload, f"USERDATA_{slot}"))
            return self._validate_relics(relics, source)
        except (OSError, SaveReadError, struct.error, ValueError) as exc:
            return ValidationReport(ValidationStatus.UNKNOWN, reasons=(str(exc),), source=source)

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

    def _read_bnd4_entry(self, raw: bytes, index: int) -> bytes:
        """Compatibility helper for callers that need one decrypted entry."""
        return self._read_bnd4_entries(raw)[index]

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
                color=str(meta.get("color", "Unknown")),
                name=str(meta.get("name", f"Relic {relic_id}")),
                favorite=bool(entry[12]), equipped=False, slot=slot, player_name=player_name))
        return relics

    def _validate_relics(self, relics: list[RelicRecord], source: str) -> ValidationReport:
        results = []
        seen_unique: dict[tuple[str, int], int] = {}
        for relic in relics:
            result = self._validate_relic(relic)
            results.append(result)
            if relic.relic_id in self._unique_ids():
                key = (relic.slot, relic.relic_id)
                seen_unique[key] = seen_unique.get(key, 0) + 1
        for result_index, result in enumerate(results):
            key = (result.relic.slot, result.relic.relic_id)
            if seen_unique.get(key, 0) > 1:
                result = RelicResult(result.relic, ValidationStatus.VIOLATES,
                                     result.reasons + ("唯一遗物重复出现",))
                results[result_index] = result
        statuses = {result.status for result in results}
        status = (ValidationStatus.VIOLATES if ValidationStatus.VIOLATES in statuses
                  else ValidationStatus.UNKNOWN if ValidationStatus.UNKNOWN in statuses
                  else ValidationStatus.CONFORMS)
        return ValidationReport(status, tuple(results), source=source)

    def _validate_relic(self, relic: RelicRecord) -> RelicResult:
        meta = self.rule_data.relics.get(relic.relic_id)
        if relic.relic_id in self.ILLEGAL_RANGE:
            return RelicResult(relic, ValidationStatus.VIOLATES, ("遗物 ID 位于已知非法范围",))
        if relic.relic_id not in self.KNOWN_RANGE or meta is None:
            return RelicResult(relic, ValidationStatus.UNKNOWN, ("遗物 ID 或版本数据未知",))
        reasons = []
        expected = meta["slots"]
        if not self._metadata_known(expected, relic.effects):
            return RelicResult(relic, ValidationStatus.UNKNOWN, ("词条或生成池数据未知",))
        if not self._effects_fit(expected, relic.effects):
            reasons.append("词条不在该遗物的可生成池中")
        conflict = self._has_conflict(relic.effects)
        if conflict is None:
            return RelicResult(relic, ValidationStatus.UNKNOWN, ("词条冲突数据未知",))
        if conflict:
            reasons.append("词条存在已知冲突")
        if not self._is_sorted(relic.effects):
            reasons.append("正面词条顺序违反已知规则")
        status = ValidationStatus.VIOLATES if reasons else ValidationStatus.CONFORMS
        return RelicResult(relic, status, tuple(reasons))

    def _effects_fit(self, slots: tuple[int, ...], effects: tuple[int, ...]) -> bool:
        from itertools import permutations
        for order in permutations(range(3)):
            valid = True
            for target, source in enumerate(order):
                effect = effects[source]
                pool = slots[target]
                if pool == -1:
                    valid &= effect in self.EMPTY_EFFECTS
                else:
                    valid &= effect not in self.EMPTY_EFFECTS and effect in self._rollable_effects(pool)
            for target, source in enumerate(order):
                curse = effects[source + 3]
                effect = effects[source]
                pool = slots[target + 3]
                if pool == -1:
                    valid &= curse in self.EMPTY_EFFECTS
                elif curse not in self.EMPTY_EFFECTS:
                    valid &= curse in self._rollable_effects(pool)
                elif self._effect_needs_curse(effect):
                    valid = False
            if valid:
                return True
        return False

    def _rollable_effects(self, pool: int) -> set[int]:
        if pool in {2000000, 2100000, 2200000}:
            effects: set[int] = set()
            for deep_pool in (2000000, 2100000, 2200000):
                effects.update(self.rule_data.pools.get(deep_pool, set()))
            return effects
        return self.rule_data.pools.get(pool, set())

    def _metadata_known(self, slots: tuple[int, ...], effects: tuple[int, ...]) -> bool:
        for effect in effects:
            if effect not in self.EMPTY_EFFECTS and effect not in self.rule_data.effects:
                return False
        for pool in slots:
            if (pool != -1 and pool not in self.rule_data.pool_ids
                    and pool not in self.rule_data.pools):
                return False
        return True

    def _effect_needs_curse(self, effect: int) -> bool:
        pools = self.rule_data.effect_pools.get(effect, set()) - {effect}
        if not pools:
            return False
        return 2000000 in pools and not pools.intersection({2100000, 2200000})

    def _has_conflict(self, effects: tuple[int, ...]) -> bool | None:
        conflicts = []
        for effect in effects:
            if effect in self.EMPTY_EFFECTS:
                continue
            meta = self.rule_data.effects.get(effect)
            if meta is None:
                return None
            conflict = meta["conflict"]
            if conflict != -1 and conflict in conflicts:
                return True
            conflicts.append(conflict)
        return False

    def _is_sorted(self, effects: tuple[int, ...]) -> bool:
        values = [(float("inf"), effect) if effect in self.EMPTY_EFFECTS else
                  (self.rule_data.effects[effect]["sort"], effect)
                  for effect in effects[:3] if effect in self.EMPTY_EFFECTS or effect in self.rule_data.effects]
        return len(values) == 3 and values == sorted(values)

    def _unique_ids(self) -> set[int]:
        return {value for span in self.UNIQUE_RANGES for value in span}


def _int(value: str | None, default: int) -> int:
    try:
        return int(value) if value not in (None, "") else default
    except ValueError:
        return default


def _color_name(value: str | None) -> str:
    return {"0": "Red", "1": "Blue", "2": "Yellow", "3": "Green", "4": "White"}.get(
        value or "", "Unknown")
