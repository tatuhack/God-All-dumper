#define _GNU_SOURCE
#define _LARGEFILE64_SOURCE
#include "native_offsets.h"
#include <link.h>
#include <elf.h>
#include <fcntl.h>
#include <unistd.h>
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <limits.h>

#define MAX_SEGMENTS 4096
#define MAX_MAPS 8192
struct Segment {uintptr_t bias,first,vaddr,memsz,filesz,offset;char module[512];};
struct ExecMap {uintptr_t start,end;};
struct PxoNativeContext {int fd;size_t segments,maps;bool truncated;struct Segment *segment;struct ExecMap *map;};
uintptr_t pxo_normalize_pointer(uintptr_t raw,bool arm32){return arm32?raw&~(uintptr_t)1:raw;}
static uintptr_t word(const unsigned char *p,unsigned n){uintptr_t v=0;for(unsigned i=0;i<n;i++)v|=(uintptr_t)p[i]<<(i*8);return v;}

/* Layout information is represented as byte offsets, not a copied engine struct.
   These two explicitly scoped layouts are checked against seven runtime API values. */
int pxo_match_layout(const unsigned char *data,size_t length,unsigned width,const struct PxoEvidence *e,uintptr_t *raw){
    if(!data||!e||!raw||(width!=4&&width!=8)||width>sizeof(uintptr_t)||e->parameter_count>255||e->flags>65535||e->iflags>65535)return 0;
    int matches=0,selected=0;
    for(unsigned variant=0;variant<2;variant++){
        unsigned name_slot=2+variant,token=(8+variant)*width;
        if(length<token+12)continue;
        if(word(data+name_slot*width,width)!=e->name||word(data+(name_slot+1)*width,width)!=e->klass||word(data+(name_slot+2)*width,width)!=e->return_type)continue;
        if(word(data+token,4)!=e->token||word(data+token+4,2)!=e->flags||word(data+token+6,2)!=e->iflags||data[token+10]!=e->parameter_count)continue;
        selected=(int)variant+1;matches++;
    }
    if(matches!=1)return matches>1?-1:0;
    *raw=word(data,width);return selected;
}

int pxo_segment_offsets(uintptr_t address,uintptr_t bias,uintptr_t first,uintptr_t vaddr,uintptr_t memsz,uintptr_t filesz,uintptr_t fileoff,struct PxoNative *r){
    if(first>vaddr||filesz>memsz||vaddr>UINTPTR_MAX-bias||first>UINTPTR_MAX-bias)return 0;
    uintptr_t start=bias+vaddr,base=bias+first;
    if(address<start||address-start>=memsz||address<base)return 0;
    r->address=address;r->load_bias=bias;r->image_base=base;r->rva=address-base;r->elf_vaddr=address-bias;
    uintptr_t delta=address-start;r->file_backed=delta<filesz&&fileoff<=UINTPTR_MAX-delta;
    r->file_offset=r->file_backed?fileoff+delta:0;return 1;
}

static int record_module(struct dl_phdr_info *info,size_t size,void *arg){
    (void)size;struct PxoNativeContext *c=arg;uintptr_t first=UINTPTR_MAX;
    for(unsigned i=0;i<info->dlpi_phnum;i++)if(info->dlpi_phdr[i].p_type==PT_LOAD&&info->dlpi_phdr[i].p_vaddr<first)first=info->dlpi_phdr[i].p_vaddr;
    if(first==UINTPTR_MAX)return 0;
    for(unsigned i=0;i<info->dlpi_phnum;i++){
        const ElfW(Phdr) *p=&info->dlpi_phdr[i];if(p->p_type!=PT_LOAD||!(p->p_flags&PF_X))continue;
        if(c->segments==MAX_SEGMENTS){c->truncated=true;return 1;}
        struct Segment *s=&c->segment[c->segments++];s->bias=info->dlpi_addr;s->first=first;s->vaddr=p->p_vaddr;s->memsz=p->p_memsz;s->filesz=p->p_filesz;s->offset=p->p_offset;
        int length=snprintf(s->module,sizeof(s->module),"%s",info->dlpi_name&&*info->dlpi_name?info->dlpi_name:"<main-executable>");
        if(length<0||(size_t)length>=sizeof(s->module))s->module[0]=0;
    }
    return 0;
}
struct PxoNativeContext *pxo_native_open(void){
    struct PxoNativeContext *c=calloc(1,sizeof(*c));if(!c)return NULL;c->fd=-1;
    c->segment=calloc(MAX_SEGMENTS,sizeof(*c->segment));c->map=calloc(MAX_MAPS,sizeof(*c->map));
    if(!c->segment||!c->map){pxo_native_close(c);return NULL;}
    c->fd=open("/proc/self/mem",O_RDONLY|O_CLOEXEC);
    FILE *f=fopen("/proc/self/maps","r");
    if(f){char line[2048],perms[5];unsigned long long begin,end;
        while(fgets(line,sizeof(line),f)){
            if(sscanf(line,"%llx-%llx %4s",&begin,&end,perms)!=3||!strchr(perms,'x'))continue;
            if(c->maps==MAX_MAPS){c->truncated=true;break;}
            if(begin>UINTPTR_MAX||end>UINTPTR_MAX||begin>=end)continue;
            c->map[c->maps++]=(struct ExecMap){(uintptr_t)begin,(uintptr_t)end};
        }if(ferror(f))c->truncated=true;fclose(f);
    }
    dl_iterate_phdr(record_module,c);return c;
}
void pxo_native_close(struct PxoNativeContext *c){if(!c)return;if(c->fd>=0)close(c->fd);free(c->segment);free(c->map);free(c);}

