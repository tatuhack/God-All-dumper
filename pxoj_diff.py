#!/usr/bin/env python3
"""PXOJ Diff: compare two pxojdumper schema-2 JSON dumps, entirely offline."""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import sys
import unicodedata

VERSION = '0.1.0'
LIMIT = 70 * 1024 * 1024
MAX_RECORDS = 200000
U64 = (1 << 64) - 1
KEY_FIELDS = ('image', 'namespace', 'declaring_type', 'name', 'return_type')
PLACEHOLDERS = ('<unavailable>', '<cyclic-type>', '<nesting-limit>', '<name-limit>')
NOTICE = ('Exact metadata signatures are candidate identity, not proof of the same behavior. '
          'RVA equality does not prove unchanged code. Dump-time virtual addresses are never used to match methods. '
          'Schema 2 has no build hash, ABI, method token, generic arity or static/instance flags. '
          'Use dumps of the same ABI; binary identity and compatibility are not verified.')


def clean(value):
    return ''.join(c if not unicodedata.category(c).startswith('C') else
                   ('\\u%04x' % ord(c) if ord(c) <= 0xffff else '\\U%08x' % ord(c))
                   for c in str(value))


def strict_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate JSON object key: ' + clean(key))
        result[key] = value
    return result


def invalid_constant(value):
    raise ValueError('Non-finite JSON constant: ' + value)


def load_json(path, limit):
    with Path(path).open('rb') as stream:
        raw = stream.read(limit + 1)
    if len(raw) > limit:
        raise ValueError(f'Input exceeds {limit} bytes')
    return json.loads(raw, object_pairs_hook=strict_object, parse_constant=invalid_constant), hashlib.sha256(raw).hexdigest()


def text_field(row, key, index):
    value = row.get(key)
    if not isinstance(value, str) or len(value) > 4096:
        raise ValueError(f'Invalid {key} in record {index}')
    return value


def hexint(value):
    if not isinstance(value, str) or not re.fullmatch(r'0x[0-9a-fA-F]{1,16}', value):
        raise ValueError('Expected unsigned 64-bit 0x-prefixed hexadecimal string')
    return int(value, 16)


def owner_key(row):
    return (row['image'], row['namespace'], row['qualified_name'] if row['kind'] == 'type' else row['declaring_type'])


def method_key(row):
    return tuple(row[k] for k in KEY_FIELDS) + (row['parameter_count'], tuple(row['parameter_types']))


def label(row):
    owner = '.'.join(filter(None, (row['namespace'], row['declaring_type'])))
    return f"{row['image']} | {owner}::{row['name']}({', '.join(row['parameter_types'])}) -> {row['return_type']}"


def signature_problem(row):
    if row['parameter_count'] != len(row['parameter_types']):
        return 'parameter list is truncated'
    names = [row[k] for k in KEY_FIELDS] + row['parameter_types']
    if any(not row[k] for k in KEY_FIELDS if k != 'namespace') or any(not p for p in row['parameter_types']):
        return 'empty signature component'
    if any(any(p in name for p in PLACEHOLDERS) or '\ufffd' in name for name in names):
        return 'unavailable or lossy signature text'
    # The collector silently cuts text at 4096 bytes; a boundary-length value is suspect.
    if any(len(name.encode('utf-8', errors='surrogatepass')) >= 4096 or
           any(0xd800 <= ord(c) <= 0xdfff for c in name) for name in names):
        return 'potentially truncated or invalid Unicode signature text'
    return None


