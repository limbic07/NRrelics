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

    def test_extra_curse_violates_item_id_slot_count(self):
        effects = {effect: {'conflict': -1, 'sort': effect}
                   for effect in (1, 2, 3, 4, 100)}
        rules = RuleData(
            relics={2003002: {'slots': (2100000, 2100000, 2100000, -1, -1, -1)}},
            effects=effects,
            pools={2100000: {1, 2, 3}, 3000000: {100}},
            pool_ids={2100000, 3000000},
        )
        validator = ReadOnlySaveValidator(rules)
        extra = RelicRecord(0, 2003002, (1, 2, 3, 0, 0, 100),
                            'Blue', 'special', False, False)
        result = validator._validate_relic(extra)
        self.assertIs(result.status, ValidationStatus.VIOLATES)
        self.assertIn('负面词条数量不匹配：应为 0 条，实际 1 条', result.reasons[0])

        invalid = RelicRecord(0, 2003002, (1, 2, 4, 0, 0, 100),
                              'Blue', 'special', False, False)
        self.assertIs(validator._validate_relic(invalid).status, ValidationStatus.VIOLATES)

    def test_deep_effect_in_combined_pool_but_not_assigned_pool_is_unknown(self):
        rules = RuleData(
            relics={2003002: {'slots': (2100000, 2100000, 2100000, -1, -1, -1)}},
            effects={effect: {'conflict': -1, 'sort': effect} for effect in (1, 2, 3, 4)},
            pools={2100000: {1, 2, 3}, 2200000: {4}},
            pool_ids={2100000, 2200000},
        )
        validator = ReadOnlySaveValidator(rules)
        broad_only = RelicRecord(0, 2003002, (1, 2, 4, 0, 0, 0),
                                 'Blue', 'deep', False, False)
        result = validator._validate_relic(broad_only)
        self.assertIs(result.status, ValidationStatus.UNKNOWN)
        self.assertIn('仅匹配合并池', result.reasons[0])

        exact = RelicRecord(0, 2003002, (1, 2, 3, 0, 0, 0),
                            'Blue', 'deep', False, False)
        self.assertIs(validator._validate_relic(exact).status, ValidationStatus.CONFORMS)

    def test_public_wrong_id_example_and_matching_template(self):
        # Upstream issue #55: same effects can fit a different item ID, while
        # 2003202 has no curse slots. The save itself is never rewritten.
        validator = ReadOnlySaveValidator(check_id_consistency=True)
        effects = (7044100, 6610400, 6610802, 0xFFFFFFFF, 6820200, 6850900)
        wrong = RelicRecord(0, 2003202, effects, 'Yellow', 'deep', False, False)
        valid = RelicRecord(0, 2001202, effects, 'Yellow', 'deep', False, False)
        result = validator._validate_relic(wrong)
        self.assertIs(result.status, ValidationStatus.VIOLATES)
        self.assertIn('应为 0 条，实际 2 条', result.reasons[0])
        self.assertIs(validator._validate_relic(valid).status, ValidationStatus.CONFORMS)

    def test_required_curse_cannot_be_bypassed_by_no_curse_template(self):
        validator = ReadOnlySaveValidator()
        relic = RelicRecord(0, 2003002,
                            (7044100, 6610400, 6610802, 0, 0, 0),
                            'Red', 'deep', False, False)
        result = validator._validate_relic(relic)
        self.assertIs(result.status, ValidationStatus.VIOLATES)
        self.assertTrue(any('必须附带负面词条' in reason for reason in result.reasons))

    def test_curses_must_remain_paired_even_when_total_count_is_correct(self):
        validator = ReadOnlySaveValidator()
        relic = RelicRecord(0, 2001202,
                            (7044100, 6610400, 6610802, 6820200, 6850900, 0),
                            'Yellow', 'deep', False, False)
        result = validator._validate_relic(relic)
        self.assertIs(result.status, ValidationStatus.VIOLATES)
        self.assertTrue(any('第 3 条正面词条' in reason for reason in result.reasons))

    def test_missing_configured_curse_is_not_optional(self):
        validator = ReadOnlySaveValidator(check_id_consistency=True)
        relic = RelicRecord(0, 2001102,
                            (6500000, 6631900, 6610400, 0, 0, 6820000),
                            'Blue', 'deep', False, False)
        result = validator._validate_relic(relic)
        self.assertIs(result.status, ValidationStatus.VIOLATES)
        self.assertIn('应为 2 条，实际 1 条', result.reasons[0])

    def test_default_accepts_legal_combination_and_strict_checks_original_id(self):
        effects = (6633100, 7044500, 6610802, 0, 0, 6820000)
        relic = RelicRecord(0, 2003002, effects, 'Red', 'deep', False, False)
        self.assertIs(ReadOnlySaveValidator()._validate_relic(relic).status,
                      ValidationStatus.CONFORMS)
        strict = ReadOnlySaveValidator(check_id_consistency=True)._validate_relic(relic)
        self.assertIs(strict.status, ValidationStatus.VIOLATES)
        self.assertIn('应为 0 条，实际 1 条', strict.reasons[0])
        self.assertEqual(relic.relic_id, 2003002)

    def test_combination_mode_preserves_size_type_and_fixed_relic(self):
        validator = ReadOnlySaveValidator()
        effects = (6633100, 7044500, 6610802, 0, 0, 6820000)
        for relic_id in (2003000, 1000002, 1000):
            with self.subTest(relic_id=relic_id):
                relic = RelicRecord(0, relic_id, effects, 'Red', 'test', False, False)
                self.assertIs(validator._validate_relic(relic).status, ValidationStatus.VIOLATES)

    def test_combination_mode_does_not_merge_incompatible_templates(self):
        rules = RuleData(
            relics={2003002: {'color': 'Red', 'is_deep': True,
                             'slots': (2100000, 2100000, 2100000, -1, -1, -1)},
                    2013002: {'color': 'Red', 'is_deep': True,
                             'slots': (2200000, 2200000, 2200000, -1, -1, -1)},
                    2013202: {'color': 'Yellow', 'is_deep': True,
                             'slots': (2100000, 2100000, 2200000, -1, -1, -1)}},
            effects={i: {'conflict': -1, 'sort': i} for i in (1, 2, 3)},
            pools={2100000: {1, 2}, 2200000: {3}}, pool_ids={2100000, 2200000},
        )
        relic = RelicRecord(0, 2003002, (1, 2, 3, 0, 0, 0), 'Red', 'test', False, False)
        self.assertIs(ReadOnlySaveValidator(rules)._validate_relic(relic).status,
                      ValidationStatus.UNKNOWN)

    def test_exact_pool_check_uses_same_effect_curse_permutation(self):
        rules = RuleData(
            relics={2000001: {'slots': (2000000, 2100000, -1, 3000000, -1, -1)}},
            effects={effect: {'conflict': -1, 'sort': effect} for effect in (1, 2, 100)},
            pools={2000000: {2}, 2100000: {1}, 2200000: {2}, 3000000: {100}},
            pool_ids={2000000, 2100000, 2200000, 3000000},
            effect_pools={1: {2100000}, 2: {2000000, 2200000}},
        )
        relic = RelicRecord(0, 2000001, (1, 2, 0, 100, 0, 0),
                            'Red', 'deep', False, False)
        result = ReadOnlySaveValidator(rules)._validate_relic(relic)
        self.assertIs(result.status, ValidationStatus.UNKNOWN)
        self.assertIn('仅匹配合并池', result.reasons[0])

    def test_unknown_effect_does_not_hide_known_slot_count_mismatch(self):
        rules = RuleData(relics={100: {'slots': (100, -1, -1, -1, -1, -1)}})
        relic = RelicRecord(0, 100, (999, 0, 0, 888, 0, 0),
                            'Red', 'unknown effects', False, False)
        result = ReadOnlySaveValidator(rules)._validate_relic(relic)
        self.assertIs(result.status, ValidationStatus.VIOLATES)
        self.assertIn('应为 0 条，实际 1 条', result.reasons[0])
        self.assertIn('词条或生成池数据未知', result.reasons)

    def test_one_and_two_effect_relics_use_their_own_template_counts(self):
        rules = RuleData(
            relics={100: {'slots': (100, -1, -1, -1, -1, -1)},
                    101: {'slots': (100, 100, -1, -1, -1, -1)}},
            effects={effect: {'conflict': -1, 'sort': effect} for effect in (1, 2)},
            pools={100: {1, 2}}, pool_ids={100},
        )
        validator = ReadOnlySaveValidator(rules)
        for relic_id, effects in ((100, (1, 0, 0, 0, 0, 0)),
                                  (101, (1, 2, 0, 0, 0, 0))):
            with self.subTest(relic_id=relic_id):
                relic = RelicRecord(0, relic_id, effects, 'Red', 'normal', False, False)
                self.assertIs(validator._validate_relic(relic).status, ValidationStatus.CONFORMS)


if __name__ == '__main__':
    unittest.main()
