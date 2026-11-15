import importlib.util
from pathlib import Path
import struct
import tempfile
import unittest
import zipfile
ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('packager', ROOT / 'tools/package_module.py')
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)

class PackagingTests(unittest.TestCase):
    def fixture(self, root):
        for abi, (cls, machine) in p.ABIS.items():
            path = root / abi / 'lib/libpxojdumper.so'
            path.parent.mkdir(parents=True)
            data = bytearray(64)
            data[:6] = b'\x7fELF' + bytes([cls, 1])
            struct.pack_into('<H', data, 18, machine)
            path.write_bytes(data)

    def test_archive_layout_permissions_and_reproducibility(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.fixture(root / 'libs')
            dest = p.package(root / 'libs', root / 'out')
            first = dest.read_bytes()
            with zipfile.ZipFile(dest) as z:
                self.assertIsNone(z.testzip())
                for abi in p.ABIS:
                    self.assertIn(f'zygisk/{abi}.so', z.namelist())
                props = z.read('module.prop').decode()
                self.assertIn('id=pxojdumper', props)
                self.assertNotIn('${', props)
                self.assertNotIn('updateJson=', props)
                self.assertIn('licenses/Apache-2.0.txt', z.namelist())
                self.assertEqual((z.getinfo('action.sh').external_attr >> 16) & 0o777, 0o755)
                self.assertEqual(z.read('LICENSE'), (ROOT / 'LICENSE').read_bytes())
            self.assertEqual(first, p.package(root / 'libs', root / 'out').read_bytes())

    def test_wrong_architecture_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.fixture(root / 'libs')
            (root / 'libs/arm64-v8a/lib/libpxojdumper.so').write_bytes(b'invalid')
            with self.assertRaises(ValueError):
                p.package(root / 'libs', root / 'out')

if __name__ == '__main__':
    unittest.main()
