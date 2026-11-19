"""Actual C collector -> Diff -> Seeker -> Phantom, with a synthetic runtime only."""
import ctypes
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent
spec = importlib.util.spec_from_file_location('diff_integration', ROOT / 'pxoj_diff.py')
d = importlib.util.module_from_spec(spec)
spec.loader.exec_module(d)


@unittest.skipUnless((REPO / 'src/collector.c').is_file() and (REPO / 'seeker/pxoj_seeker.py').is_file(),
                     'Requires full pxojdumper checkout and C compiler; not part of standalone ZIP')
class CollectorIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        root = Path(cls.tmp.name)
        subprocess.run(['cc', '-shared', '-fPIC', '-Wall', '-Wextra', '-Werror',
                        str(REPO / 'src/collector.c'), str(REPO / 'src/native_offsets.c'),
                        '-ldl', '-o', str(root / 'collector.so')], check=True)
        subprocess.run(['cc', '-shared', '-fPIC', '-Wall', '-Wextra', '-Werror',
                        str(REPO / 'tests/mock_runtime.c'), '-o', str(root / 'runtime.so')], check=True)
        cls.collector = ctypes.CDLL(str(root / 'collector.so'))
        cls.runtime = ctypes.CDLL(str(root / 'runtime.so'))
        cls.collector.pxo_collect.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_size_t, ctypes.c_char_p, ctypes.c_size_t]
        spec = importlib.util.spec_from_file_location('seeker_diff_integration', REPO / 'seeker/pxoj_seeker.py')
        cls.seeker = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.seeker)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def collect(self, path, mode, limit=100):
        path.mkdir()
        self.runtime.mock_mode(mode)
        err = ctypes.create_string_buffer(256)
        result = self.collector.pxo_collect(self.runtime._handle, str(path).encode(), limit, err, 256)
        self.assertIn(result, (0, 2), err.value)
        return next(path.glob('*.json'))

    def test_collector_native_and_unavailable_profiles(self):
        for mode in (0, 3, 5, 6, 7, 8, 9):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as td:
                root = Path(td)
                old_path = self.collect(root / 'old', mode)
                new_path = self.collect(root / 'new', mode)
                old, new = d.Dump(old_path), d.Dump(new_path)
                r = d.compare(old, new)
                self.assertGreater(len(r['matches']), 0)
                self.assertEqual(len(r['ambiguous']), 0)
                state = r['matches'][0]['native']['state']
                self.assertEqual(state, 'rva_unchanged' if mode in (5, 6) else 'unavailable_both')
                chosen = root / 'new-selection.json'
                chosen.write_text(json.dumps(d.handoff(old, new, 1)))
                args = self.seeker.parser().parse_args(['export', str(new_path), '--selection', str(chosen),
                            '--arch', 'x64', '-o', str(root / 'hook.js')])
                if mode in (5, 6):
                    plan, row = self.seeker.prepare_handoff(args)
                    self.assertEqual(plan['dump_sha256'], new.digest)
                    self.assertEqual(plan['calling'], 'hits')
                    self.assertEqual(plan['edits'], {'args': {}, 'return': None})
                else:
                    with self.assertRaises(ValueError):
                        self.seeker.prepare_handoff(args)

    def test_collector_partial_output_stays_partial(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            a = self.collect(root / 'old', 5, limit=2)
            b = self.collect(root / 'new', 5)
            r = d.compare(d.Dump(a), d.Dump(b))
            self.assertTrue(r['old_dump']['partial'])
            self.assertFalse(r['new_dump']['partial'])
            self.assertTrue(any('partial' in w for w in r['warnings']))


if __name__ == '__main__':
    unittest.main()
