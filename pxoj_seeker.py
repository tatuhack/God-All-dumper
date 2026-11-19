#!/usr/bin/env python3
"""PXOJ Seeker: Search and compare saved IL2CPP dump records."""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import re
import sys
import unicodedata

VERSION = '0.1.0'
KINDS = ('type', 'method', 'field')
OFFSET_KEYS = {'rva': 'native_offset', 'address': 'native_address', 'file': 'elf_file_offset',
               'field': 'runtime_reported_offset'}


def hexint(value):
    if not isinstance(value, str) or not re.fullmatch(r'0[xX][0-9a-fA-F]{1,16}', value):
        raise ValueError('Invalid unsigned hexadecimal value')
    return int(value, 16)


def load_dump(path):
    with path.open('rb') as f:
        raw = f.read(64 * 1024 * 1024 + 1)
    if len(raw) > 64 * 1024 * 1024:
        raise ValueError('Dump exceeds the 64 MiB limit')
    data = json.loads(raw)
    if (not isinstance(data, dict) or data.get('tool') != 'pxojdumper'
            or type(data.get('schema')) is not int or data['schema'] != 2
            or not isinstance(data.get('records'), list) or len(data['records']) > 200000):
        raise ValueError('Expected a pxojdumper schema 2 dump')
    methods = {}
    for index, row in enumerate(data['records']):
        if not isinstance(row, dict):
            raise ValueError(f'Record {index} must be an object')
        if row.get('kind') == 'method':
            required_text(row, 'return_type', index)
            params = row.get('parameter_types')
            if (not isinstance(params, list) or len(params) > 1024
                    or any(not isinstance(p, str) or len(p) > 4096 for p in params)
                    or type(row.get('parameter_count')) is not int
                    or row['parameter_count'] != len(params)):
                raise ValueError(f'Invalid method parameters in record {index}')
            methods[index] = row
    return data, methods, hashlib.sha256(raw).hexdigest()


def signature(row):
    return f"{row['image']} | {owner(row)}::{row['name']}({', '.join(row['parameter_types'])}) -> {row['return_type']}"


def offset_problem(row):
    if offset_value(row, 'rva') is None:
        return 'no valid RVA in the dump'
    return None


def clean(value):
    """Keep Unicode names readable, but never print terminal controls/bidi overrides."""
    return ''.join(c if not unicodedata.category(c).startswith('C') else
                   ('\\u%04x' % ord(c) if ord(c) <= 0xffff else '\\U%08x' % ord(c))
                   for c in str(value))


def required_text(row, key, index):
    value = row.get(key)
    if not isinstance(value, str) or len(value) > 4096:
        raise ValueError(f'Invalid {key} in record {index}')


def owner(row):
    name = row.get('qualified_name', row.get('name', '')) if row['kind'] == 'type' else row['declaring_type']
    return '.'.join(filter(None, (row['namespace'], name)))


def class_key(row):
    if row['kind'] == 'type':
        return ('id', row['type_id'])
    if row.get('declaring_type_id') is not None:
        return ('id', row['declaring_type_id'])
    return ('legacy-name', row['image'], row['namespace'], row['declaring_type'])


def label(row):
    if row['kind'] == 'method':
        return signature(row)
    prefix = f"{row['image']} | {owner(row)}"
    return prefix if row['kind'] == 'type' else f"{prefix}::{row['name']} : {row['type']}"


def offset_value(row, kind):
    if kind == 'field':
        return row.get('runtime_reported_offset') if row['kind'] == 'field' else None
    if row['kind'] != 'method':
        return None
    try:
        return hexint(row.get(OFFSET_KEYS[kind]))
    except ValueError:
        return None


def number(text):
    try:
        value = int(text, 16 if re.fullmatch(r'0[xX][0-9a-fA-F]+', text) else 10)
    except ValueError:
        raise argparse.ArgumentTypeError('Use a nonnegative decimal integer or 0x-prefixed hex') from None
    if not 0 <= value <= 0xffffffffffffffff:
        raise argparse.ArgumentTypeError('Offset must be within unsigned 64-bit range')
    return value