def native_evidence(row):
    """Validate recorded consistency only, never claim validation of a live binary."""
    if row.get('offset_status') != 'layout_and_mapping_snapshot_validated' or row.get('offset_confidence') != 'conditional_on_runtime_layout':
        return {'valid': False, 'reason': 'native offset unavailable or unvalidated',
                'offset_status': row.get('offset_status')}
    try:
        address, base, bias, rva, vaddr, raw = [hexint(row.get(k)) for k in
            ('native_address', 'image_base', 'elf_load_bias', 'native_offset', 'elf_virtual_address', 'raw_method_pointer')]
        if not address or bias > base or base > address or address != base + rva or address != bias + vaddr:
            raise ValueError('inconsistent address/base/RVA/ELF evidence')
        thumb = row.get('thumb')
        if type(thumb) is not bool or raw != address + int(thumb) or (thumb and address % 2):
            raise ValueError('inconsistent raw pointer / Thumb evidence')
        module = row.get('native_module')
        if not isinstance(module, str) or not module or len(module.encode('utf-8', errors='surrogatepass')) > 511 or '\ufffd' in module or module.startswith('<') or module.endswith('/'):
            raise ValueError('missing or unsupported native module')
        if any(unicodedata.category(c).startswith('C') for c in module):
            raise ValueError('control characters in native module')
        if 'elf_file_offset' not in row:
            raise ValueError('missing ELF file-offset evidence')
        file_offset = None if row['elf_file_offset'] is None else hexint(row['elf_file_offset'])
        return {'valid': True, 'module': module, 'rva': hex(rva), 'elf_virtual_address': hex(vaddr),
                'elf_file_offset': None if file_offset is None else hex(file_offset),
                'dump_time_address': hex(address), 'thumb': thumb, 'elf_min_vaddr': hex(base - bias),
                'offset_profile': row.get('offset_profile'), 'offset_status': row['offset_status']}
    except ValueError as exc:
        return {'valid': False, 'reason': str(exc), 'offset_status': row.get('offset_status')}


class Dump:
    def __init__(self, path):
        self.path = Path(path)
        self.data, self.digest = load_json(path, LIMIT)
        d = self.data
        if not isinstance(d, dict) or d.get('tool') != 'pxojdumper' or type(d.get('schema')) is not int or d['schema'] != 2:
            raise ValueError('Only pxojdumper schema-2 JSON is supported; .cs is not accepted')
        if type(d.get('partial')) is not bool:
            raise ValueError('Dump requires Boolean partial')
        self.rows = d.get('records')
        if not isinstance(self.rows, list) or len(self.rows) > MAX_RECORDS:
            raise ValueError('Invalid records or more than 200000 records')
        if 'record_count' in d and (type(d['record_count']) is not int or d['record_count'] != len(self.rows)):
            raise ValueError('record_count differs from records length')
        self.methods, self.types, self.groups, self.unresolved = {}, defaultdict(list), defaultdict(list), []
        self.modules, self.native, self.aliases = defaultdict(set), {}, defaultdict(list)
        self.counts = Counter()
        for index, row in enumerate(self.rows):
            if not isinstance(row, dict) or row.get('kind') not in ('type', 'method', 'field'):
                raise ValueError(f'Unsupported record at index {index}')
            for key in ('image', 'namespace', 'name'):
                text_field(row, key, index)
            kind = row['kind']
            self.counts[kind] += 1
            if kind == 'type':
                text_field(row, 'qualified_name', index)
                if type(row.get('type_id')) is not int or row['type_id'] != index:
                    raise ValueError(f'type_id must equal records index in record {index}')
                self.types[owner_key(row)].append(index)
            else:
                text_field(row, 'declaring_type', index)
            if kind == 'method':
                text_field(row, 'return_type', index)
                params, count = row.get('parameter_types'), row.get('parameter_count')
                if not isinstance(params, list) or len(params) > 1024 or any(not isinstance(p, str) or len(p) > 4096 for p in params):
                    raise ValueError(f'Invalid parameter_types in record {index}')
                if type(count) is not int or not len(params) <= count <= 0xffffffff:
                    raise ValueError(f'Invalid parameter_count in record {index}')
                self.methods[index] = row
                evidence = self.native[index] = native_evidence(row)
                module = row.get('native_module')
                if isinstance(module, str) and module:
                    self.modules[PurePosixPath(module).name].add(module)
                if evidence['valid']:
                    self.aliases[(evidence['module'], evidence['rva'])].append(index)
        # Validate references in a second pass. Older hand-written examples may omit them.
        for index, row in enumerate(self.rows):
            if row['kind'] == 'type':
                continue
            if 'declaring_type_id' in row:
                parent = row['declaring_type_id']
                if type(parent) is not int or not 0 <= parent < len(self.rows):
                    raise ValueError(f'Invalid declaring_type_id in record {index}')
                target = self.rows[parent]
                if target.get('kind') != 'type' or owner_key(target) != owner_key(row):
                    raise ValueError(f'Mismatched declaring_type_id in record {index}')
            if row['kind'] == 'method':
                reason = signature_problem(row)
                if len(self.types.get(owner_key(row), [])) > 1:
                    reason = 'declaring class identity appears more than once'
                if reason:
                    self.unresolved.append({'id': index, 'label': label(row), 'reason': reason})
                else:
                    self.groups[method_key(row)].append(index)

    def summary(self):
        return {'file': self.path.name, 'sha256': self.digest, 'partial': self.data['partial'],
                'records': len(self.rows), 'kinds': dict(self.counts),
                'valid_native_evidence': sum(e['valid'] for e in self.native.values())}

    def shared_count(self, index):
        e = self.native[index]
        return len(self.aliases[(e['module'], e['rva'])]) if e['valid'] else 0


