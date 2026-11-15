#!/usr/bin/env python3
"""PXOJ Phantom: inspect pxojdumper schema-2 dumps and prepare bounded Frida hooks."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import select
import shlex
import sys
import threading

VERSION = '0.1.0'
ROOT = Path(__file__).resolve().parent
SCALARS = {
    'System.Boolean': ('bool', 0, 1), 'System.SByte': ('i8', -128, 127),
    'System.Byte': ('u8', 0, 255), 'System.Int16': ('i16', -32768, 32767),
    'System.UInt16': ('u16', 0, 65535), 'System.Char': ('u16', 0, 65535),
    'System.Int32': ('i32', -(2**31), 2**31 - 1),
    'System.UInt32': ('u32', 0, 2**32 - 1),
}
LIMIT = 70 * 1024 * 1024


def hexint(value):
    if not isinstance(value, str) or not re.fullmatch(r'0x[0-9a-fA-F]{1,16}', value):
        raise ValueError('Expected a hexadecimal address string')
    return int(value, 16)


def safe_text(value):
    # Dump metadata is untrusted. Never render ANSI/control sequences in a terminal.
    return str(value).encode('unicode_escape').decode('ascii')


def load_dump(path):
    with Path(path).open('rb') as stream:
        raw = stream.read(LIMIT + 1)
    if len(raw) > LIMIT:
        raise ValueError('Dump exceeds 70 MiB')
    data = json.loads(raw)
    if not isinstance(data, dict) or data.get('tool') != 'pxojdumper' or data.get('schema') != 2:
        raise ValueError('Only pxojdumper schema 2 JSON is accepted; .cs is not a hook source')
    rows = data.get('records')
    if not isinstance(rows, list) or len(rows) > 200000:
        raise ValueError('Invalid records or record limit exceeded')
    methods = {}
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise ValueError(f'Invalid record {index}')
        if row.get('kind') != 'method':
            continue
        for key in ('name', 'declaring_type', 'namespace', 'image', 'return_type'):
            if not isinstance(row.get(key), str) or len(row[key]) > 4096:
                raise ValueError(f'Invalid {key} in record {index}')
        params = row.get('parameter_types')
        if not isinstance(params, list) or len(params) > 1024 or any(not isinstance(p, str) or len(p) > 4096 for p in params):
            raise ValueError(f'Invalid parameters in record {index}')
        if type(row.get('parameter_count')) is not int or row['parameter_count'] < len(params):
            raise ValueError(f'Invalid parameter count in record {index}')
        methods[index] = row
    return data, methods, hashlib.sha256(raw).hexdigest()


def signature(row):
    owner = '.'.join(filter(None, (row['namespace'], row['declaring_type'])))
    return f"{row['image']} | {owner}::{row['name']}({', '.join(row['parameter_types'])}) -> {row['return_type']}"


def native_problem(row):
    if row.get('offset_status') != 'layout_and_mapping_snapshot_validated' or row.get('offset_confidence') != 'conditional_on_runtime_layout':
        return 'native offset is unavailable or not validated'
    try:
        address, base, bias, rva, vaddr = [hexint(row.get(k)) for k in (
            'native_address', 'image_base', 'elf_load_bias', 'native_offset', 'elf_virtual_address')]
        if base > address or bias > base or address != base + rva or address != bias + vaddr:
            return 'inconsistent address/RVA evidence'
        if rva > 0x7fffffff or base - bias > 0x7fffffff:
            return 'ELF/RVA exceeds the supported 2 GiB range'
        if type(row.get('thumb')) is not bool:
            return 'missing ARM mode evidence'
        if hexint(row.get('raw_method_pointer')) != address + int(row['thumb']):
            return 'raw pointer / Thumb evidence differs'
        module = row.get('native_module')
        if not isinstance(module, str) or not module or module.startswith('<') or len(module) > 511:
            return 'unsupported native module'
    except ValueError as exc:
        return str(exc)
    return None


def value_problem(row, calling, arch, shared):
    if calling not in ('static', 'instance'):
        return 'select static or instance explicitly; v0.2 does not save method flags'
    if arch not in ('arm64', 'x64'):
        return 'typed values are restricted to arm64 or x64 Linux/Android'
    if shared > 1:
        return 'multiple dump records share this native address; use hits-only'
    if any(c in row['declaring_type'] + row['name'] for c in '<>`'):
        return 'generic/compiler-generated signatures are not supported for typed values'
    if row['parameter_count'] != len(row['parameter_types']):
        return 'parameter list is truncated'
    if any(t not in SCALARS for t in row['parameter_types']):
        return 'all parameters must be supported Boolean/integer scalars (no float, object, pointer, ref, enum, struct or generic)'
    if row['return_type'] not in SCALARS and row['return_type'] != 'System.Void':
        return 'return must be a supported scalar or System.Void; hidden struct returns are unsafe'
    # Keep every known parameter in GP registers. Leave hidden MethodInfo untouched.
    available = (8 if arch == 'arm64' else 6) - (calling == 'instance')
    if row['parameter_count'] > available:
        return 'signature exceeds supported general-purpose argument registers'
    return None


def scalar_value(type_name, text):
    if type_name not in SCALARS:
        raise ValueError('Unsupported scalar type')
    kind, low, high = SCALARS[type_name]
    if kind == 'bool' and text.lower() in ('true', 'false'):
        number = int(text.lower() == 'true')
    else:
        try:
            number = int(text, 16 if re.fullmatch(r'[+-]?0[xX][0-9a-fA-F]+', text) else 10)
        except (ValueError, TypeError):
            raise ValueError(f'Expected an integer for {type_name}') from None
    if not low <= number <= high:
        raise ValueError(f'{type_name} range is {low}..{high}')
    return number


def make_plan(path, method_id, arch, calling='hits', ttl=60, max_calls=1000):
    data, methods, digest = load_dump(path)
    if method_id not in methods:
        raise ValueError('No method with that record ID')
    row = methods[method_id]
    reason = native_problem(row)
    if reason:
        raise ValueError(reason)
    if arch not in ('arm64', 'arm', 'x64', 'ia32'):
        raise ValueError('Unknown Frida architecture')
    if row['thumb'] and arch != 'arm':
        raise ValueError('Thumb dump requires arm architecture')
    shared = 0
    for candidate in methods.values():
        if candidate.get('native_module') != row['native_module']:
            continue
        try:
            shared += hexint(candidate.get('native_offset')) == hexint(row['native_offset'])
        except ValueError:
            continue
    if calling != 'hits':
        reason = value_problem(row, calling, arch, shared)
        if reason:
            raise ValueError(reason)
    if not 1 <= ttl <= 3600 or not 1 <= max_calls <= 1000000:
        raise ValueError('TTL must be 1..3600 seconds and max calls 1..1000000')
    return {
        'product': 'PXOJ Phantom', 'version': VERSION, 'dump_sha256': digest,
        'method_id': method_id, 'label': signature(row), 'partial_dump': bool(data.get('partial')),
        'module': row['native_module'], 'rva': row['native_offset'],
        'elf_min_vaddr': hex(hexint(row['image_base']) - hexint(row['elf_load_bias'])),
        'thumb': row['thumb'], 'arch': arch, 'calling': calling,
        'parameters': [SCALARS[t][0] for t in row['parameter_types']] if calling != 'hits' else [],
        'result': ('void' if row['return_type'] == 'System.Void' else SCALARS[row['return_type']][0]) if calling != 'hits' else 'unknown',
        'shared_records': shared, 'ttl_seconds': ttl, 'max_calls': max_calls,
        'edits': {'args': {}, 'return': None},
    }, row


def script_source(plan):
    # JSON encoding only: no metadata is interpolated as executable JS.
    return "'use strict';\nconst PXO_CONFIG = " + json.dumps(plan, ensure_ascii=True) + ';\n' + (ROOT / 'agent.js').read_text(encoding='utf-8')


def write_new(path, content):
    with Path(path).open('x', encoding='utf-8') as stream:
        stream.write(content)


def select_method(methods, query=''):
    while True:
        if not query:
            query = input('Search method / class (q to quit): ').strip()
        if query.lower() == 'q':
            raise KeyboardInterrupt
        hits = [(i, r) for i, r in methods.items() if query.casefold() in signature(r).casefold()]
        for i, r in hits[:60]:
            marker = 'hookable' if not native_problem(r) else 'no offset'
            print(f'[{i}] [{marker}] {safe_text(signature(r))}')
        if len(hits) > 60:
            print(f'{len(hits)} matches; only first 60 shown. Refine your search.')
        chosen = input('Record ID, or Enter to search again: ').strip()
        if chosen.isdecimal() and int(chosen) in {i for i, _ in hits}:
            return int(chosen)
        query = ''


def prepare_edits(plan, row, arg_edits, ret):
    if (arg_edits or ret is not None) and plan['calling'] == 'hits':
        raise ValueError('Edits require --calling static or instance')
    for edit in arg_edits:
        index, sep, value = edit.partition('=')
        if not sep or not index.isdecimal() or int(index) >= len(row['parameter_types']):
            raise ValueError('Use --arg INDEX=VALUE with a zero-based managed parameter index')
        plan['edits']['args'][str(int(index))] = scalar_value(row['parameter_types'][int(index)], value)
    if ret is not None:
        plan['edits']['return'] = scalar_value(row['return_type'], ret)


def interruptible_input(prompt, failed):
    print(prompt, end='', flush=True)
    while not failed.is_set():
        ready, _, _ = select.select([sys.stdin], [], [], 0.1)
        if ready:
            line = sys.stdin.readline()
            if not line:
                raise EOFError
            return line.rstrip('\r\n')
    raise ValueError('Session ended or logging failed')


def run_live(plan, row, args):
    try:
        import frida
    except ImportError:
        raise ValueError('frida Python binding is missing. Offline list/export still work. See README for Termux limitations.') from None
    print('Selected:', safe_text(plan['label']))
    print('Dump cannot prove binary identity. Use the exact same app/native-library build and ABI.')
    print('Instrumentation itself can crash the app. Start in an authorized test environment.')
    if input('Type SAME BUILD to attach in observation mode: ').strip() != 'SAME BUILD':
        print('Cancelled; no attachment.')
        return
    log = Path(args.log).open('x', encoding='utf-8')  # Never overwrite existing logs.
    lock = threading.Lock()
    failed = threading.Event()
    session = script = None
    def message(message, data):
        with lock:
            try:
                log.write(json.dumps(message, ensure_ascii=True) + '\n')
                log.flush()
                print(json.dumps(message, ensure_ascii=True))
            except (OSError, ValueError):
                failed.set()
    def detached(*reason):
        failed.set()
        print('Session detached:', safe_text(reason))
    try:
        device = frida.get_usb_device(timeout=5) if args.usb else (frida.get_local_device() if args.local else frida.get_device_manager().add_remote_device(args.host))
        session = device.attach(args.pid)
        session.on('detached', detached)
        script = session.create_script(script_source(plan))
        script.on('message', message)
        script.load()
        api = script.exports_sync
        print(json.dumps(api.start('SAME BUILD'), ensure_ascii=True))
        print('Commands: status, arg INDEX VALUE, ret VALUE, clear, arm, disarm, stop, quit')
        print('Edits are staged only. arm requires ARM and expires with this session; no automatic re-arm.')
        while not failed.is_set():
            try:
                parts = shlex.split(interruptible_input('phantom> ', failed))
            except ValueError as exc:
                if failed.is_set():
                    raise
                print('Command rejected:', safe_text(exc))
                continue
            if not parts:
                continue
            cmd = parts[0].lower()
            try:
                if cmd in ('quit', 'q', 'stop'):
                    print(json.dumps(api.stop('user'), ensure_ascii=True)); break
                if cmd == 'status' and len(parts) == 1:
                    print(json.dumps(api.status(), ensure_ascii=True))
                elif cmd == 'disarm' and len(parts) == 1:
                    print(json.dumps(api.disarm(), ensure_ascii=True))
                elif cmd == 'clear' and len(parts) == 1:
                    print(json.dumps(api.clear(), ensure_ascii=True))
                elif cmd == 'arm' and len(parts) == 1:
                    print(json.dumps(api.status(), ensure_ascii=True))
                    if interruptible_input('Changes affect future calls; side effects cannot be undone. Type ARM: ', failed).strip() == 'ARM':
                        print(json.dumps(api.arm('ARM'), ensure_ascii=True))
                elif cmd == 'arg' and len(parts) == 3 and parts[1].isdecimal():
                    index = int(parts[1])
                    if index >= len(row['parameter_types']):
                        raise ValueError('Parameter index out of range')
                    print(json.dumps(api.setarg(index, scalar_value(row['parameter_types'][index], parts[2])), ensure_ascii=True))
                elif cmd == 'ret' and len(parts) == 2:
                    print(json.dumps(api.setreturn(scalar_value(row['return_type'], parts[1])), ensure_ascii=True))
                else:
                    print('Unknown command or argument count')
            except Exception as exc:
                print('Command rejected:', safe_text(exc))
        if failed.is_set():
            raise ValueError('Session detached or logging failed; hook cleanup attempted')
    finally:
        if script is not None:
            try:
                script.exports_sync.stop('client-exit')
            except Exception:
                pass
            try:
                script.unload()
            except Exception:
                pass
        if session is not None:
            try:
                session.detach()
            except Exception:
                pass
        log.close()


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--version', action='version', version=f'PXOJ Phantom {VERSION}')
    sub = p.add_subparsers(dest='command', required=True)
    listing = sub.add_parser('list', help='Search dump without Frida or root')
    listing.add_argument('dump', type=Path)
    listing.add_argument('query', nargs='?', default='')
    listing.add_argument('--limit', type=int, default=60)
    for name in ('export', 'run'):
        item = sub.add_parser(name, help='Select a method; export JS or attach interactively')
        item.add_argument('dump', type=Path)
        item.add_argument('--method', type=int, help='Dump records[] index, as printed by list')
        item.add_argument('--arch', required=True, choices=('arm64', 'arm', 'x64', 'ia32'))
        item.add_argument('--calling', default='hits', choices=('hits', 'static', 'instance'))
        item.add_argument('--ttl', type=int, default=60)
        item.add_argument('--max-calls', type=int, default=1000)
        item.add_argument('--arg', action='append', default=[], metavar='INDEX=VALUE')
        item.add_argument('--ret', help='Stage a scalar return edit; never armed automatically')
        if name == 'export':
            item.add_argument('-o', '--output', type=Path, required=True)
        else:
            item.add_argument('--pid', type=int, required=True)
            modes = item.add_mutually_exclusive_group()
            modes.add_argument('--host', default='127.0.0.1:27042')
            modes.add_argument('--usb', action='store_true')
            modes.add_argument('--local', action='store_true', help='Local development process, not Android server')
            item.add_argument('--log', type=Path, required=True)
    a = p.parse_args(argv)
    try:
        data, methods, _ = load_dump(a.dump)
        if data.get('partial'):
            print('Warning: partial dump; duplicate-address checks cannot detect omitted methods.', file=sys.stderr)
        if a.command == 'list':
            if not 1 <= a.limit <= 10000:
                raise ValueError('--limit must be 1..10000')
            hits = [(i, r) for i, r in methods.items() if a.query.casefold() in signature(r).casefold()]
            for i, row in hits[:a.limit]:
                print(f"[{i}] [{'hookable' if not native_problem(row) else 'no offset'}] {safe_text(signature(row))}")
            print(f'{len(hits)} matches; showing {min(len(hits), a.limit)}')
            return 0
        method_id = a.method if a.method is not None else select_method(methods)
        plan, row = make_plan(a.dump, method_id, a.arch, a.calling, a.ttl, a.max_calls)
        prepare_edits(plan, row, a.arg, a.ret)
        if a.command == 'export':
            write_new(a.output, script_source(plan))
            print(f'Wrote {a.output}. No attachment or edits performed.')
            print('Frida REPL: pxo.start("SAME BUILD"); edits stay OFF until pxo.arm("ARM").')
        else:
            if a.pid <= 0:
                raise ValueError('--pid must be positive')
            run_live(plan, row, a)
        return 0
    except (KeyboardInterrupt, EOFError):
        print('\nStopped. Cleanup attempted; previous app side effects cannot be undone.')
        return 130
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        print('Error:', safe_text(exc), file=sys.stderr)
        return 2
    except Exception as exc:
        print('Frida/session error:', safe_text(exc), file=sys.stderr)
        return 3


if __name__ == '__main__':
    sys.exit(main())
