# Verification: independent implementation

Date: 2026-11-15 UTC.

## Passed

- 13 Python unittest cases. Collector tests compile a C mock runtime and call the
  collector against that mock's exported functions. Cases cover method/type/field
  metadata, Japanese name preservation, JSON escaping, missing exports, runtime
  not ready, invalid output location, zero budget, nested A.Inner/B.Inner identity, record cap, and output-size cap against a nonterminating mock iterator (4KiB test limit).
- Distribution checks validate the official SDK's Git blob hash, package naming,
  shell syntax, and shell argument rejection with mocked property commands.
- Node WebUI tests: package validation, initial read, save, off, unavailable bridge,
  failed save, callback cleanup and rejected bridge errors.
- Four Android native Release builds: arm64-v8a, armeabi-v7a, x86, x86_64, API23,
  official Android NDK r28c / CMake 4.1.2. All compiled with -Wall -Wextra -Werror.
- Official Zygisk SDK API v5 is used unchanged. No C++ STL is linked.

## Not verified

No Android device installation, root-manager installer execution, reboot,
actual WebView rendering, game launch or real Unity/IL2CPP dump was tested.
Mock exports are not evidence of real Unity version compatibility.
Native method addresses/offsets, translated-architecture loading, SDK/source
reconstruction, runtime protection bypass and full existing-tool parity are absent.

## Files and provenance

The implementation is separate from the previous derivative build. Existing dumper
source files, private MethodInfo layouts, xDL, and WebUI helper libraries were not
copied into this directory. Only the official public SDK header is vendored under
its original permission/disclaimer. This is not a legal clean-room certification;
earlier research included inspecting other tools.

See verification/ for the executed test and native-build logs.

Review corrections: nested types use qualified outer+inner names and per-dump IDs;
time and output-size checks are cooperative between records, not hard execution
limits. Archive includes this test report. Installer is Magisk-format only; no
KernelSU/APatch compatibility claim is made. In-process crash risk is disclosed.

Host AddressSanitizer/UBSan smoke test was also run with LeakSanitizer disabled.
LeakSanitizer itself is unavailable under this executor's ptrace environment, so
no leak-check pass is claimed.