def compare_native(old, new, oi, ni, policy):
    a, b = old.native[oi], new.native[ni]
    result = {'old': a, 'new': b, 'old_shared_records': old.shared_count(oi), 'new_shared_records': new.shared_count(ni)}
    if not a['valid'] or not b['valid']:
        result['state'] = ('unavailable_both' if not a['valid'] and not b['valid'] else
                           'became_available' if b['valid'] else 'became_unavailable')
        return result
    am, bm = a['module'], b['module']
    base = PurePosixPath(am).name
    if am == bm:
        basis = 'exact_module_path'
    elif (policy == 'basename-unique' and base == PurePosixPath(bm).name and
          len(old.modules[base]) == len(new.modules[base]) == 1):
        basis = 'unique_basename_heuristic'
    else:
        result.update(state='module_incomparable', module_basis='none')
        return result
    result.update(module_basis=basis, module_path_changed=am != bm,
                  dump_time_address_changed=a['dump_time_address'] != b['dump_time_address'],
                  elf_virtual_address_changed=a['elf_virtual_address'] != b['elf_virtual_address'],
                  elf_min_vaddr_changed=a['elf_min_vaddr'] != b['elf_min_vaddr'],
                  elf_file_offset_changed=a['elf_file_offset'] != b['elf_file_offset'],
                  offset_profile_changed=a['offset_profile'] != b['offset_profile'])
    if a['thumb'] != b['thumb']:
        result['state'] = 'thumb_mode_changed'
        return result
    delta = hexint(b['rva']) - hexint(a['rva'])
    result.update(state='rva_changed' if delta else 'rva_unchanged',
                  rva_delta=('-' if delta < 0 else '+') + hex(abs(delta)))
    return result


def compare(old, new, module_policy='basename-unique'):
    if module_policy not in ('exact', 'basename-unique'):
        raise ValueError('Invalid module policy')
    report = {'tool': 'PXOJ Diff', 'version': VERSION, 'schema': 1,
              'old_dump': old.summary(), 'new_dump': new.summary(), 'module_policy': module_policy,
              'matching': 'unique exact complete metadata signature; record IDs are dump-local',
              'notice': NOTICE, 'matches': [], 'old_only': [], 'new_only': [], 'ambiguous': [],
              'unresolved_old': old.unresolved, 'unresolved_new': new.unresolved}
    warnings = [NOTICE]
    if old.data['partial'] or new.data['partial']:
        warnings.append('At least one dump is partial. Unobserved methods may be omitted, and duplicate signatures/shared implementations may be missing.')
    warnings.append('old_only/new_only mean observed in just one dump, not confirmed deletion/addition. Renames, changed signatures, obfuscation and collection differences can produce both.')
    if module_policy == 'basename-unique':
        warnings.append('Different module paths are compared only if the basename is unique in both dumps. This is a naming heuristic, not binary identity.')
    report['warnings'] = warnings
    keys = set(old.groups) | set(new.groups)
    for key in sorted(keys):
        oi, ni = old.groups.get(key, []), new.groups.get(key, [])
        row = old.methods[oi[0]] if oi else new.methods[ni[0]]
        if len(oi) > 1 or len(ni) > 1:
            report['ambiguous'].append({'label': label(row), 'old_ids': oi, 'new_ids': ni,
                                        'reason': 'signature occurs multiple times; no arbitrary pairing'})
        elif oi and ni:
            report['matches'].append({'old_id': oi[0], 'new_id': ni[0], 'label': label(row),
                                      'native': compare_native(old, new, oi[0], ni[0], module_policy)})
        elif oi:
            report['old_only'].append({'id': oi[0], 'label': label(row), 'native': old.native[oi[0]]})
        else:
            report['new_only'].append({'id': ni[0], 'label': label(row), 'native': new.native[ni[0]]})
    report['summary'] = {k: len(report[k]) for k in ('matches', 'old_only', 'new_only', 'ambiguous', 'unresolved_old', 'unresolved_new')}
    report['summary']['native_states'] = dict(sorted(Counter(m['native']['state'] for m in report['matches']).items()))
    return report


