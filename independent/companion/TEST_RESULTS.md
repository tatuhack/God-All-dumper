# PXOJ Phantom v0.1.0 — Verification

Verification date: 2026-11-15 UTC.

## Passed

- Python compilation: CLI and test files.
- JavaScript syntax check: generated agent.
- **28 Python unit tests**: schema parsing, bad metadata, native-offset consistency, Thumb evidence, overload IDs, duplicate-RVA normalization, unsupported signatures, scalar bounds, edit staging, output overwrite refusal, script/terminal escaping, CLI list/export, limits.
- **21 mocked-agent tests**: live-base rebasing, observation without mutation, static/instance argument indexing, signed values, return replacement, ARM gate, edit-triggered disarm, cancellation of in-flight return changes, stop/restart generation handling, call limits, TTL, bounded logs, entry-only hits, ELF/ABI/executable checks.
- Independent code review and rerun of those 49 tests after corrections.
- Existing pxojdumper suite: **25 Python tests + WebUI suite** passed. No collector, installer or WebUI source was changed by this companion.

Commands from the project root:

```sh
python3 -m py_compile companion/pxoj_phantom.py companion/tests/test_phantom.py companion/tests/live_smoke.py
node --check companion/agent.js
python3 -m unittest discover -s companion/tests -v
node companion/tests/agent_test.cjs
python3 -m unittest discover -s tests -v
node tests/webui_test.mjs
```

## Attempted, not passed

- Installed the official Frida Python package 17.26.3 in an isolated test directory and verified its import/version.
- Attempted `tests/live_smoke.py`, which compiles and starts a local C fixture then attaches Frida. The execution environment's runtime failed while attempting to create a runtime directory on a read-only filesystem and exited with status 139. A second attempt using a writable test HOME gave the same environment failure. No successful native hook result was obtained. No system security settings were changed to work around it.

The native smoke test is included so it can be run on an authorized Linux x64 development host with a functioning Frida runtime. It is not part of default unit discovery and requires Frida plus a C compiler. Its presence is not evidence of a passing test.

## Not tested

- Android devices, emulator, Termux/Bionic installation or runtime.
- Real IL2CPP-generated functions, Unity games, ARM64/ARM32/x86 machine code.
- Frida server/client connection on a device, native hook relocation, actual ABI correctness.
- Runtime-injected JavaScript under a real Frida engine. Mocked Node tests do not establish this.
- CLI-exported script in a real Frida REPL.

The release is **experimental**, not production-ready or universally compatible. Same-build, ELF-range and type checks reduce mistakes but cannot prove a function's true ABI or semantics. See README for the supported subset and operational risks.