class Dump:
    def __init__(self, path):
        self.path = Path(path)
        self.data, self.methods, self.digest = load_dump(path)
        self.rows = self.data['records']
        if type(self.data.get('schema')) is not int or type(self.data.get('partial')) is not bool:
            raise ValueError('Expected integer schema and Boolean partial in collector output')
        self.members = defaultdict(list)
        self.aliases = defaultdict(list)
        self.counts = Counter()
        for index, row in enumerate(self.rows):
            kind = row.get('kind')
            if kind not in KINDS:
                raise ValueError(f'Unsupported record kind in record {index}')
            for key in ('image', 'namespace', 'name'):
                required_text(row, key, index)
            if kind == 'type':
                required_text(row, 'qualified_name', index)
                if type(row.get('type_id')) is not int or row['type_id'] != index:
                    raise ValueError(f'type_id must equal records[] index in record {index}')
            else:
                required_text(row, 'declaring_type', index)
                # Optional in old hand-written samples, present in real collector output.
                parent = row.get('declaring_type_id')
                if parent is not None:
                    if type(parent) is not int or not 0 <= parent < len(self.rows):
                        raise ValueError(f'Invalid declaring_type_id in record {index}')
                    target = self.rows[parent]
                    if target.get('kind') != 'type' or target.get('type_id') != parent or any(
                        target.get(k) != row.get(k) for k in ('image', 'namespace')) or target.get('qualified_name') != row['declaring_type']:
                        raise ValueError(f'Mismatched declaring_type_id in record {index}')
                self.members[class_key(row)].append(index)
            if kind == 'field':
                required_text(row, 'type', index)
                off, flags = row.get('runtime_reported_offset'), row.get('flags')
                if type(off) is not int or not 0 <= off <= 0xffffffffffffffff or type(flags) is not int:
                    raise ValueError(f'Invalid field offset/flags in record {index}')
                if type(row.get('is_static')) is not bool or type(row.get('is_literal')) is not bool:
                    raise ValueError(f'Invalid field attributes in record {index}')
                if row['is_static'] != bool(flags & 16) or row['is_literal'] != bool(flags & 64):
                    raise ValueError(f'Inconsistent field attributes in record {index}')
            if kind == 'method':
                rva = offset_value(row, 'rva')
                module = row.get('native_module')
                if isinstance(module, str) and rva is not None:
                    self.aliases[(module, rva)].append(index)
            self.counts[kind] += 1

    def row(self, index):
        if type(index) is not int or not 0 <= index < len(self.rows):
            raise ValueError(f'No record with ID {index}')
        return self.rows[index]

    def shared(self, index):
        row = self.row(index)
        if row['kind'] != 'method':
            return []
        module = row.get('native_module')
        return self.aliases.get((module, offset_value(row, 'rva')), []) if isinstance(module, str) else []

    def state(self, index):
        row = self.row(index)
        if row['kind'] == 'type':
            return 'class context'
        if row['kind'] == 'field':
            return 'field only; not a function RVA'
        reason = offset_problem(row)
        if reason:
            return 'unavailable: ' + reason
        shared = len(self.shared(index))
        return 'RVA recorded' + (f'; shared by {shared} records' if shared > 1 else '')


def searchable(row):
    fields = [('name', row['name'], 100), ('class', owner(row), 60),
              ('namespace', row['namespace'], 15), ('image', row['image'], 5)]
    if row['kind'] == 'method':
        fields += [('return', row['return_type'], 20), ('parameters', ' '.join(row['parameter_types']), 20)]
    elif row['kind'] == 'field':
        fields += [('field_type', row['type'], 20)]
    return fields


