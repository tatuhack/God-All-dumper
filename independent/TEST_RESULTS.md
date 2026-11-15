# Verification — 0.2.0

## Verified locally

- 25 Python tests: runtime metadata, scoped native layouts, each API-evidence
  mismatch, nested names, failure reporting, budgets, packaging and configuration.
- Both layout descriptions decoded with 32-bit and 64-bit fixture widths.
- Compiled mock runtime: reported native address equals the actual function pointer.
- Loaded ELF with nonzero first PT_LOAD virtual address: RVA and ELF virtual address
  differ as expected; tests verify the actual runtime function address.
- Pointer into another DSO is attributed to that DSO rather than libil2cpp.so.
- NX/null pointers, unreadable records, unsupported/ambiguous layouts, missing
  validation evidence, ELF boundary/zero-fill cases and overflow checks.
- Node WebUI tests: validation, initial read, save/off, bridge failures, cleanup.
- Four native Release builds using Android NDK r28c / CMake 4.1.2, API23,
  -Wall -Wextra -Werror: arm64-v8a, armeabi-v7a, x86 and x86_64.
- ZIP layout, architecture headers, official SDK hash and required notices.

Build and test logs are in verification/. Address values in tests come from an
independent mock runtime and loaded test libraries, not a real Unity game.

## Not verified

- Android installation, root-manager WebView, game launch and real IL2CPP output.
- Real ARM32 pread64/Thumb integration: 32-bit fixtures on a 64-bit host test decoding
  and arithmetic only. Cross-compilation is not execution on that architecture.
- Compatibility with arbitrary Unity releases, hidden exports or modified layouts.
- Snapshot stability against concurrent loader/memory-permission changes.
- Exact original method-body identity after structural checks. Generic code sharing,
  thunks or runtime modifications can remain relevant.

AddressSanitizer/UBSan host smoke testing uses LeakSanitizer disabled because this
executor does not support its ptrace-dependent checking. No leak-test pass is claimed.
