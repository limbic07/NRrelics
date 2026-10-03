"""Focused checks for the read-only save parser and its bundled rule data."""

import ast
import struct
import tempfile
import unittest
from pathlib import Path

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from core.relic_validation import (
    ReadOnlySaveValidator, RelicRecord, RuleData, ValidationStatus,
)


ROOT = Path(__file__).resolve().parents[1]


def make_test_save(relic_id=25000):
    """Build a minimal BND4 with ten encrypted profiles and one relic."""
    validator = ReadOnlySaveValidator(RuleData())
    payload_size = (validator.STATE_OFFSET + 80 + (validator.STATE_COUNT - 1) * 8
                    + 0x94 + 0x5B8 + 4 + validator.ENTRY_COUNT * 14)
    payloads = []
    for slot in validator.INVENTORY_SLOTS:
        payload = bytearray(payload_size)
        if slot == 0:
            handle = validator.RELIC_TYPE | 1
            struct.pack_into('<II', payload, validator.STATE_OFFSET, handle, relic_id)
            name_offset = (validator.STATE_OFFSET + 80
                           + (validator.STATE_COUNT - 1) * 8 + 0x94)
            payload[name_offset:name_offset + 8] = '角色甲'.encode('utf-16-le')
            item_offset = name_offset + 0x5B8 + 4
            struct.pack_into('<III', payload, item_offset, handle, 1, 0)
            payload[item_offset + 12] = 1
        payload += bytes(-len(payload) % 16)
        iv = bytes([slot]) * 16
        encryptor = Cipher(algorithms.AES(validator.SAVE_KEY), modes.CBC(iv)).encryptor()
        payloads.append(iv + encryptor.update(bytes(payload)) + encryptor.finalize())

    header = bytearray(validator.BND4_HEADER + len(payloads) * validator.BND4_ENTRY)
    header[:4] = b'BND4'
    struct.pack_into('<I', header, 12, len(payloads))
    offset = len(header)
    for slot, payload in enumerate(payloads):
        entry_offset = validator.BND4_HEADER + slot * validator.BND4_ENTRY
        header[entry_offset:entry_offset + 8] = b'\x40\x00\x00\x00\xff\xff\xff\xff'
        struct.pack_into('<5i', header, entry_offset + 8, len(payload), 0, offset, 0, 0)
        offset += len(payload)
    return bytes(header) + b''.join(payloads)


class RelicValidationTests(unittest.TestCase):
    def test_bundled_rule_tables_and_package_entries_exist(self):
        rules = RuleData.load()
        self.assertGreater(len(rules.relics), 1000)
        self.assertGreater(len(rules.effects), 1000)
        spec = ast.parse((ROOT / 'NRrelic_Bot.spec').read_text(encoding='utf-8'))
        static_data = next(ast.literal_eval(node.value) for node in spec.body
                           if isinstance(node, ast.Assign)
                           and any(isinstance(target, ast.Name) and target.id == '_static_data'
                                   for target in node.targets))
        packaged = {source for source, _ in static_data}
        for path in (ROOT / 'data/relic_validation').iterdir():
            if path.is_file():
                self.assertIn(path.relative_to(ROOT).as_posix(), packaged)

    def test_synthetic_save_is_parsed_without_writing_file(self):
        original = make_test_save()
        with tempfile.TemporaryDirectory() as directory:
            for suffix in ('.sl2', '.co2'):
                path = Path(directory) / f'synthetic{suffix}'
                path.write_bytes(original)
                report = ReadOnlySaveValidator(RuleData()).validate_path(path)
                self.assertEqual(path.read_bytes(), original)
                self.assertIs(report.status, ValidationStatus.VIOLATES)
                self.assertEqual(len(report.results), 1)
                relic = report.results[0].relic
                self.assertEqual(relic.slot, 'USERDATA_0')
                self.assertEqual(relic.player_name, '角色甲')
                self.assertTrue(relic.favorite)
                self.assertIn('非法范围', report.results[0].reasons[0])

    def test_corrupt_save_and_unknown_relic_remain_unknown(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'broken.sl2'
            path.write_bytes(b'not a BND4 save')
            report = ReadOnlySaveValidator(RuleData()).validate_path(path)
            self.assertIs(report.status, ValidationStatus.UNKNOWN)
            self.assertEqual(path.read_bytes(), b'not a BND4 save')

        relic = RelicRecord(0, 99999999, (0,) * 6, 'Unknown', 'unknown', False, False)
        result = ReadOnlySaveValidator(RuleData())._validate_relic(relic)
        self.assertIs(result.status, ValidationStatus.UNKNOWN)

    def test_unique_rule_is_scoped_to_each_player(self):
        rules = RuleData(relics={1000: {'slots': (-1,) * 6}}, effects={})
        validator = ReadOnlySaveValidator(rules)
        first = RelicRecord(0, 1000, (0,) * 6, 'Blue', 'test', False, False,
                            'USERDATA_0', '角色甲')
        second = RelicRecord(1, 1000, (0,) * 6, 'Blue', 'test', False, False,
                             'USERDATA_1', '角色乙')
        separate = validator._validate_relics([first, second], 'synthetic')
        self.assertIs(separate.status, ValidationStatus.CONFORMS)
        duplicate = validator._validate_relics([first, first], 'synthetic')
        self.assertIs(duplicate.status, ValidationStatus.VIOLATES)
        self.assertTrue(all(any('唯一遗物重复' in reason for reason in result.reasons)
                            for result in duplicate.results))

    def test_unmapped_special_curse_is_unknown_but_bad_positive_is_violation(self):
        effects = {effect: {'conflict': -1, 'sort': effect}
                   for effect in (1, 2, 3, 4, 100)}
        rules = RuleData(
            relics={2003002: {'slots': (2100000, 2100000, 2100000, -1, -1, -1)}},
            effects=effects,
            pools={2100000: {1, 2, 3}, 3000000: {100}},
            pool_ids={2100000, 3000000},
        )
        validator = ReadOnlySaveValidator(rules)
        unclear = RelicRecord(0, 2003002, (1, 2, 3, 0, 0, 100),
                              'Blue', 'special', False, False)
        result = validator._validate_relic(unclear)
        self.assertIs(result.status, ValidationStatus.UNKNOWN)
        self.assertIn('额外负面词条', result.reasons[0])

        invalid = RelicRecord(0, 2003002, (1, 2, 4, 0, 0, 100),
                              'Blue', 'special', False, False)
        self.assertIs(validator._validate_relic(invalid).status, ValidationStatus.VIOLATES)


if __name__ == '__main__':
    unittest.main()