def search(dump, terms, *, kind='all', match_all=False, excluded=(), image='', class_name='',
           has_rva=False, offset=None, offset_kind=None):
    terms = list(dict.fromkeys(t.casefold() for t in terms if t))
    if len(terms) > 32 or any(len(t) > 256 for t in terms):
        raise ValueError('Use at most 32 keywords, each at most 256 characters')
    if offset is not None and offset_kind is None:
        raise ValueError('--offset requires --offset-kind: rva, address, file, or field')
    if offset_kind is not None and offset is None:
        raise ValueError('--offset-kind requires --offset')
    if has_rva and kind not in ('all', 'method'):
        raise ValueError('--has-rva is only meaningful for methods')
    results = []
    for index, row in enumerate(dump.rows):
        if kind != 'all' and row['kind'] != kind:
            continue
        if image.casefold() not in row['image'].casefold() or class_name.casefold() not in owner(row).casefold():
            continue
        if has_rva and (row['kind'] != 'method' or offset_problem(row)):
            continue
        if offset is not None and offset_value(row, offset_kind) != offset:
            continue
        fields = [(name, value.casefold(), weight) for name, value, weight in searchable(row)]
        if any(word.casefold() in value for word in excluded for _, value, _ in fields):
            continue
        evidence, score = [], 0
        for term in terms:
            matches = [(weight + (30 if term == value else 0), name) for name, value, weight in fields if term in value]
            if matches:
                points, name = max(matches)
                score += points
                evidence.append({'term': term, 'field': name})
        if terms and (not evidence or (match_all and len(evidence) != len(terms))):
            continue
        results.append({'id': index, 'kind': row['kind'], 'score': score,
                        'label': label(row), 'state': dump.state(index), 'matches': evidence})
    return sorted(results, key=lambda r: (-r['score'], r['id']))


def details(dump, index):
    row = dump.row(index)
    result = {'id': index, 'kind': row['kind'], 'label': label(row), 'state': dump.state(index),
              'record': row, 'same_class_ids': dump.members.get(class_key(row), []),
              'same_native_rva_ids': dump.shared(index)}
    return result


def print_result(item):
    print(f"[{item['id']}] {item['kind']} score={item['score']} | {clean(item['label'])}")
    why = ', '.join(f"{m['term']}:{m['field']}" for m in item['matches'])
    print('    ' + clean(item['state']) + (' | matched ' + clean(why) if why else ''))


def print_details(item):
    print(f"[{item['id']}] {item['kind']} | {clean(item['label'])}")
    print('  Status:', clean(item['state']))
    row = item['record']
    if row['kind'] == 'method':
        for title, key in [('Module', 'native_module'), ('Native RVA', 'native_offset'),
                           ('ELF file offset', 'elf_file_offset'), ('Dump-time VA (ASLR)', 'native_address'),
                           ('Offset evidence', 'offset_status'), ('Confidence', 'offset_confidence')]:
            print(f'  {title}:', clean(row.get(key)))
        aliases = item['same_native_rva_ids']
        print('  Shared module/RVA IDs:', ', '.join(map(str, aliases[:40])) or 'none')
        if len(aliases) > 40:
            print(f'  {len(aliases)} records total; use search with --offset-kind rva and --offset.')
    elif row['kind'] == 'field':
        print('  Runtime-reported FIELD offset:', hex(row['runtime_reported_offset']))
        print(f"  Static={row['is_static']}, literal={row['is_literal']}; flags={hex(row['flags'])}")
        print('  Field offsets are distinct from method RVAs.')
    members = item['same_class_ids']
    print('  Same-class member IDs:', ', '.join(map(str, members[:40])) or 'none')
    if len(members) > 40:
        print(f'  {len(members)} members total; use search --class to view more.')


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--version', action='version', version=f'PXOJ Seeker {VERSION} (Offline)')
    sub = p.add_subparsers(dest='command', required=True)
    info = sub.add_parser('info', help='Summarize schema, kinds and native availability')
    info.add_argument('dump', type=Path)
    info.add_argument('--json', action='store_true')
    s = sub.add_parser('search', help='Rank literal keywords across classes, methods and fields')
    s.add_argument('dump', type=Path)
    s.add_argument('keywords', nargs='*')
    s.add_argument('--kind', choices=('all',) + KINDS, default='all')
    s.add_argument('--all', dest='match_all', action='store_true', help='Require every keyword; default matches any')
    s.add_argument('--exclude', action='append', default=[])
    s.add_argument('--image', default='')
    s.add_argument('--class', dest='class_name', default='')
    s.add_argument('--has-rva', action='store_true', help='Only methods with a recorded RVA')
    s.add_argument('--offset', type=number)
    s.add_argument('--offset-kind', choices=tuple(OFFSET_KEYS))
    s.add_argument('--limit', type=int, default=30)
    s.add_argument('--skip', type=int, default=0)
    s.add_argument('--json', action='store_true')
    for command in ('show', 'compare'):
        s = sub.add_parser(command, help='Inspect a candidate' if command == 'show' else 'Compare 2..12 candidate record IDs')
        s.add_argument('dump', type=Path)
        s.add_argument('ids', type=int, nargs='+' if command == 'compare' else 1)
        s.add_argument('--json', action='store_true')
    return p


