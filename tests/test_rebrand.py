import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
BASE = json.loads((ROOT / 'UPSTREAM_BLOBS.json').read_text())


def blob(path):
    data = (ROOT / path).read_bytes()
    return hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()


class RebrandTests(unittest.TestCase):
    def test_native_engine_and_dependencies_unchanged(self):
        for path in BASE:
            if path.startswith('module/src/main/cpp/') and path not in {
                'module/src/main/cpp/game.h', 'module/src/main/cpp/log.h',
                'module/src/main/cpp/hack.h', 'module/src/main/cpp/il2cpp_dump.h'}:
                with self.subTest(path=path):
                    self.assertEqual(blob(path), BASE[path])

    def test_original_notices_and_helper_preserved(self):
        for path in ['LICENSE', 'template/module/webroot/kernelsu-alt.mjs', 'gradlew',
                     'gradle/wrapper/gradle-wrapper.jar']:
            self.assertEqual(blob(path), BASE[path])
        self.assertIn('Perfare', (ROOT / 'NOTICE.md').read_text())
        self.assertIn('HexHacking', (ROOT / 'THIRD_PARTY_NOTICES.txt').read_text())
        self.assertIn('Apache License', (ROOT / 'licenses/Apache-2.0.txt').read_text())

    def test_branding_and_property_consistency(self):
        config = (ROOT / 'module.gradle').read_text()
        for field in ('moduleLibraryName', 'moduleId', 'moduleName'):
            self.assertIn(f'{field} = "pxojdumper"', config)
        for path in ['module/src/main/cpp/game.h', 'template/module/service.sh',
                     'template/module/action.sh', 'template/module/webroot/index.html']:
            content = (ROOT / path).read_text()
            self.assertIn('persist.pxojdumper.package', content)
            self.assertNotIn('persist.il2cppdumper.package', content)

    def test_packaging_keeps_api_and_licenses_disables_old_updater(self):
        gradle = (ROOT / 'module/build.gradle').read_text()
        for name in ('LICENSE', 'NOTICE.md', 'THIRD_PARTY_NOTICES.txt', 'licenses'):
            self.assertIn(f'rootProject.file("{name}")', gradle)
        self.assertIn('zygisk/${it.relativePath.segments[1]}.so', gradle)
        self.assertNotIn('updateJson', gradle)
        self.assertNotIn('updateJson=', (ROOT / 'template/module/module.prop').read_text())
        self.assertFalse((ROOT / 'update.json').exists())

    def test_shell_syntax(self):
        for path in ROOT.glob('template/module/**/*.sh'):
            subprocess.run(['sh', '-n', str(path)], check=True)
        subprocess.run(['sh', '-n', str(ROOT / 'template/module/META-INF/com/google/android/update-binary')], check=True)

    @unittest.skipUnless(shutil.which('c++'), 'C++ compiler required')
    def test_native_target_property_with_stubbed_android_api(self):
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            (work / 'sys').mkdir()
            (work / 'android').mkdir()
            (work / 'sys/system_properties.h').write_text('int __system_property_get(const char*, char*);\n')
            (work / 'android/log.h').write_text('')
            test = work / 'test.cpp'
            test.write_text(r'''
#include <cstring>
#include <cstdlib>
#include <iostream>
int __system_property_get(const char* key, char* out) {
    const char* value = nullptr;
    if (!strcmp(key, "persist.pxojdumper.package")) value = getenv("TEST_PERSIST");
    if (!strcmp(key, "debug.pxojdumper.package")) value = getenv("TEST_DEBUG");
    if (value) { strcpy(out, value); return strlen(value); }
    *out = 0; return 0;
}
#include "game.h"
int main() { std::cout << GetGamePackageName(); }
''')
            exe = work / 'test'
            subprocess.run(['c++', '-std=c++20', '-I', str(work), '-I', str(ROOT / 'module/src/main/cpp'),
                            str(test), '-o', str(exe)], check=True)
            cases = [({}, 'com.example.game'), ({'TEST_DEBUG': 'com.test.debug'}, 'com.test.debug'),
                     ({'TEST_PERSIST': 'com.test.primary', 'TEST_DEBUG': 'com.test.debug'}, 'com.test.primary')]
            for env, expected in cases:
                self.assertEqual(subprocess.check_output([str(exe)], env=env, text=True), expected)

if __name__ == '__main__':
    unittest.main()
