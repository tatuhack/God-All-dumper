# Verification results

Date: 2026-11-15 UTC.
Source: tatuhack/Zygisk-Il2CppDumper commit ce531f9b4a53a37b1691d008f93caa8b339ee8c4.
All downloaded upstream files were verified against their Git blob hashes before edits.
UPSTREAM_BLOBS.json records that baseline.

## Passed

- Python unittest: 8 tests. Coverage: original native core/dependency hashes, legal notices,
  branding/property consistency, ZIP layout and reproducibility, executable permissions,
  wrong-ABI rejection, shell syntax, compiled C++ target-property selection with stubbed
  Android API (persistent, debug fallback, default).
- Node WebUI mocked scenarios: no root bridge, read current target, save target,
  reject shell metacharacters, recover button state after save failure.
- Android native Release build: all four ABIs, arm64-v8a, armeabi-v7a, x86, x86_64.
- Native ELF verification: correct machine/class; zygisk_module_entry present in all
  four; JNI_OnLoad present in ARM variants; only Android system shared dependencies,
  with no libc++_shared.so dependency.
- Module archive: 15 entries, four correctly placed native libraries, expanded
  module.prop, shell modes 0755, original LICENSE and third-party notices included.
- No compiler warnings/errors found in the native build log.

## Official build tools

Downloaded with curl from Google's official Android repository and matched the
checksums advertised by Google's repository XML:

- https://dl.google.com/android/repository/android-ndk-r28c-linux.zip
  SHA-1 a7b54a5de87fecd125a17d54f73c446199e72a64
- https://dl.google.com/android/repository/cmake-4.1.2-linux.zip
  SHA-1 c8c4f1c19b75c56f28b9dcf1af928d25cf1a1471

Build command used tools/build_native.sh with Android API 23 and c++_static.
Native source implementation was unchanged. Build logs were retained locally and are excluded from this source repository.

## Not completed / limitations

- Gradle :module:assembleRelease stopped before project evaluation: the Java wrapper
  download returned java.net.SocketException: Network is unreachable. The direct NDK
  build above succeeded independently. The pinned Gradle/AGP/SDK37 route is not verified.
- No Android device installation, reboot, game launch, root-manager WebUI rendering,
  actual dump.cs output, or compatibility test against a Unity game was performed.
- Mock WebUI testing is not visual/device QA.
- Preserving upstream engine code is not proof that every game/version works.
- No GitHub push, release publication, repository rename or device configuration occurred.
