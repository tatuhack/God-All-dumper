import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('diff_package', ROOT / 'package.py')
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)


class PackageTests(unittest.TestCase):
    def test_reproducible_standalone_archive_and_repack(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            a, b = root / 'a.zip', root / 'b.zip'
            self.assertEqual(p.build(a), p.build(b))
            self.assertEqual(a.read_bytes(), b.read_bytes())
            with self.assertRaises(FileExistsError):
                p.build(a)
            with zipfile.ZipFile(a) as archive:
                self.assertIsNone(archive.testzip())
                self.assertEqual(len(archive.namelist()), len(p.FILES))
                self.assertFalse(any('__pycache__' in name or name.startswith('/') or '..' in Path(name).parts for name in archive.namelist()))
                archive.extractall(root / 'unpacked')
            extracted = root / 'unpacked' / ('pxoj-diff-' + p.VERSION)
            result = subprocess.run([sys.executable, str(extracted / 'pxoj_diff.py'), 'compare',
                         str(extracted / 'examples/old-dump.json'), str(extracted / 'examples/new-dump.json'),
                         '--format', 'json'], text=True, capture_output=True, check=True)
            summary = json.loads(result.stdout)['summary']
            self.assertEqual(summary['native_states']['rva_changed'], 1)
            self.assertEqual(summary['ambiguous'], 1)
            subprocess.run([sys.executable, str(extracted / 'package.py'), str(root / 'repacked.zip')],
                           text=True, capture_output=True, check=True)
            self.assertEqual(a.read_bytes(), (root / 'repacked.zip').read_bytes())

    def test_example_handoff_is_bound_to_new_dump(self):
        with tempfile.TemporaryDirectory() as td:
            output = Path(td) / 'selection.json'
            result = subprocess.run([sys.executable, str(ROOT / 'pxoj_diff.py'), 'handoff',
                       str(ROOT / 'examples/old-dump.json'), str(ROOT / 'examples/new-dump.json'),
                       '--old-id', '1', '-o', str(output)], text=True, capture_output=True, check=True)
            import hashlib
            chosen = json.loads(output.read_text())
            self.assertEqual(chosen['method_id'], 2)
            self.assertEqual(chosen['dump_sha256'], hashlib.sha256((ROOT / 'examples/new-dump.json').read_bytes()).hexdigest())
            self.assertIn('No connection', result.stdout)


if __name__ == '__main__':
    unittest.main()
