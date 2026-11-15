import ctypes as C
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[1]
P=C.c_size_t
class Evidence(C.Structure):
    _fields_=[('name',P),('klass',P),('return_type',P),('token',C.c_uint32),('parameter_count',C.c_uint32),('flags',C.c_uint32),('iflags',C.c_uint32)]
class Native(C.Structure):
    _fields_=[('available',C.c_bool),('file_backed',C.c_bool),('thumb',C.c_bool),('status',C.c_char_p),('profile',C.c_char_p)]+[(x,P) for x in ('raw','address','load_bias','image_base','rva','elf_vaddr','file_offset')]+[('module',C.c_char*512)]
class OffsetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();path=Path(cls.tmp.name)/'offsets.so'
        subprocess.run(['cc','-shared','-fPIC','-Wall','-Wextra','-Werror',str(ROOT/'src/native_offsets.c'),'-ldl','-o',str(path)],check=True)
        cls.lib=C.CDLL(str(path));cls.lib.pxo_match_layout.argtypes=[C.c_void_p,P,C.c_uint,C.POINTER(Evidence),C.POINTER(P)]
        cls.lib.pxo_segment_offsets.argtypes=[P]*7+[C.POINTER(Native)]
        cls.lib.pxo_normalize_pointer.argtypes=[P,C.c_bool];cls.lib.pxo_normalize_pointer.restype=P
        cls.lib.pxo_native_open.restype=C.c_void_p;cls.lib.pxo_native_close.argtypes=[C.c_void_p]
        cls.lib.pxo_native_resolve.argtypes=[C.c_void_p,C.c_void_p,C.POINTER(Evidence),C.POINTER(Native)]
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def data(self,width,modern):
        d=bytearray(9*width+12);e=Evidence(0x1000,0x2000,0x3000,0x6000001,2,6,0)
        def put(offset,value,n):d[offset:offset+n]=value.to_bytes(n,'little')
        put(0,0xf0000001,width)
        for i,v in enumerate((e.name,e.klass,e.return_type)):put((2+modern+i)*width,v,width)
        tail=(8+modern)*width;put(tail,e.token,4);put(tail+4,e.flags,2);put(tail+6,e.iflags,2);d[tail+10]=e.parameter_count
        return d,e
    def match(self,d,w,e):
        b=C.create_string_buffer(bytes(d));raw=P();result=self.lib.pxo_match_layout(b,len(d),w,C.byref(e),C.byref(raw));return result,raw.value
    def test_both_layouts_and_pointer_widths(self):
        for width in (4,8):
            for modern in (0,1):
                d,e=self.data(width,modern);self.assertEqual(self.match(d,width,e),(modern+1,0xf0000001))
    def test_each_validation_field_rejected(self):
        for key in ('name','klass','return_type','token','parameter_count','flags','iflags'):
            d,e=self.data(8,1);setattr(e,key,getattr(e,key)+1);self.assertEqual(self.match(d,8,e)[0],0)
    def test_short_read_unsupported_tail_and_ambiguity(self):
        d,e=self.data(8,0);self.assertEqual(self.match(d[:12],8,e)[0],0)
        # Shift a legacy tail as in unsupported historical variants.
        d[68:80]=d[64:76];d[64:68]=b'\x01\x00\x00\x00';self.assertEqual(self.match(d,8,e)[0],0)
        d=bytearray(84);self.assertEqual(self.match(d,8,Evidence())[0],-1)
    def test_nonzero_image_vaddr_and_file_offset(self):
        n=Native();self.assertEqual(self.lib.pxo_segment_offsets(0x7305,0x5000,0x1000,0x2000,0x1000,0x800,0x400,C.byref(n)),1)
        self.assertEqual((n.image_base,n.rva,n.elf_vaddr,n.file_offset),(0x6000,0x1305,0x2305,0x705))
        self.assertTrue(n.file_backed)
    def test_boundaries_bss_and_overflow(self):
        n=Native();f=self.lib.pxo_segment_offsets
        self.assertEqual(f(0x1100,0,0x1000,0x1000,0x200,0x100,0,C.byref(n)),1);self.assertFalse(n.file_backed)
        self.assertEqual(f(0x1200,0,0x1000,0x1000,0x200,0x100,0,C.byref(n)),0)
        maximum=(1<<(8*C.sizeof(P)))-1
        self.assertEqual(f(0,maximum,0,1,100,100,0,C.byref(n)),0)
        self.assertEqual(f(0x1000,0,0x1000,0x1000,2,3,0,C.byref(n)),0)
    def test_thumb_only_on_arm32(self):
        self.assertEqual(self.lib.pxo_normalize_pointer(0xf0000001,True),0xf0000000)
        self.assertEqual(self.lib.pxo_normalize_pointer(0xf0000001,False),0xf0000001)
    def test_unreadable_record_does_not_crash(self):
        ctx=self.lib.pxo_native_open();self.assertTrue(ctx)
        try:
            n=Native();e=Evidence();self.lib.pxo_native_resolve(ctx,0x1000,C.byref(e),C.byref(n))
            self.assertFalse(n.available);self.assertEqual(n.status,b'method_record_read_failed')
            self.lib.pxo_native_resolve(ctx,1,C.byref(e),C.byref(n));self.assertEqual(n.status,b'invalid_method_record')
        finally:self.lib.pxo_native_close(ctx)
    def test_missing_validation_preserves_unavailable(self):
        n=Native();self.lib.pxo_native_resolve(None,None,None,C.byref(n));self.assertEqual(n.status,b'validation_exports_missing')
if __name__=='__main__':unittest.main()
