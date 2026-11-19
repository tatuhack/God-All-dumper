#!/usr/bin/env python3
"""Build a deterministic, standalone PXOJ Diff source ZIP without overwriting."""
import argparse
import hashlib
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parent
VERSION = '0.1.0'
FILES = ('LICENSE', 'README.md', 'TEST_RESULTS.md', 'pxoj_diff.py', 'package.py',
         'examples/old-dump.json', 'examples/new-dump.json',
         'tests/test_diff.py', 'tests/test_collector_integration.py', 'tests/test_package.py', 'tests/scale_smoke.py')


def build(path):
    path = Path(path)
    payloads = [(name, (ROOT / name).read_bytes()) for name in FILES]
    with zipfile.ZipFile(path, 'x', compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in sorted(payloads):
            info = zipfile.ZipInfo(f'pxoj-diff-{VERSION}/' + name, date_time=(2026, 11, 16, 0, 0, 0))
            info.create_system = 3
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = (0o100755 if name == 'pxoj_diff.py' else 0o100644) << 16
            archive.writestr(info, data)
    with zipfile.ZipFile(path) as archive:
        if archive.testzip() is not None:
            raise ValueError('ZIP integrity check failed')
    return hashlib.sha256(path.read_bytes()).hexdigest()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    print(args.output)
    print('SHA256', build(args.output))
