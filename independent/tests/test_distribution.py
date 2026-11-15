import hashlib
import importlib.util
from pathlib import Path
import os
import subprocess
import struct
import tempfile
import unittest
import zipfile
ROOT=Path(__file__).resolve().parents[1]

class DistributionTests(unittest.TestCase):
    def test_sdk_integrity(self):
        data=(ROOT/'third_party/zygisk.hpp').read_bytes()
        self.assertEqual(hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest(),'9749755fbc61d167fd2e0a2bd84a7cb63e821c7f')
    def test_shell_validation_with_mock_properties(self):
        with tempfile.TemporaryDirectory() as tmp:
            d=Path(tmp)
            for command in ('getprop','setprop'):
                f=d/command;f.write_text('#!/bin/sh\nprintf "%s\\n" "$*" >> "$COMMAND_LOG"\n');f.chmod(0o755)
            env={**os.environ,'PATH':str(d)+':'+os.environ['PATH'],'COMMAND_LOG':str(d/'calls')}
            script=ROOT/'module/pxojdumper'
            for args in (['set','com.test.game'],['show'],['off']):subprocess.run(['sh',str(script),*args],env=env,check=True)
            original=(d/'calls').read_text()
            for package in ('com.test;id',"com.test'",'com.1bad','a'*91):
                r=subprocess.run(['sh',str(script),'set',package],env=env,capture_output=True)
                self.assertNotEqual(r.returncode,0)
            self.assertEqual(original,(d/'calls').read_text())
            self.assertIn('persist.pxojdumper.package com.test.game',original)
    def test_shell_syntax(self):
        for file in [ROOT/'module/pxojdumper',ROOT/'module/action.sh',ROOT/'module/customize.sh',ROOT/'module/META-INF/com/google/android/update-binary']:
            subprocess.run(['sh','-n',str(file)],check=True)
    def test_module_archive_layout(self):
        spec=importlib.util.spec_from_file_location('pxo_build',ROOT/'tools/build.py')
        build=importlib.util.module_from_spec(spec);spec.loader.exec_module(build)
        with tempfile.TemporaryDirectory() as tmp:
            d=Path(tmp)
            for abi,(cls,machine) in build.ABIS.items():
                p=d/abi/'libpxojdumper.so';p.parent.mkdir()
                data=bytearray(64);data[:6]=b'\x7fELF'+bytes([cls,1]);struct.pack_into('<H',data,18,machine);p.write_bytes(data)
            dest=build.archive(d,d/'module.zip')
            with zipfile.ZipFile(dest) as z:
                self.assertIsNone(z.testzip())
                for abi in build.ABIS:self.assertIn(f'zygisk/{abi}.so',z.namelist())
                self.assertIn('TEST_RESULTS.md',z.namelist())
                self.assertEqual(z.read('THIRD_PARTY_NOTICES.md'),(ROOT/'THIRD_PARTY_NOTICES.md').read_bytes())
                self.assertEqual((z.getinfo('pxojdumper').external_attr>>16)&0o777,0o755)
            (d/'arm64-v8a/libpxojdumper.so').write_bytes(b'bad')
            with self.assertRaises(ValueError):build.archive(d,d/'bad.zip')

    def test_distribution_brand_and_limits(self):
        self.assertIn('name=pxojdumper',(ROOT/'module/module.prop').read_text())
        self.assertIn('native_offset\\\":null',(ROOT/'src/collector.c').read_text())
        for path in (ROOT/'src').iterdir():
            self.assertNotIn('xdl_',path.read_text())
        self.assertIn('実機',(ROOT/'README.md').read_text())
if __name__=='__main__':unittest.main()
