#!/usr/bin/env python3
"""Build a deterministic source-only PXOJ Phantom archive; no install or upload."""
import argparse
import hashlib
from pathlib import Path
import zipfile
ROOT=Path(__file__).resolve().parent
FILES=['LICENSE','README.md','TEST_RESULTS.md','pxoj_phantom.py','agent.js','package.py',
       'examples/sample-dump.json','tests/test_phantom.py','tests/agent_test.cjs',
       'tests/live_smoke.py','tests/native_fixture.c']

def build(path):
    path=Path(path)
    with zipfile.ZipFile(path,'x',compression=zipfile.ZIP_DEFLATED) as z:
        for name in sorted(FILES):
            data=(ROOT/name).read_bytes()
            info=zipfile.ZipInfo('pxoj-phantom-0.1.0/'+name,date_time=(2026,11,15,0,0,0))
            info.create_system=3;info.compress_type=zipfile.ZIP_DEFLATED
            info.external_attr=(0o100755 if name=='pxoj_phantom.py' else 0o100644)<<16
            z.writestr(info,data)
    with zipfile.ZipFile(path) as z:
        assert z.testzip() is None
    print(path)
    print('SHA256',hashlib.sha256(path.read_bytes()).hexdigest())
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('output',type=Path);a=p.parse_args();build(a.output)
