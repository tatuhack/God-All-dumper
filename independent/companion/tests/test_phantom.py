import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('phantom', ROOT / 'pxoj_phantom.py')
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)


def fixture():
    return {'tool':'pxojdumper','schema':2,'partial':False,'records':[
        {'kind':'type','type_id':0,'name':'Example'},
        {'kind':'method','name':'Add','declaring_type':'Example','namespace':'Test','image':'Assembly-CSharp.dll',
         'parameter_count':1,'parameter_types':['System.Int32'],'return_type':'System.Int32',
         'offset_status':'layout_and_mapping_snapshot_validated','offset_confidence':'conditional_on_runtime_layout',
         'native_address':'0x7f002000','image_base':'0x7f000000','elf_load_bias':'0x7f000000',
         'native_offset':'0x2000','elf_virtual_address':'0x2000','raw_method_pointer':'0x7f002000',
         'thumb':False,'native_module':'/data/app/test/lib/arm64/libil2cpp.so'}]}


class PhantomTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / 'dump.json'
        self.data = fixture()
        self.save()
    def tearDown(self): self.tmp.cleanup()
    def save(self): self.path.write_text(json.dumps(self.data))
    def plan(self, **kw):
        return p.make_plan(self.path,1,kw.pop('arch','arm64'),**kw)
    def test_real_schema_load(self):
        data, methods, digest = p.load_dump(self.path)
        self.assertEqual(list(methods),[1]); self.assertEqual(len(digest),64)
    def test_hits_default(self):
        plan,_ = self.plan(); self.assertEqual(plan['calling'],'hits'); self.assertEqual(plan['edits'],{'args':{},'return':None})
    def test_instance_shift_config(self):
        plan,_=self.plan(calling='instance'); self.assertEqual(plan['parameters'],['i32']); self.assertEqual(plan['result'],'i32')
    def test_bad_schema(self):
        self.data['schema']=1; self.save()
        with self.assertRaises(ValueError): p.load_dump(self.path)
    def test_bad_record(self):
        self.data['records'][1]['parameter_count']=True; self.save()
        with self.assertRaises(ValueError): p.load_dump(self.path)
    def test_missing_method(self):
        with self.assertRaises(ValueError): p.make_plan(self.path,0,'arm64')
    def test_missing_offset(self):
        self.data['records'][1]['native_offset']=None; self.save()
        with self.assertRaises(ValueError): self.plan()
    def test_inconsistent_address(self):
        self.data['records'][1]['image_base']='0x1000'; self.save()
        with self.assertRaises(ValueError): self.plan()
    def test_unvalidated_offset(self):
        self.data['records'][1]['offset_status']='unknown'; self.save()
        with self.assertRaises(ValueError): self.plan()
    def test_thumb_preserved(self):
        row=self.data['records'][1]; row['thumb']=True; row['raw_method_pointer']='0x7f002001'; self.save()
        with self.assertRaises(ValueError): self.plan()
        self.assertTrue(self.plan(arch='arm')[0]['thumb'])
    def test_shared_values_rejected_hits_allowed(self):
        self.data['records'].append(copy.deepcopy(self.data['records'][1])); self.save()
        self.assertEqual(self.plan()[0]['shared_records'],2)
        with self.assertRaises(ValueError): self.plan(calling='static')
    def test_duplicate_rva_zero_padding(self):
        second=copy.deepcopy(self.data['records'][1]);second['native_offset']='0x00002000'
        self.data['records'].append(second);self.save()
        with self.assertRaises(ValueError): self.plan(calling='static')
    def test_malformed_other_offset(self):
        second=copy.deepcopy(self.data['records'][1]);second['native_offset']=123
        self.data['records'].append(second);self.save()
        self.plan()
    def test_32bit_values_rejected(self):
        for arch in ('arm','ia32'):
            with self.assertRaises(ValueError): self.plan(arch=arch,calling='static')
    def test_float_object_pointer_ref_enum_aggregate_rejected(self):
        for kind in ('System.Single','System.Double','System.Int64','System.String','System.Int32&','System.Int32*','Game.Enum','Vector3','T'):
            self.data['records'][1]['parameter_types']=[kind]; self.save()
            with self.assertRaises(ValueError): self.plan(calling='static')
            self.plan()
    def test_struct_return_rejected_even_scalar_parameters(self):
        self.data['records'][1]['return_type']='Vector3'; self.save()
        with self.assertRaises(ValueError): self.plan(calling='static')
    def test_generic_rejected(self):
        self.data['records'][1]['declaring_type']='Example`1'; self.save()
        with self.assertRaises(ValueError): self.plan(calling='instance')
    def test_truncated_parameters_rejected(self):
        self.data['records'][1]['parameter_count']=2; self.save()
        with self.assertRaises(ValueError): self.plan(calling='static')
    def test_register_limit(self):
        row=self.data['records'][1]; row['parameter_count']=6; row['parameter_types']=['System.Int32']*6; self.save()
        self.plan(arch='x64',calling='static')
        with self.assertRaises(ValueError): self.plan(arch='x64',calling='instance')
    def test_value_bounds(self):
        for kind, (_,lo,hi) in p.SCALARS.items():
            self.assertEqual(p.scalar_value(kind,str(lo)),lo)
            self.assertEqual(p.scalar_value(kind,str(hi)),hi)
            for n in (lo-1,hi+1):
                with self.assertRaises(ValueError): p.scalar_value(kind,str(n))
        self.assertEqual(p.scalar_value('System.Boolean','true'),1)
        self.assertEqual(p.scalar_value('System.Int32','-0x12'),-18)
        self.assertEqual(p.scalar_value('System.Int32','09'),9)
    def test_staging_does_not_arm(self):
        plan,row=self.plan(calling='static'); p.prepare_edits(plan,row,['0=-5'],'99')
        self.assertEqual(plan['edits'],{'args':{'0':-5},'return':99})
        self.assertNotIn('armed',plan)
    def test_bad_stage_indices(self):
        plan,row=self.plan(calling='static')
        for value in ('-1=9','1=9','zero=9','0','0=3.5'):
            with self.assertRaises(ValueError): p.prepare_edits(plan,row,[value],None)
    def test_hits_cannot_stage(self):
        plan,row=self.plan()
        with self.assertRaises(ValueError): p.prepare_edits(plan,row,['0=5'],None)
    def test_void_return_cannot_stage(self):
        self.data['records'][1]['return_type']='System.Void'; self.save()
        plan,row=self.plan(calling='static')
        with self.assertRaises(ValueError): p.prepare_edits(plan,row,[],'1')
    def test_no_script_injection(self):
        row=self.data['records'][1]; row['name']='foo"; throw new Error("bad"); //\n\x1b[2J'; self.save()
        source=p.script_source(self.plan()[0]); self.assertIn('\\u001b',source)
        js=Path(self.tmp.name)/'generated.js'; js.write_text(source)
        subprocess.run(['node','--check',str(js)],check=True)
        self.assertNotIn('\x1b',p.safe_text(row['name']))
    def test_refuse_overwrite(self):
        with self.assertRaises(FileExistsError): p.write_new(self.path,'bad')
        p.load_dump(self.path)
    def test_cli_export_and_list(self):
        script=Path(self.tmp.name)/'hook.js'
        self.assertEqual(p.main(['export',str(self.path),'--method','1','--arch','arm64','-o',str(script)]),0)
        self.assertIn('rpc.exports = pxo',script.read_text())
        self.assertEqual(p.main(['list',str(self.path),'Add']),0)
    def test_invalid_limits(self):
        for kw in ({'ttl':0},{'ttl':3601},{'max_calls':0},{'max_calls':1000001}):
            with self.assertRaises(ValueError): self.plan(**kw)

if __name__=='__main__': unittest.main()
