#pragma once
#include <stddef.h>
#include <stdint.h>
#include <stdbool.h>
struct PxoEvidence { uintptr_t name,klass,return_type; uint32_t token,parameter_count,flags,iflags; };
struct PxoNative {
    bool available,file_backed,thumb;
    const char *status,*profile;
    uintptr_t raw,address,load_bias,image_base,rva,elf_vaddr,file_offset;
    char module[512];
};
struct PxoNativeContext;
struct PxoNativeContext *pxo_native_open(void);
void pxo_native_close(struct PxoNativeContext *context);
void pxo_native_resolve(struct PxoNativeContext *context,const void *method,const struct PxoEvidence *evidence,struct PxoNative *result);
/* Pure helpers exported for deterministic boundary/profile tests. */
int pxo_match_layout(const unsigned char *data,size_t length,unsigned width,const struct PxoEvidence *evidence,uintptr_t *raw);
int pxo_segment_offsets(uintptr_t address,uintptr_t bias,uintptr_t first_vaddr,uintptr_t segment_vaddr,uintptr_t memsize,uintptr_t filesize,uintptr_t fileoff,struct PxoNative *result);

uintptr_t pxo_normalize_pointer(uintptr_t raw,bool arm32);
