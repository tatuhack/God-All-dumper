# Native offset validation

## Scoped layouts

Two byte-layout descriptions are implemented independently from format facts:

- 2020.3-compatible: 8 pointer-sized fields before the token; name/class/return type
  occupy pointer slots 2/3/4.
- 2022.3-compatible: 9 pointer-sized fields before the token; name/class/return type
  occupy pointer slots 3/4/5.

The token is followed by flags, implementation flags, slot, and an 8-bit parameter
count. No whole engine header or other dumper implementation is included.
Older/custom tails, missing API validation, and ambiguous matches are rejected.
A matching layout does not identify the actual Unity version.

Format references:
- https://github.com/MlgmXyysd/libil2cpp/blob/master/libil2cpp/Unity_2020.3/2020.3.0f1/il2cpp-class-internals.h
- https://github.com/MlgmXyysd/libil2cpp/blob/master/libil2cpp/Unity_2022.3/2022.3.8f1/il2cpp-class-internals.h

## Validation chain

1. Read the MethodInfo bytes through /proc/self/mem with pread64; check alignment,
   read size, checked offsets, and bounded EINTR retries. Read refusal is not bypassed.
2. Require exact pointer identities for public API name, class and return type,
   plus exact token, parameter count, flags and implementation flags.
3. Require one unambiguous supported layout. Reject null methodPointer.
4. On ARM32 only, retain the raw pointer and clear Thumb bit 0 for address arithmetic.
5. Require the normalized address in an executable initial /proc/self/maps range
   and exactly one executable PT_LOAD from dl_iterate_phdr.
6. Calculate against the actual owning ELF, even if it is not libil2cpp.so.
7. Read the same MethodInfo bytes again and reject observed changes.

These checks establish structural and snapshot evidence, not semantic proof of a
function's implementation. No function is invoked to test its behavior. Generic
sharing and thunks are valid outcomes. Concurrent mutation can still race reads.

## Address definitions

Let B be dlpi_addr (load bias), Vmin the minimum PT_LOAD p_vaddr, A the normalized
method pointer, and V/O the p_vaddr/p_offset of the matching executable segment.

- image_base = B + Vmin
- native_offset (RVA) = A - image_base
- elf_virtual_address = A - B
- elf_file_offset = O + (A - (B + V)), only if this delta is below p_filesz

`image_base` is the start of the lowest PT_LOAD segment, not an assumed zero-based
ELF virtual address or the start of its executable segment. When Vmin is nonzero,
RVA differs from ELF virtual address. File offsets are relative to the ELF image;
for an ELF stored inside an APK they are not automatically APK-container offsets.
A PT_LOAD zero-fill tail may have a runtime address without an ELF file offset.

JSON uses hexadecimal strings. Failure returns null address/offset with status.
Snapshots do not contain a content hash/build ID, so retain the matching library
build separately before comparing offsets across app versions.
