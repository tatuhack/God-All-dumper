#!/usr/bin/env python3
"""Opt-in local native smoke test, NOT an Android/Unity compatibility test.
Requires official frida Python binding, cc, and permission to attach to our child.
"""
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import time
import frida
from test_phantom import fixture, p, ROOT

with tempfile.TemporaryDirectory() as tmp:
    binary = Path(tmp)/'phantom_fixture'
    subprocess.run(['cc','-O0','-fno-inline','-fPIE','-pie','-rdynamic',str(ROOT/'tests/native_fixture.c'),'-ldl','-o',str(binary)],check=True)
    process = subprocess.Popen([str(binary)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True)
    session = script = None
    try:
        base,add,instance = [int(s,16) for s in process.stdout.readline().split()]
        data = fixture(); row=data['records'][1]
        row.update(native_module=str(binary),native_address=hex(add),raw_method_pointer=hex(add),
            image_base=hex(base),elf_load_bias=hex(base),native_offset=hex(add-base),elf_virtual_address=hex(add-base))
        dump=Path(tmp)/'fixture.json';dump.write_text(json.dumps(data))
        plan,_=p.make_plan(dump,1,'x64','static',ttl=2,max_calls=100)
        session=frida.get_local_device().attach(process.pid)
        events=[]
        script=session.create_script(p.script_source(plan));script.on('message',lambda m,d: events.append(m));script.load()
        api=script.exports_sync; api.start('SAME BUILD')
        def call(n,mode=0):
            process.stdin.write(f'{mode} {n}\n');process.stdin.flush();return int(process.stdout.readline())
        assert call(10)==11,'observe changed output'
        api.setarg(0,-5); assert call(10)==11,'staging changed output'
        api.arm('ARM'); assert call(10)==-4,'argument edit failed'
        api.setreturn(77);assert call(10)==11,'edit did not disarm'
        api.arm('ARM');assert call(10)==77,'return edit failed'
        api.disarm();assert call(10)==11,'disarm failed'
        api.arm('ARM'); time.sleep(2.2);assert call(10)==11,'TTL failed'
        assert not api.status()['active'],'TTL did not detach'
        script.unload();script=None
        row.update(native_address=hex(instance),raw_method_pointer=hex(instance),native_offset=hex(instance-base),elf_virtual_address=hex(instance-base))
        dump.write_text(json.dumps(data));plan,_=p.make_plan(dump,1,'x64','instance',max_calls=4)
        script=session.create_script(p.script_source(plan));script.on('message',lambda m,d:events.append(m));script.load()
        api=script.exports_sync;api.start('SAME BUILD')
        assert call(10,1)==12
        api.setarg(0,20);api.arm('ARM');assert call(10,1)==22,'instance index incorrect'
        api.stop('test');assert call(10,1)==12,'stop did not restore original'
        assert any(m.get('type')=='send' and m['payload'].get('event')=='calls' for m in events)
        assert not any(m.get('type')=='error' for m in events),events
        print(f'PASS: Frida {frida.__version__}, Linux x64 native fixture; observe/stage/arg/return/disarm/TTL/instance/stop/logging')
    finally:
        if script:
            try: script.unload()
            except Exception: pass
        if session:
            try: session.detach()
            except Exception: pass
        process.terminate();process.wait(timeout=5)
