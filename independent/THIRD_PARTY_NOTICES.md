# Third-party dependency

third_party/zygisk.hpp is the unmodified official public Zygisk SDK header:
https://github.com/topjohnwu/zygisk-module-sample/blob/master/module/jni/zygisk.hpp
Git blob SHA-1: 9749755fbc61d167fd2e0a2bd84a7cb63e821c7f
Copyright 2022-2023 John "topjohnwu" Wu. The permission and disclaimer below are
also retained in the header. The upstream README identifies the SDK as 0BSD.

Permission to use, copy, modify, and/or distribute this software for any
purpose with or without fee is hereby granted.

THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES WITH
REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF MERCHANTABILITY
AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR ANY SPECIAL, DIRECT,
INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES WHATSOEVER RESULTING FROM
LOSS OF USE, DATA OR PROFITS, WHETHER IN AN ACTION OF CONTRACT, NEGLIGENCE OR
OTHER TORTIOUS ACTION, ARISING OUT OF OR IN CONNECTION WITH THE USE OR
PERFORMANCE OF THIS SOFTWARE.

The collector, UI, scripts, tests and packaging are project-specific implementations.
The only vendored external source is the public SDK header above. Byte-layout facts
for optional MethodInfo validation are documented in docs/NATIVE_OFFSETS.md; no
Unity header or existing dumper source is distributed as part of that component.
