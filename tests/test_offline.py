import copy
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('seeker', ROOT / 'pxoj_seeker.py')
s = importlib.util.module_from_spec(spec)
spec.loader.exec_module(s)


def fixture():
    cls = {'kind': 'type', 'type_id': 0, 'qualified_name': 'Player', 'name': 'Player',
           'namespace': 'Game', 'image': 'Assembly-CSharp.dll'}
    method = {'kind': 'method', 'declaring_type_id': 0, 'declaring_type': 'Player',
              'namespace': 'Game', 'image': 'Assembly-CSharp.dll', 'name': 'GetSpeed',
              'parameter_count': 0, 'parameter_types': [], 'return_type': 'System.Single',
              'offset_status': 'layout_and_mapping_snapshot_validated',
              'offset_confidence': 'conditional_on_runtime_layout', 'native_address': '0x7f002000',
              'image_base': '0x7f000000', 'elf_load_bias': '0x7f000000', 'native_offset': '0x2000',
              'elf_virtual_address': '0x2000', 'elf_file_offset': '0x1000',
              'raw_method_pointer': '0x7f002000', 'thumb': False,
              'native_module': '/data/app/example/lib/arm64/libil2cpp.so'}
    damage = copy.deepcopy(method)
    damage.update(name='ApplyDamage', parameter_count=1, parameter_types=['System.Int32'], return_type='System.Int32',
                  native_offset='0x3000', elf_virtual_address='0x3000', elf_file_offset='0x2000',
                  native_address='0x7f003000', raw_method_pointer='0x7f003000')
    field = {'kind': 'field', 'declaring_type_id': 0, 'declaring_type': 'Player',
             'namespace': 'Game', 'image': 'Assembly-CSharp.dll', 'name': 'moveSpeed',
             'type': 'System.Single', 'runtime_reported_offset': 32, 'flags': 6,
             'is_static': False, 'is_literal': False}
    unavailable = copy.deepcopy(damage)
    unavailable.update(name='CalculateDamage', native_offset=None, native_address=None,
                       offset_status='unsupported_or_mismatched_layout')
    duplicate = copy.deepcopy(damage)
    duplicate.update(name='ApplyDamageAlias', native_offset='0x00003000')
    return {'tool': 'pxojdumper', 'schema': 2, 'partial': False,
            'records': [cls, method, damage, field, unavailable, duplicate], 'example_only': True}


class SeekerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.directory = Path(self.tmp.name)
        self.path = self.directory / 'dump with spaces.json'
        self.chosen = self.directory / 'selected.json'
        self.data = fixture()
        self.save()

    def tearDown(self):
        self.tmp.cleanup()

    def save(self):
        self.path.write_text(json.dumps(self.data), encoding='utf-8')

    def dump(self):
        return s.Dump(self.path)

    def cli(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            result = s.main([str(x) for x in args])
        return result, out.getvalue(), err.getvalue()

    def test_actual_kinds_and_class_context(self):
        dump = self.dump()
        self.assertEqual(dump.counts, {'type': 1, 'method': 4, 'field': 1})
        self.assertEqual(s.details(dump, 0)['same_class_ids'], [1, 2, 3, 4, 5])

    def test_casefold_multi_keyword_ranking_any(self):
        hits = s.search(self.dump(), ['SPEED', 'damage'])
        self.assertEqual({r['id'] for r in hits}, {1, 2, 3, 4, 5})
        self.assertTrue(all(r['score'] > 0 and r['matches'] for r in hits))
        self.assertEqual([r['id'] for r in hits], [1, 2, 3, 4, 5])

    def test_all_keywords_match_different_fields(self):
        hits = s.search(self.dump(), ['Player', 'Speed'], match_all=True)
        self.assertEqual([r['id'] for r in hits], [1, 3])

    def test_empty_search_returns_all(self):
        self.assertEqual(len(s.search(self.dump(), [])), 6)

    def test_exclusions_and_filters(self):
        hits = s.search(self.dump(), ['damage'], excluded=['alias'], kind='method',
                        image='csharp', class_name='player', has_rva=True)
        self.assertEqual([r['id'] for r in hits], [2])
        self.assertEqual(s.search(self.dump(), [], image='other'), [])
        self.assertEqual(s.search(self.dump(), [], class_name='Enemy'), [])

    def test_keyword_is_literal_not_regex(self):
        self.assertEqual(s.search(self.dump(), ['.*']), [])

    def test_name_rank_exceeds_class_rank(self):
        self.data['records'][2]['name'] = 'Player'
        self.save()
        self.assertEqual(s.search(self.dump(), ['Player'])[0]['id'], 0)  # exact class name also earns 130
        self.assertEqual(s.search(self.dump(), ['Player'])[1]['id'], 2)

    def test_native_rva_not_file_or_field_offset(self):
        dump = self.dump()
        self.assertEqual([r['id'] for r in s.search(dump, [], offset=0x2000, offset_kind='rva')], [1])
        self.assertEqual([r['id'] for r in s.search(dump, [], offset=0x2000, offset_kind='file')], [2, 4, 5])
        self.assertEqual([r['id'] for r in s.search(dump, [], offset=32, offset_kind='field')], [3])
        self.assertEqual(s.search(dump, [], offset=32, offset_kind='rva'), [])

    def test_offset_kind_required_and_no_implicit_rva(self):
        with self.assertRaises(ValueError): s.search(self.dump(), [], offset=32)
        with self.assertRaises(ValueError): s.search(self.dump(), [], offset_kind='rva')
        with self.assertRaises(ValueError): s.search(self.dump(), [], kind='field', has_rva=True)

    def test_aliases_normalize_hex(self):
        dump = self.dump()
        self.assertEqual(dump.shared(2), [2, 5])

    def test_static_field_not_treated_as_instance_offset(self):
        self.data['records'][3].update(flags=22, is_static=True)
        self.save()
        code, out, _ = self.cli('show', self.path, '3')
        self.assertEqual(code, 0)
        self.assertIn('Static=True', out)
        self.assertIn('Field offsets are distinct', out)

    def test_invalid_type_parent_and_field_rejected(self):
        for index, key, value in [(0, 'type_id', True), (2, 'declaring_type_id', 3),
                                  (3, 'runtime_reported_offset', True), (3, 'is_static', True),
                                  (0, 'qualified_name', None), (3, 'type', []), (3, 'flags', '6')]:
            self.data = fixture()
            self.data['records'][index][key] = value
            self.save()
            with self.assertRaises(ValueError, msg=f'{index} {key}'): self.dump()

    def test_different_images_do_not_merge_owners(self):
        cls = copy.deepcopy(self.data['records'][0])
        cls.update(type_id=6, image='Other.dll')
        field = copy.deepcopy(self.data['records'][3])
        field.update(declaring_type_id=6, image='Other.dll')
        self.data['records'].extend([cls, field]); self.save()
        self.assertEqual(s.details(self.dump(), 6)['same_class_ids'], [7])

    def test_same_display_name_does_not_merge_type_ids(self):
        self.data['records'][0]['qualified_name'] = '<name-limit>'
        for row in self.data['records'][1:]:
            row['declaring_type'] = '<name-limit>'
        cls = copy.deepcopy(self.data['records'][0]); cls['type_id'] = 6
        field = copy.deepcopy(self.data['records'][3]); field['declaring_type_id'] = 6
        self.data['records'].extend([cls, field]); self.save()
        self.assertEqual(s.details(self.dump(), 6)['same_class_ids'], [7])
        self.assertEqual(s.details(self.dump(), 1)['same_class_ids'], [1, 2, 3, 4, 5])

    def test_schema_partial_types_rejected(self):
        for key, value in [('schema', 2.0), ('partial', 'false')]:
            self.data = fixture(); self.data[key] = value; self.save()
            with self.assertRaises(ValueError): self.dump()

    def test_unknown_kind_rejected(self):
        self.data['records'][0]['kind'] = 'assembly'; self.save()
        with self.assertRaises(ValueError): self.dump()

    def test_invalid_record_id_rejected(self):
        for index in (-1, 6, True):
            with self.assertRaises(ValueError): self.dump().row(index)

    def test_json_stdout_parseable_and_pagination(self):
        self.data['partial'] = True; self.save()
        code, out, err = self.cli('search', self.path, 'speed', '--limit', 1, '--skip', 1, '--json')
        self.assertEqual(code, 0)
        parsed = json.loads(out)
        self.assertEqual(parsed['total'], 2)
        self.assertEqual(parsed['results'][0]['id'], 3)
        self.assertIn('partial', err)

    def test_info_compare_show(self):
        code, out, _ = self.cli('info', self.path, '--json')
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)['shared_rva_groups'], 1)
        code, out, _ = self.cli('compare', self.path, 1, 3, '--json')
        self.assertEqual(code, 0)
        self.assertEqual(len(json.loads(out)['candidates']), 2)
        self.assertEqual(self.cli('compare', self.path, 1, 1)[0], 2)
        self.assertEqual(self.cli('compare', self.path, 1)[0], 2)

    def test_control_and_bidi_escape_but_japanese_kept(self):
        self.assertEqual(s.clean('日本\n\x1b[2J\u202e'), '日本\\u000a\\u001b[2J\\u202e')
        self.data['records'][2]['name'] = 'Damage\x1b[2J\u202e'; self.save()
        code, out, _ = self.cli('search', self.path, 'damage')
        self.assertEqual(code, 0)
        self.assertNotIn('\x1b', out)
        self.assertNotIn('\u202e', out)

    def test_keyword_and_pagination_limits(self):
        with self.assertRaises(ValueError): s.search(self.dump(), ['x' * 257])
        with self.assertRaises(ValueError): s.search(self.dump(), [str(i) for i in range(33)])
        self.assertEqual(self.cli('search', self.path, '--limit', 0)[0], 2)
        self.assertEqual(self.cli('search', self.path, '--skip', -1)[0], 2)

    def test_number_parser(self):
        self.assertEqual(s.number('0X20'), 32)
        self.assertEqual(s.number('032'), 32)
        for text in ('-1', '1.0', '0x', str(2**64)):
            with self.assertRaises(Exception): s.number(text)
