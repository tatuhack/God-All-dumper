import ctypes
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[1]

class CollectorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory()
        d=Path(cls.tmp.name)
        subprocess.run(['cc','-shared','-fPIC','-Wall','-Wextra','-Werror','-DPXO_OUTPUT_LIMIT=4096',str(ROOT/'src/collector.c'),'-ldl','-o',str(d/'collector.so')],check=True)
        subprocess.run(['cc','-shared','-fPIC','-Wall','-Wextra','-Werror',str(ROOT/'tests/mock_runtime.c'),'-o',str(d/'runtime.so')],check=True)
        cls.collector=ctypes.CDLL(str(d/'collector.so'))
        cls.runtime=ctypes.CDLL(str(d/'runtime.so'))
        cls.collector.pxo_collect.argtypes=[ctypes.c_void_p,ctypes.c_char_p,ctypes.c_size_t,ctypes.c_char_p,ctypes.c_size_t]
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def call(self,directory,limit=100,handle=None):
        error=ctypes.create_string_buffer(256)
        result=self.collector.pxo_collect(handle or self.runtime._handle,str(directory).encode(),limit,error,256)
        return result,error.value.decode()
    def setUp(self):self.runtime.mock_mode(0)
    def test_metadata_and_mock_api_field_offset(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(self.call(d)[0],0)
            data=json.loads(next(Path(d).glob('*.json')).read_text())
            self.assertEqual(data['record_count'],3)
            method=data['records'][1]
            self.assertEqual(method['name'],'Jump"\n日本')
            self.assertIsNone(method['native_offset'])
            self.assertEqual(method['parameter_types'],['System.Int32'])
            field=data['records'][2]
            self.assertEqual(field['runtime_reported_offset'],0x24)
            self.assertTrue(field['is_static'])
    def test_nested_class_names_are_not_ambiguous(self):
        self.runtime.mock_mode(3)
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(self.call(d)[0],0)
            rows=json.loads(next(Path(d).glob('*.json')).read_text())['records']
            types=[row for row in rows if row['kind']=='type']
            self.assertEqual([row['qualified_name'] for row in types],['A+Inner','B+Inner'])
            self.assertNotEqual(types[0]['type_id'],types[1]['type_id'])
            self.assertEqual(rows[1]['declaring_type_id'],types[0]['type_id'])
            self.assertEqual(rows[4]['declaring_type_id'],types[1]['type_id'])

    def test_output_limit_stops_nonterminating_iterator(self):
        self.runtime.mock_mode(4)
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(self.call(d,10000)[0],2)
            data=json.loads(next(Path(d).glob('*.json')).read_text())
            self.assertTrue(data['partial'])
            self.assertLess(data['record_count'],100)
            self.assertLess(sum(p.stat().st_size for p in Path(d).iterdir()),8192)

    def test_record_limit(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(self.call(d,1)[0],2)
            data=json.loads(next(Path(d).glob('*.json')).read_text())
            self.assertTrue(data['partial']);self.assertEqual(data['record_count'],1)
    def test_not_ready_produces_no_files(self):
        for mode in (1,2):
            self.runtime.mock_mode(mode)
            with tempfile.TemporaryDirectory() as d:
                self.assertEqual(self.call(d)[0],3);self.assertEqual(list(Path(d).iterdir()),[])
    def test_missing_exports(self):
        with tempfile.TemporaryDirectory() as d:
            result,error=self.call(d,handle=self.collector._handle)
            self.assertEqual(result,1);self.assertIn('Missing export',error)
    def test_bad_output_path(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(self.call(Path(d)/'absent')[0],1)
    def test_zero_budget(self):
        with tempfile.TemporaryDirectory() as d:self.assertEqual(self.call(d,0)[0],1)
if __name__=='__main__':unittest.main()
