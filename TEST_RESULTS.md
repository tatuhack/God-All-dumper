# PXOJ Diff 0.1.0 verification

## Scope

Host environment: Linux x86_64, Python 3.12.14, Debian GCC 14.2.0. Tests use synthetic JSON and the existing pxojdumper C collector with a synthetic IL2CPP runtime. They are not results from a Unity game or an Android device.

## Checks

- Full source checkout: **43 tests passed, no skips** using `python3 -m unittest discover -s diff/tests -v` from the collector repository.
- Extracted standalone ZIP: **41 tests passed, 2 skipped**. The two collector integration tests require the full source checkout and C compiler. All standalone tests passed.
- Syntax compilation: `python3 -m py_compile diff/pxoj_diff.py diff/package.py` passed.
- Packaging: deterministic ZIP bytes across repeated builds, integrity check, extracted CLI comparison, SHA-bound handoff, and byte-identical repack passed.
- Independent code review and isolated edge-case tests completed. A lossy module-path case was corrected and added to regression coverage before final verification.

### Functional coverage

- Exact full signatures, overload distinctions, record reordering, Unicode names, duplicate signatures/classes, partial dumps and missing signatures.
- ASLR-only movement, positive/negative RVA changes, nonzero ELF minimum virtual address, file-offset changes, module path changes and basename collisions.
- Shared implementations, unavailable offsets, invalid Thumb/raw pointer evidence, malformed offsets, unsigned-64 arithmetic beyond JavaScript-safe integer range.
- Existing Seeker selection migration, wrong SHA rejection, exact loaded-byte SHA binding, new record IDs, blocked ambiguous handoffs and no-overwrite output.
- Malformed JSON, duplicate keys, non-finite constants, Boolean IDs, invalid references, limits, control-character escaping and input validation.
- Actual C collector output in synthetic runtime modes 0, 3, 5, 6, 7, 8 and 9. Valid native layouts 5/6 passed Diff -> Seeker -> Phantom offline plan preparation with edits unset. Unavailable layouts were retained as metadata matches, and Seeker/Phantom rejected native export. Partial collector output remained marked partial.

### Synthetic scale smoke

Two inputs each contained 20,000 methods plus one type (12,545,503 bytes per file). The new input reversed method order, moved the runtime base and increased each RVA by 0x10. All 20,000 matched with correct new IDs and +0x10 deltas.

Observed in one host run: 19.248 seconds for loading/comparing both inputs, maximum process RSS 164,264 KiB (includes synthetic input preparation). This is a single cloud-host measurement, not a Termux timing or memory guarantee. Optional reproduction: `python3 tests/scale_smoke.py`.

## Not verified

- Android hardware, Termux package installation or execution, Magisk/KernelSU/APatch.
- Real Unity games, obfuscated/custom runtimes, cross-version behavioral identity.
- Live Frida attachment, live calls, edits or target process memory.
- An actual game update pair supplied by the user.

The tool compares recorded metadata and offset evidence offline. No app process was attached, no hooks were installed, and no source repository was published or pushed for this deliverable.