def main(argv=None):
    a = parser().parse_args(argv)
    try:
        dump = Dump(a.dump)
        if dump.data.get('partial'):
            print('Warning: partial dump. Missing candidates and aliases cannot be ruled out.', file=sys.stderr)
        if a.command == 'info':
            summary = {'tool': 'PXOJ Seeker', 'version': VERSION, 'dump_sha256': dump.digest,
                       'schema': 2, 'partial': bool(dump.data.get('partial')), 'records': len(dump.rows),
                       'kinds': dict(dump.counts),
                       'methods_with_recorded_rva': sum(not offset_problem(r) for r in dump.methods.values()),
                       'shared_rva_groups': sum(len(v) > 1 for v in dump.aliases.values())}
            if a.json:
                print(json.dumps(summary, ensure_ascii=True))
            else:
                for key, value in summary.items():
                    print(key + ':', clean(value))
                print('RVAs reflect the saved dump only.')
        elif a.command == 'search':
            if not 1 <= a.limit <= 1000 or a.skip < 0:
                raise ValueError('--limit must be 1..1000; --skip must be nonnegative')
            hits = search(dump, a.keywords, kind=a.kind, match_all=a.match_all, excluded=a.exclude,
                          image=a.image, class_name=a.class_name, has_rva=a.has_rva,
                          offset=a.offset, offset_kind=a.offset_kind)
            page = hits[a.skip:a.skip + a.limit]
            if a.json:
                print(json.dumps({'dump_sha256': dump.digest, 'partial': bool(dump.data.get('partial')),
                                  'total': len(hits), 'skip': a.skip, 'results': page}, ensure_ascii=True))
            else:
                for item in page:
                    print_result(item)
                print(f'{len(hits)} matches; showing {len(page)} from skip={a.skip}. Rank is name relevance, not proof of behavior.')
        elif a.command in ('show', 'compare'):
            if a.command == 'compare' and (not 2 <= len(a.ids) <= 12 or len(set(a.ids)) != len(a.ids)):
                raise ValueError('compare requires 2..12 distinct record IDs')
            items = [details(dump, i) for i in a.ids]
            if a.json:
                print(json.dumps({'dump_sha256': dump.digest, 'partial': bool(dump.data.get('partial')), 'candidates': items}, ensure_ascii=True))
            else:
                for item in items:
                    print_details(item)
                print('Name matches do not establish behavior. Compare signatures, class context, and shared RVAs.')
        return 0
    except (KeyboardInterrupt, EOFError):
        print('\nCancelled.')
        return 130
    except (ValueError, OSError, RecursionError) as exc:
        print('Error:', clean(exc), file=sys.stderr)
        return 2
    except Exception as exc:
        print('Session error:', clean(exc), file=sys.stderr)
        return 3


if __name__ == '__main__':
    sys.exit(main())