def read_selection(path):
    chosen, _ = load_json(path, 65536)
    if (not isinstance(chosen, dict) or chosen.get('tool') != 'PXOJ Seeker' or
            type(chosen.get('schema')) is not int or chosen['schema'] != 1 or
            type(chosen.get('method_id')) is not int or chosen['method_id'] < 0 or
            not isinstance(chosen.get('dump_sha256'), str) or not re.fullmatch('[0-9a-f]{64}', chosen['dump_sha256'])):
        raise ValueError('Expected a valid PXOJ Seeker schema-1 selection')
    return chosen


def handoff(old, new, old_id, *, selection=None, module_policy='basename-unique'):
    if selection is not None:
        chosen = read_selection(selection)
        if chosen['dump_sha256'] != old.digest:
            raise ValueError('Old selection SHA-256 differs from old dump; record IDs are dump-local')
        old_id = chosen['method_id']
    if type(old_id) is not int or old_id not in old.methods:
        raise ValueError('No method with that old record ID')
    report = compare(old, new, module_policy)
    pair = next((m for m in report['matches'] if m['old_id'] == old_id), None)
    if pair is None:
        raise ValueError('No unique complete signature match for this old ID; inspect ambiguous/unresolved/old-only results')
    ni = pair['new_id']
    full_label = label(new.methods[ni])
    return {'tool': 'PXOJ Seeker', 'schema': 1, 'version': '0.1.0',
            'dump_sha256': new.digest, 'method_id': ni, 'label': full_label[:1024],
            'label_truncated': len(full_label) > 1024, 'partial_dump': new.data['partial'],
            'note': 'Candidate selection only. No connection, hook or edit was performed. Review the new build independently.',
            'generated_by': 'PXOJ Diff ' + VERSION,
            'diff_provenance': {'old_dump_sha256': old.digest, 'old_method_id': old_id,
                                'match': 'unique exact complete metadata signature',
                                'native_state': pair['native']['state'], 'old_partial': old.data['partial']}}


def render_text(report, limit=100, changed_only=False):
    yield f'PXOJ Diff {VERSION} | old -> new'
    yield f"Old: {clean(report['old_dump']['file'])} | {report['old_dump']['sha256']}"
    yield f"New: {clean(report['new_dump']['file'])} | {report['new_dump']['sha256']}"
    for warning in report['warnings']:
        yield 'Warning: ' + warning
    yield 'Summary: ' + json.dumps(report['summary'], ensure_ascii=True)
    for section in ('matches', 'old_only', 'new_only', 'ambiguous', 'unresolved_old', 'unresolved_new'):
        entries = report[section]
        if section == 'matches' and changed_only:
            entries = [e for e in entries if e['native']['state'] != 'rva_unchanged' or
                       any(e['native'].get(k) for k in ('elf_virtual_address_changed', 'elf_file_offset_changed',
                           'elf_min_vaddr_changed', 'offset_profile_changed'))]
        yield f'\n{section}: {len(entries)} (showing {min(len(entries), limit)})'
        for e in entries[:limit]:
            if section == 'matches':
                n = e['native']
                yield f"  [{e['old_id']} -> {e['new_id']}] {n['state']} | {clean(e['label'])}"
                yield f"    RVA {n['old'].get('rva', 'unavailable')} -> {n['new'].get('rva', 'unavailable')} | delta {n.get('rva_delta', 'n/a')} | {n.get('module_basis', 'n/a')}"
                if n['old_shared_records'] > 1 or n['new_shared_records'] > 1:
                    yield f"    Shared module/RVA records: {n['old_shared_records']} -> {n['new_shared_records']}"
                for k in ('elf_virtual_address_changed', 'elf_file_offset_changed', 'elf_min_vaddr_changed', 'offset_profile_changed'):
                    if n.get(k):
                        yield '    ' + k + ': true'
            elif section == 'ambiguous':
                yield f"  old={e['old_ids']} new={e['new_ids']} | {clean(e['label'])}"
            else:
                yield f"  [{e['id']}] {clean(e['label'])}" + (' | ' + clean(e['reason']) if 'reason' in e else '')
        if len(entries) > limit:
            yield '  More records omitted from text. Use --format json for the full report.'


