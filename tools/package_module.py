#!/usr/bin/env python3
"""Package already-built native libraries. Never installs/flashes anything."""
import argparse
import re
from pathlib import Path
import struct
import zipfile

ROOT = Path(__file__).resolve().parents[1]
ABIS = {'arm64-v8a': (2, 183), 'armeabi-v7a': (1, 40), 'x86': (1, 3), 'x86_64': (2, 62)}


def package(libs, output):
    config = dict(re.findall(r'(module\w+)\s*=\s*"([^"]*)"', (ROOT / 'module.gradle').read_text()))
    code = re.search(r'moduleVersionCode\s*=\s*(\d+)', (ROOT / 'module.gradle').read_text()).group(1)
    values = dict(id=config['moduleId'], name=config['moduleName'], version=config['moduleVersion'],
                  versionCode=code, author=config['moduleAuthor'], description=config['moduleDescription'])
    entries = {}
    for abi, (elf_class, machine) in ABIS.items():
        data = (libs / abi / 'lib' / f'lib{config["moduleLibraryName"]}.so').read_bytes()
        if len(data) < 64 or data[:4] != b'\x7fELF' or data[4] != elf_class or data[5] != 1 or struct.unpack_from('<H', data, 18)[0] != machine:
            raise ValueError(f'Invalid or wrong-ABI ELF: {abi}')
        entries[f'zygisk/{abi}.so'] = data
    template = ROOT / 'template/module'
    for p in template.rglob('*'):
        if p.is_file():
            name = str(p.relative_to(template))
            data = p.read_bytes()
            if name == 'module.prop':
                text = data.decode()
                for key, value in values.items():
                    text = text.replace('${' + key + '}', value)
                if '${' in text:
                    raise ValueError('Unresolved module.prop placeholder')
                data = text.encode()
            entries[name] = data
    for name in ('LICENSE', 'NOTICE.md', 'THIRD_PARTY_NOTICES.txt'):
        entries[name] = (ROOT / name).read_bytes()
    for p in (ROOT / 'licenses').rglob('*'):
        if p.is_file():
            entries[str(p.relative_to(ROOT))] = p.read_bytes()
    output.mkdir(parents=True, exist_ok=True)
    dest = output / f'{values["name"]}-{values["version"]}-{code}-release.zip'
    with zipfile.ZipFile(dest, 'w', zipfile.ZIP_DEFLATED) as z:
        for name, data in sorted(entries.items()):
            info = zipfile.ZipInfo(name, (2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            executable = name.endswith('.sh') or name.endswith('/update-binary')
            info.external_attr = (0o100755 if executable else 0o100644) << 16
            z.writestr(info, data)
    return dest


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--libs', type=Path, required=True, help='CMake output root with ABI/lib/libpxojdumper.so')
    parser.add_argument('--output', type=Path, default=ROOT / 'out')
    args = parser.parse_args()
    print(package(args.libs, args.output))