static ssize_t safe_read(int fd,uintptr_t address,void *out,size_t n){
    #if UINTPTR_MAX > INT64_MAX
    if(address>(uintptr_t)INT64_MAX){errno=EOVERFLOW;return -1;}
    #endif
    if((uint64_t)n>(uint64_t)INT64_MAX-(uint64_t)address){errno=EOVERFLOW;return -1;}
    ssize_t count;unsigned retries=0;
    do{count=pread64(fd,out,n,(off64_t)address);}while(count<0&&errno==EINTR&&++retries<3);
    return count;
}
void pxo_native_resolve(struct PxoNativeContext *c,const void *method,const struct PxoEvidence *e,struct PxoNative *r){
    memset(r,0,sizeof(*r));r->status="validation_exports_missing";r->profile="none";
    if(!e)return;
    if(!c){r->status="offset_context_unavailable";return;}
    if(c->fd<0){r->status="self_memory_read_denied";return;}
    if(!c->maps||!c->segments||c->truncated){r->status="mapping_snapshot_unavailable";return;}
    if(!method||(uintptr_t)method%sizeof(uintptr_t)){r->status="invalid_method_record";return;}
    unsigned char bytes[9*sizeof(uintptr_t)+12];memset(bytes,0,sizeof(bytes));
    ssize_t n=safe_read(c->fd,(uintptr_t)method,bytes,sizeof(bytes));
    if(n<0){r->status="method_record_read_failed";return;}
    int profile=pxo_match_layout(bytes,(size_t)n,sizeof(uintptr_t),e,&r->raw);
    if(!profile){r->status="unsupported_or_mismatched_layout";return;}
    if(profile<0){r->status="ambiguous_layout";return;}
    r->profile=profile==1?"2020.3-compatible-8ptr":"2022.3-compatible-9ptr";
    if(!r->raw){r->status="null_method_pointer";return;}
    uintptr_t address=r->raw;
#if defined(__arm__)
    r->thumb=(address&1)!=0;address=pxo_normalize_pointer(address,true);
#endif
    bool executable=false;
    for(size_t i=0;i<c->maps;i++)if(address>=c->map[i].start&&address<c->map[i].end){executable=true;break;}
    if(!executable){r->status="pointer_not_executable";return;}
    unsigned matches=0;
    for(size_t i=0;i<c->segments;i++){
        struct Segment *s=&c->segment[i];struct PxoNative candidate=*r;
        if(!pxo_segment_offsets(address,s->bias,s->first,s->vaddr,s->memsz,s->filesz,s->offset,&candidate))continue;
        matches++;*r=candidate;snprintf(r->module,sizeof(r->module),"%s",s->module);
    }
    if(matches!=1){r->status=matches?"ambiguous_elf_segment":"no_executable_elf_segment";return;}
    /* Detect mutation of the metadata record after the mapping calculation. */
    if(!r->module[0]){r->status="module_path_truncated";return;}
    size_t used=(profile==1?8:9)*sizeof(uintptr_t)+12;
    unsigned char again[sizeof(bytes)];ssize_t n2=safe_read(c->fd,(uintptr_t)method,again,used);
    if(n2!=(ssize_t)used||memcmp(bytes,again,used)){r->status="method_record_changed";return;}
    r->available=true;r->status="layout_and_mapping_snapshot_validated";
}