def write_new(path, contents):
    # Exclusive creation: never overwrite dumps, selections or earlier reports.
    with Path(path).open('x', encoding='utf-8') as stream:
        for chunk in contents:
            stream.write(chunk)


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--version', action='version', version='PXOJ Diff ' + VERSION)
    sub = p.add_subparsers(dest='command', required=True)
    for command in ('compare', 'handoff'):
        s = sub.add_parser(command, help='Compare metadata and native RVA evidence' if command == 'compare' else 'Save one matched new-build candidate as a Seeker selection')
        s.add_argument('old_dump', type=Path)
        s.add_argument('new_dump', type=Path)
        s.add_argument('--module-policy', choices=('exact', 'basename-unique'), default='basename-unique')
        if command == 'compare':
            s.add_argument('--format', choices=('text', 'json'), default='text')
            s.add_argument('--limit', type=int, default=100, help='Max displayed rows per text section (1..10000); JSON is always complete')
            s.add_argument('--changed-only', action='store_true', help='Hide RVA-unchanged text rows without other offset/profile changes; JSON remains complete')
            s.add_argument('-o', '--output', type=Path)
        else:
            origin = s.add_mutually_exclusive_group(required=True)
            origin.add_argument('--old-id', type=int)
            origin.add_argument('--selection', type=Path, help='Existing selection bound to the old dump')
            s.add_argument('-o', '--output', type=Path, required=True)
    return p


def main(argv=None):
    a = parser().parse_args(argv)
    try:
        if a.command == 'compare' and not 1 <= a.limit <= 10000:
            raise ValueError('--limit must be 1..10000')
        old, new = Dump(a.old_dump), Dump(a.new_dump)
        if a.command == 'handoff':
            chosen = handoff(old, new, a.old_id, selection=a.selection, module_policy=a.module_policy)
            write_new(a.output, [json.dumps(chosen, ensure_ascii=True, indent=2), '\n'])
            print(f"Saved new-dump candidate [{chosen['method_id']}] to {clean(a.output)}")
            print(chosen['note'])
            print('Seeker/Phantom will recheck native evidence. Do not reuse an old hook script.')
            if old.data['partial'] or new.data['partial']:
                print('Warning: partial dump; omitted duplicate signatures or shared implementations cannot be ruled out.', file=sys.stderr)
        else:
            report = compare(old, new, a.module_policy)
            chunks = json.JSONEncoder(ensure_ascii=True, indent=2).iterencode(report) if a.format == 'json' else (line + '\n' for line in render_text(report, a.limit, a.changed_only))
            if a.output:
                write_new(a.output, chunks)
                print('Saved report:', clean(a.output))
            else:
                for chunk in chunks:
                    sys.stdout.write(chunk)
                if a.format == 'json':
                    print()
        return 0
    except (ValueError, OSError, RecursionError) as exc:
        print('Error:', clean(exc), file=sys.stderr)
        return 2
    except (KeyboardInterrupt, EOFError):
        print('\nCancelled.', file=sys.stderr)
        return 130


if __name__ == '__main__':
    sys.exit(main())
