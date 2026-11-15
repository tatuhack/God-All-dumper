#!/usr/bin/env python3
"""Build/package only; never uploads, flashes, reboots or changes device settings."""
import argparse
import os
from pathlib import Path
import struct
import subprocess
import zipfile

ROOT=Path(__file__).resolve().parents[1]
ABIS={'arm64-v8a':(2,183),'armeabi-v7a':(1,40),'x86':(1,3),'x86_64':(2,62)}


def archive(build, destination):
    members={}
    for abi,(elf_class,machine) in ABIS.items():
        binary=(build/abi/'libpxojdumper.so').read_bytes()
        if len(binary)<64 or binary[:6]!=b'\x7fELF'+bytes([elf_class,1]) or struct.unpack_from('<H',binary,18)[0]!=machine:
            raise ValueError(f'Invalid ELF architecture: {abi}')
        members[f'zygisk/{abi}.so']=binary
    for path in (ROOT/'module').rglob('*'):
        if path.is_file():members[path.relative_to(ROOT/'module').as_posix()]=path.read_bytes()
    for path in (ROOT/'docs').rglob('*'):
        if path.is_file():members[path.relative_to(ROOT).as_posix()]=path.read_bytes()
    for name in ('LICENSE','THIRD_PARTY_NOTICES.md','README.md','TEST_RESULTS.md'):
        members[name]=(ROOT/name).read_bytes()
    destination.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(destination,'w',compression=zipfile.ZIP_DEFLATED) as z:
        for name,data in sorted(members.items()):
            info=zipfile.ZipInfo(name,date_time=(2026,1,1,0,0,0));info.create_system=3;info.compress_type=zipfile.ZIP_DEFLATED
            mode=0o755 if name.endswith('.sh') or name.endswith('/update-binary') or name=='pxojdumper' else 0o644
            info.external_attr=(0o100000|mode)<<16;z.writestr(info,data)
    return destination


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--ndk',type=Path,default=os.environ.get('ANDROID_NDK_HOME'))
    p.add_argument('--cmake-bin',type=Path,default=os.environ.get('CMAKE_BIN'))
    p.add_argument('--build',type=Path,default=ROOT/'build')
    p.add_argument('--output',type=Path,default=ROOT/'out/pxojdumper-0.2.0-independent.zip')
    p.add_argument('--package-only',action='store_true')
    a=p.parse_args();a.build=a.build.resolve()
    if not a.package_only:
        if not a.ndk or not a.cmake_bin:p.error('Set --ndk and --cmake-bin (official Android NDK and CMake paths)')
        for abi in ABIS:
            subprocess.run([str(a.cmake_bin/'cmake'),'-S',str(ROOT),'-B',str(a.build/abi),'-G','Ninja',
                            f'-DCMAKE_MAKE_PROGRAM={a.cmake_bin}/ninja',f'-DCMAKE_TOOLCHAIN_FILE={a.ndk}/build/cmake/android.toolchain.cmake',
                            f'-DANDROID_ABI={abi}','-DANDROID_PLATFORM=android-23','-DANDROID_STL=none','-DCMAKE_BUILD_TYPE=Release'],check=True)
            subprocess.run([str(a.cmake_bin/'cmake'),'--build',str(a.build/abi),'--parallel','2'],check=True)
    print(archive(a.build,a.output))
if __name__=='__main__':main()
