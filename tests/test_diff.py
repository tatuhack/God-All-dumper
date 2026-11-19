import contextlib
import copy
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('pxoj_diff', ROOT / 'pxoj_diff.py')
d = importlib.util.module_from_spec(spec)
spec.loader.exec_module(d)


def fixture():
    klass = {'kind': 'type', 'type_id': 0, 'qualified_name': 'Player', 'name': 'Player',
             'namespace': 'Game', 'image': 'Assembly-CSharp.dll'}
    method = {'kind': 'method', 'declaring_type_id': 0, 'declaring_type': 'Player',
              'namespace': 'Game', 'image': 'Assembly-CSharp.dll', 'name': 'GetSpeed',
              'parameter_count': 0, 'parameter_types': [], 'return_type': 'System.Single',
              'offset_status': 'layout_and_mapping_snapshot_validated',
              'offset_confidence': 'conditional_on_runtime_layout', 'native_address': '0x7f002000',
              'image_base': '0x7f000000', 'elf_load_bias': '0x7f000000', 'native_offset': '0x2000',
              'elf_virtual_address': '0x2000', 'elf_file_offset': '0x1000',
              'raw_method_pointer': '0x7f002000', 'thumb': False,
              'native_module': '/data/app/old/lib/arm64/libil2cpp.so'}
    return {'tool': 'pxojdumper', 'schema': 2, 'partial': False, 'records': [klass, method]}


def move(row, rva, base=0x7f000000, minimum=0):
    row.update(native_address=hex(base + rva), raw_method_pointer=hex(base + rva + int(row['thumb'])),
               image_base=hex(base), elf_load_bias=hex(base - minimum), native_offset=hex(rva),
               elf_virtual_address=hex(rva + minimum))


class DiffTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.a, self.b = fixture(), fixture()
        self.old, self.new = self.root / 'old dump.json', self.root / 'new dump.json'

    def save(self):
        for path, data in ((self.old, self.a), (self.new, self.b)):
            path.write_text(json.dumps(data), encoding='utf-8')
        return d.Dump(self.old), d.Dump(self.new)

    def report(self, policy='basename-unique'):
        return d.compare(*self.save(), module_policy=policy)

    def cli(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = d.main([str(a) for a in args])
        return code, out.getvalue(), err.getvalue()

    def native(self, policy='basename-unique'):
        return self.report(policy)['matches'][0]['native']

    def test_identical_dump(self):
        r = self.report()
        self.assertEqual(r['summary']['matches'], 1)
        self.assertEqual(r['matches'][0]['native']['state'], 'rva_unchanged')
        self.assertEqual(r['old_dump']['sha256'], r['new_dump']['sha256'])

    def test_aslr_not_rva_change(self):
        move(self.b['records'][1], 0x2000, base=0x90000000)
        n = self.native()
        self.assertEqual(n['state'], 'rva_unchanged')
        self.assertTrue(n['dump_time_address_changed'])
        self.assertEqual(n['rva_delta'], '+0x0')

    def test_changed_rva_positive_and_negative(self):
        for offset, delta in ((0x2040, '+0x40'), (0x1000, '-0x1000')):
            move(self.b['records'][1], offset)
            n = self.native()
            self.assertEqual((n['state'], n['rva_delta']), ('rva_changed', delta))

    def test_hex_spelling_is_not_offset_change(self):
        self.b['records'][1]['native_offset'] = '0x00002000'
        self.assertEqual(self.native()['state'], 'rva_unchanged')

    def test_nonzero_minimum_vaddr(self):
        move(self.b['records'][1], 0x2000, minimum=0x1000)
        n = self.native()
        self.assertEqual(n['state'], 'rva_unchanged')
        self.assertTrue(n['elf_virtual_address_changed'])
        self.assertTrue(n['elf_min_vaddr_changed'])

    def test_file_offset_separate_from_rva(self):
        self.b['records'][1]['elf_file_offset'] = '0x1900'
        n = self.native()
        self.assertEqual(n['state'], 'rva_unchanged')
        self.assertTrue(n['elf_file_offset_changed'])
        self.b['records'][1]['elf_file_offset'] = None
        self.assertTrue(self.native()['elf_file_offset_changed'])

    def test_module_basename_heuristic_and_exact_policy(self):
        self.b['records'][1]['native_module'] = '/data/app/new/lib/arm64/libil2cpp.so'
        self.assertEqual(self.native()['module_basis'], 'unique_basename_heuristic')
        self.assertEqual(self.native('exact')['state'], 'module_incomparable')

    def test_different_module_basename(self):
        self.b['records'][1]['native_module'] = '/other/libgame.so'
        self.assertEqual(self.native()['state'], 'module_incomparable')

    def test_duplicate_module_basename_no_guess(self):
        extra = copy.deepcopy(self.a['records'][1])
        extra.update(name='Other', native_module='/other/libil2cpp.so')
        self.a['records'].append(extra)
        self.b['records'][1]['native_module'] = '/data/app/new/libil2cpp.so'
        self.assertEqual(self.native()['state'], 'module_incomparable')

    def test_shared_rva_is_not_duplicate_signature(self):
        for data in (self.a, self.b):
            alias = copy.deepcopy(data['records'][1])
            alias['name'] = 'Alias'
            data['records'].append(alias)
        r = self.report()
        self.assertEqual(len(r['matches']), 2)
        self.assertEqual(r['matches'][0]['native']['new_shared_records'], 2)

    def test_record_reordering_matches_new_local_id(self):
        self.b['records'].append(copy.deepcopy(self.b['records'][1]))
        self.b['records'][1]['name'] = 'Added'
        pair = self.report()['matches'][0]
        self.assertEqual((pair['old_id'], pair['new_id']), (1, 2))

    def test_signature_change_becomes_observed_only(self):
        for field, value in [('name', 'getspeed'), ('return_type', 'System.Int32'),
                             ('image', 'Other.dll')]:
            self.b = fixture()
            self.b['records'][1][field] = value
            if field == 'image':
                self.b['records'][0]['image'] = value
            r = self.report()
            self.assertEqual((len(r['old_only']), len(r['new_only']), len(r['matches'])), (1, 1, 0))

    def test_parameter_type_and_count_distinguish_overloads(self):
        self.b['records'][1].update(parameter_count=1, parameter_types=['System.Int32'])
        self.assertEqual(len(self.report()['matches']), 0)
        self.a['records'][1].update(parameter_count=1, parameter_types=['System.Single'])
        self.assertEqual(len(self.report()['matches']), 0)

    def test_duplicate_signature_ambiguous_not_arbitrarily_paired(self):
        self.a['records'].append(copy.deepcopy(self.a['records'][1]))
        r = self.report()
        self.assertEqual(len(r['matches']), 0)
        self.assertEqual(r['ambiguous'][0]['old_ids'], [1, 2])
        self.assertEqual(r['ambiguous'][0]['new_ids'], [1])

    def test_duplicate_one_sided_group_still_ambiguous(self):
        self.a['records'].append(copy.deepcopy(self.a['records'][1]))
        self.b['records'] = self.b['records'][:1]
        r = self.report()
        self.assertEqual(len(r['ambiguous']), 1)
        self.assertEqual(len(r['old_only']), 0)

    def test_duplicate_class_identity_unresolved(self):
        extra = copy.deepcopy(self.a['records'][0])
        extra['type_id'] = 2
        self.a['records'].append(extra)
        r = self.report()
        self.assertEqual(len(r['matches']), 0)
        self.assertIn('class identity', r['unresolved_old'][0]['reason'])

    def test_partial_dump_warning(self):
        self.b['partial'] = True
        r = self.report()
        self.assertTrue(any('partial' in s for s in r['warnings']))
        self.assertTrue(r['new_dump']['partial'])

    def test_incomplete_signatures_unresolved(self):
        for update in [dict(parameter_count=2, parameter_types=['System.Int32']),
                       dict(name='Outer+<unavailable>'), dict(name='A\ufffd'),
                       dict(name='x' * 4096), dict(name='あ' * 1366),
                       dict(name='\ud800'), dict(name=''), dict(return_type='')]:
            self.a = fixture()
            self.a['records'][1].update(update)
            self.assertEqual(len(self.report()['unresolved_old']), 1)

    def test_empty_namespace_and_normal_unicode_supported(self):
        for data in (self.a, self.b):
            for row in data['records']:
                row['namespace'] = ''
            data['records'][1]['name'] = '移動速度'
        self.assertEqual(len(self.report()['matches']), 1)

    def test_native_unavailable_transitions(self):
        self.b['records'][1].update(offset_status='no_method_pointer', native_offset=None, native_address=None)
        self.assertEqual(self.native()['state'], 'became_unavailable')
        self.a, self.b = self.b, self.a
        self.assertEqual(self.native()['state'], 'became_available')
        self.b = copy.deepcopy(self.a)
        self.assertEqual(self.native()['state'], 'unavailable_both')

    def test_inconsistent_native_evidence_is_never_used(self):
        for key, value in [('native_offset', '0x3000'), ('native_offset', -1), ('native_offset', '0x10000000000000000'),
                           ('elf_load_bias', '0xffffffffffffffff'), ('raw_method_pointer', '0x0'),
                           ('thumb', 1), ('native_module', '<unknown>'), ('elf_file_offset', '0xzz'),
                           ('native_module', '/lib/a\n.so'), ('native_module', '/lib/a\ufffd.so'),
                           ('native_module', '/' + 'あ' * 171)]:
            self.b = fixture()
            self.b['records'][1][key] = value
            self.assertEqual(self.native()['state'], 'became_unavailable', (key, value))

    def test_thumb_mode_change_and_invalid_normalization(self):
        self.b['records'][1]['thumb'] = True
        move(self.b['records'][1], 0x2000)
        self.assertEqual(self.native()['state'], 'thumb_mode_changed')
        move(self.b['records'][1], 0x2001)
        self.assertEqual(self.native()['state'], 'became_unavailable')

    def test_u64_rva_no_float_precision_loss(self):
        for data in (self.a, self.b):
            move(data['records'][1], 0x8000000000000000, base=0x1000)
        move(self.b['records'][1], 0x8000000000000001, base=0x1000)
        self.assertEqual(self.native()['rva_delta'], '+0x1')

    def test_invalid_schema_counts_and_parent_references(self):
        changes = [lambda a: a.update(schema=True), lambda a: a.update(schema=1),
                   lambda a: a.update(partial=1), lambda a: a.update(record_count=3),
                   lambda a: a['records'][0].update(type_id=True),
                   lambda a: a['records'][1].update(declaring_type_id=True),
                   lambda a: a['records'][1].update(declaring_type_id=100),
                   lambda a: a['records'][1].update(declaring_type='Wrong'),
                   lambda a: a['records'][1].update(parameter_count=True),
                   lambda a: a['records'][1].update(parameter_types=[42]),
                   lambda a: a['records'].append(None)]
        for change in changes:
            self.a = fixture()
            change(self.a)
            with self.assertRaises(ValueError):
                self.save()

    def test_duplicate_json_keys_and_nan_rejected(self):
        for text in ['{"tool":"other","tool":"pxojdumper"}', '{"x":NaN}']:
            self.old.write_text(text)
            with self.assertRaises(ValueError):
                d.Dump(self.old)

    def test_file_and_record_limits(self):
        self.save()
        with mock.patch.object(d, 'LIMIT', 2):
            with self.assertRaises(ValueError): d.Dump(self.old)
        with mock.patch.object(d, 'MAX_RECORDS', 1):
            with self.assertRaises(ValueError): d.Dump(self.old)

    def test_legacy_optional_parent_reference(self):
        for data in (self.a, self.b):
            del data['records'][1]['declaring_type_id']
        self.assertEqual(len(self.report()['matches']), 1)

    def test_handoff_new_id_digest_and_no_hooks(self):
        self.b['records'].append(copy.deepcopy(self.b['records'][1]))
        self.b['records'][1]['name'] = 'Added'
        old, new = self.save()
        chosen = d.handoff(old, new, 1)
        self.assertEqual(chosen['method_id'], 2)
        self.assertEqual(chosen['dump_sha256'], new.digest)
        self.assertNotEqual(chosen['dump_sha256'], old.digest)
        self.assertEqual(chosen['tool'], 'PXOJ Seeker')
        self.assertNotIn('edits', chosen)
        self.assertNotIn('rva', chosen)

    def test_handoff_existing_selection(self):
        old, new = self.save()
        chosen = d.handoff(old, new, 1)
        path = self.root / 'chosen.json'
        path.write_text(json.dumps(chosen))
        self.assertEqual(d.handoff(old, new, None, selection=path)['method_id'], 1)
        chosen['dump_sha256'] = '0' * 64
        path.write_text(json.dumps(chosen))
        with self.assertRaisesRegex(ValueError, 'SHA-256'):
            d.handoff(old, new, None, selection=path)

    def test_handoff_unknown_ambiguous_unresolved_refused(self):
        old, new = self.save()
        for identifier in (0, -1, 99, True):
            with self.assertRaises(ValueError): d.handoff(old, new, identifier)
        self.b['records'].append(copy.deepcopy(self.b['records'][1]))
        with self.assertRaisesRegex(ValueError, 'No unique'):
            d.handoff(*self.save(), 1)
        self.b = fixture()
        self.b['records'][1]['parameter_count'] = 2
        with self.assertRaisesRegex(ValueError, 'No unique'):
            d.handoff(*self.save(), 1)

    def test_selection_schema_strict(self):
        old, new = self.save()
        chosen = d.handoff(old, new, 1)
        path = self.root / 'chosen.json'
        for change in [dict(schema=True), dict(method_id=True), dict(method_id=-1), dict(dump_sha256='x')]:
            changed = dict(chosen, **change)
            path.write_text(json.dumps(changed))
            with self.assertRaises(ValueError): d.read_selection(path)

    def test_handoff_digest_from_same_loaded_bytes(self):
        old, new = self.save()
        before = new.digest
        self.new.write_text('{}')
        self.assertEqual(d.handoff(old, new, 1)['dump_sha256'], before)

    def test_cli_valid_json_and_no_overwrite(self):
        self.save()
        code, out, err = self.cli('compare', self.old, self.new, '--format', 'json')
        self.assertEqual(code, 0, err)
        self.assertEqual(json.loads(out)['summary']['matches'], 1)
        output = self.root / 'report.json'
        self.assertEqual(self.cli('compare', self.old, self.new, '--format', 'json', '-o', output)[0], 0)
        before = output.read_bytes()
        self.assertEqual(self.cli('compare', self.old, self.new, '-o', output)[0], 2)
        self.assertEqual(before, output.read_bytes())
        self.assertEqual(self.cli('compare', self.old, self.new, '-o', self.old)[0], 2)
        self.assertEqual(len(d.Dump(self.old).rows), 2)

    def test_cli_handoff_and_partial_warning(self):
        self.a['partial'] = True
        self.save()
        output = self.root / 'new selection.json'
        code, out, err = self.cli('handoff', self.old, self.new, '--old-id', 1, '-o', output)
        self.assertEqual(code, 0)
        self.assertIn('partial', err)
        self.assertEqual(d.read_selection(output)['method_id'], 1)
        self.assertEqual(self.cli('handoff', self.old, self.new, '--old-id', 1, '-o', output)[0], 2)

    def test_cli_bad_inputs_clean_error(self):
        self.save()
        self.assertEqual(self.cli('compare', self.old, self.new, '--limit', 0)[0], 2)
        self.old.write_text('{broken')
        code, out, err = self.cli('compare', self.old, self.new)
        self.assertEqual(code, 2)
        self.assertIn('Error:', err)
        self.assertNotIn('Traceback', err)

    def test_terminal_control_escaping_and_output_limit(self):
        for data in (self.a, self.b):
            data['records'][1]['name'] = 'Jump\x1b[31m\n\u202e'
        self.save()
        code, out, err = self.cli('compare', self.old, self.new, '--limit', 1)
        self.assertEqual(code, 0)
        self.assertNotIn('\x1b', out)
        self.assertNotIn('\u202e', out)
        self.assertIn('\\u001b', out)

    def test_changed_only_hides_aslr_but_not_file_offset_change(self):
        move(self.b['records'][1], 0x2000, base=0x90000000)
        r = self.report()
        self.assertIn('matches: 0', '\n'.join(d.render_text(r, changed_only=True)))
        self.b['records'][1]['elf_file_offset'] = '0x9000'
        self.assertIn('matches: 1', '\n'.join(d.render_text(self.report(), changed_only=True)))

    def test_deterministic_results_and_complete_accounting(self):
        for i in range(30):
            row = copy.deepcopy(self.a['records'][1])
            row['name'] = 'Method' + str(i)
            self.a['records'].append(row)
            if i % 3:
                self.b['records'].append(copy.deepcopy(row))
        r = self.report()
        self.assertEqual(r, self.report())
        self.assertEqual(len(r['matches']) + len(r['old_only']), 31)

    def test_empty_dumps(self):
        self.a['records'], self.b['records'] = [], []
        self.assertEqual(self.report()['summary']['matches'], 0)


if __name__ == '__main__':
    unittest.main()
