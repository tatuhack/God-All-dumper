#include "collector.h"
#include "native_offsets.h"
#include <inttypes.h>
#include <dlfcn.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <time.h>
#include <unistd.h>
#include <limits.h>

#ifndef PXO_OUTPUT_LIMIT
#define PXO_OUTPUT_LIMIT (64L*1024L*1024L)
#endif

/* Metadata APIs remain opaque. Native extraction is isolated and validated. */
typedef void Object;
struct Api {
    Object *(*domain_get)(void);
    const Object **(*domain_get_assemblies)(Object *, size_t *);
    Object *(*thread_attach)(Object *);
    void (*thread_detach)(Object *);
    const Object *(*assembly_get_image)(const Object *);
    const char *(*image_get_name)(const Object *);
    size_t (*image_get_class_count)(const Object *);
    Object *(*image_get_class)(const Object *, size_t);
    const char *(*class_get_name)(Object *);
    const char *(*class_get_namespace)(Object *);
    Object *(*class_get_declaring_type)(Object *);
    const Object *(*class_get_methods)(Object *, void **);
    Object *(*class_get_fields)(Object *, void **);
    const char *(*method_get_name)(const Object *);
    Object *(*method_get_class)(const Object *);
    uint32_t (*method_get_token)(const Object *);
    uint32_t (*method_get_flags)(const Object *,uint32_t *);
    uint32_t (*method_get_param_count)(const Object *);
    const Object *(*method_get_return_type)(const Object *);
    const Object *(*method_get_param)(const Object *, uint32_t);
    const char *(*field_get_name)(Object *);
    size_t (*field_get_offset)(Object *);
    const Object *(*field_get_type)(Object *);
    int (*field_get_flags)(Object *);
    char *(*type_get_name)(const Object *);
    void (*free)(void *);
};

#define LOAD(name) do { *(void **)(&a.name) = dlsym(library, "il2cpp_" #name); \
    if (!a.name) { snprintf(error,error_size,"Missing export: il2cpp_%s",#name); return 1; } } while (0)

/* Limit strings and escape control bytes so a name cannot inject JSON or report lines. */
static void quoted(FILE *out, const char *value) {
    fputc('"',out);
    if (value) for (size_t i=0; value[i] && i<4096; ++i) {
        unsigned char c=(unsigned char)value[i];
        if(c=='"'||c=='\\') { fputc('\\',out); fputc(c,out); }
        else if(c<32) fprintf(out,"\\u%04x",c);
        else if(c>=128) {
            size_t width = c>=0xc2 && c<=0xdf ? 2 : c>=0xe0 && c<=0xef ? 3 : c>=0xf0 && c<=0xf4 ? 4 : 0;
            bool valid=width && i+width<=4096;
            for(size_t j=1;valid && j<width;j++) valid=value[i+j] && ((unsigned char)value[i+j]&0xc0)==0x80;
            if(valid && width==3) valid=!(c==0xe0 && (unsigned char)value[i+1]<0xa0) && !(c==0xed && (unsigned char)value[i+1]>=0xa0);
            if(valid && width==4) valid=!(c==0xf0 && (unsigned char)value[i+1]<0x90) && !(c==0xf4 && (unsigned char)value[i+1]>=0x90);
            if(valid){fwrite(value+i,1,width,out);i+=width-1;}else fputs("\\ufffd",out);
        }
        else fputc(c,out);
    }
    fputc('"',out);
}
static void native_json(FILE *out,const struct PxoNative *n) {
    fputs(",\"offset_status\":",out);quoted(out,n->status);
    fputs(",\"offset_profile\":",out);quoted(out,n->profile);
    fputs(",\"offset_confidence\":",out);quoted(out,n->available?"conditional_on_runtime_layout":"unavailable");
    if(!n->available){fputs(",\"native_address\":null,\"native_offset\":null",out);return;}
    fprintf(out,",\"raw_method_pointer\":\"0x%" PRIxPTR "\",\"native_address\":\"0x%" PRIxPTR "\",\"native_offset\":\"0x%" PRIxPTR "\",\"elf_load_bias\":\"0x%" PRIxPTR "\",\"image_base\":\"0x%" PRIxPTR "\",\"elf_virtual_address\":\"0x%" PRIxPTR "\",\"thumb\":%s,\"native_module\":",n->raw,n->address,n->rva,n->load_bias,n->image_base,n->elf_vaddr,n->thumb?"true":"false");
    quoted(out,n->module);
    if(n->file_backed)fprintf(out,",\"elf_file_offset\":\"0x%" PRIxPTR "\"",n->file_offset);else fputs(",\"elf_file_offset\":null",out);
}
static void typename_json(FILE *out, struct Api *a, const Object *type) {
    char *name=type ? a->type_get_name(type) : NULL;
    quoted(out,name ? name : "<unavailable>");
    if(name) a->free(name);
}
static bool qualified_name(struct Api *a,Object *type,char *out,size_t capacity) {
    Object *chain[32];size_t depth=0;
    while(type && depth<32) {
        for(size_t i=0;i<depth;i++)if(chain[i]==type){snprintf(out,capacity,"<cyclic-type>");return false;}
        chain[depth++]=type;type=a->class_get_declaring_type(type);
    }
    if(type){snprintf(out,capacity,"<nesting-limit>");return false;}
    size_t used=0;out[0]=0;
    while(depth) {
        const char *name=a->class_get_name(chain[--depth]);
        int n=snprintf(out+used,capacity-used,"%s%s",used?"+":"",name?name:"<unavailable>");
        if(n<0||(size_t)n>=capacity-used){snprintf(out,capacity,"<name-limit>");return false;}
        used+=(size_t)n;
    }
    return true;
}
static bool expired(struct timespec *start) {
    struct timespec now; clock_gettime(CLOCK_MONOTONIC,&now);
    return now.tv_sec-start->tv_sec >= 60;
}

int pxo_collect(void *library,const char *directory,size_t max_records,char *error,size_t error_size) {
    struct Api a={0};
    if(!library||!directory||!max_records) { snprintf(error,error_size,"Invalid collector arguments");return 1; }
    LOAD(domain_get); LOAD(domain_get_assemblies); LOAD(thread_attach); LOAD(thread_detach);
    LOAD(assembly_get_image); LOAD(image_get_name); LOAD(image_get_class_count); LOAD(image_get_class);
    LOAD(class_get_name); LOAD(class_get_namespace); LOAD(class_get_declaring_type); LOAD(class_get_methods); LOAD(class_get_fields);
    LOAD(method_get_name); LOAD(method_get_param_count); LOAD(method_get_return_type); LOAD(method_get_param);
    LOAD(field_get_name); LOAD(field_get_offset); LOAD(field_get_type); LOAD(field_get_flags);
    LOAD(type_get_name); LOAD(free);
    *(void **)(&a.method_get_class)=dlsym(library,"il2cpp_method_get_class");
    *(void **)(&a.method_get_token)=dlsym(library,"il2cpp_method_get_token");
    *(void **)(&a.method_get_flags)=dlsym(library,"il2cpp_method_get_flags");
    Object *domain=a.domain_get();
    if(!domain) {snprintf(error,error_size,"IL2CPP domain is not ready");return 3;}
    Object *thread=a.thread_attach(domain);
    if(!thread) {snprintf(error,error_size,"Unable to attach collector thread");return 1;}
    size_t image_count=0;
    const Object **assemblies=a.domain_get_assemblies(domain,&image_count);
    if(!assemblies||image_count==0||image_count>65536) {
        a.thread_detach(thread);snprintf(error,error_size,"Assembly enumeration not ready or invalid");return 3;
    }
    char json_path[PATH_MAX],text_path[PATH_MAX];
    long long stamp=(long long)time(NULL);
    int n=snprintf(json_path,sizeof(json_path),"%s/dump-%lld-%ld.json",directory,stamp,(long)getpid());
    int m=snprintf(text_path,sizeof(text_path),"%s/dump-%lld-%ld.cs",directory,stamp,(long)getpid());
    if(n<0||n>=(int)sizeof(json_path)||m<0||m>=(int)sizeof(text_path)) {
        a.thread_detach(thread);snprintf(error,error_size,"Output path is too long");return 1;
    }
    FILE *json=fopen(json_path,"wx"),*text=fopen(text_path,"wx");
    if(!json||!text) {
        if(json){fclose(json);unlink(json_path);} if(text){fclose(text);unlink(text_path);}
        a.thread_detach(thread);snprintf(error,error_size,"Cannot create output files");return 1;
    }
    fprintf(json,"{\"tool\":\"pxojdumper\",\"schema\":2,\"native_offset_mode\":\"runtime_layout_validation\",\"records\":[\n");
    fprintf(text,"// pxojdumper metadata listing, not compilable C# source.\n// Native offsets require matching runtime layouts and executable ELF checks; not semantic proof.\n");
    struct PxoNativeContext *native=pxo_native_open();
    size_t native_ok=0,native_missing=0;
    size_t records=0;bool partial=false;struct timespec start;clock_gettime(CLOCK_MONOTONIC,&start);
#define BUDGET() if(records>=max_records||expired(&start)||ferror(json)||ferror(text)||ftell(json)+ftell(text)>PXO_OUTPUT_LIMIT){partial=true;goto done;}
#define ROW() do{if(records)fputs(",\n",json);records++;}while(0)
    for(size_t i=0;i<image_count;i++) {
        const Object *image=a.assembly_get_image(assemblies[i]);if(!image){partial=true;continue;}
        size_t classes=a.image_get_class_count(image);
        if(classes>max_records){partial=true;classes=max_records;}
        for(size_t c=0;c<classes;c++) {
            BUDGET();Object *klass=a.image_get_class(image,c);if(!klass){partial=true;continue;}
            char type_name[4096];if(!qualified_name(&a,klass,type_name,sizeof(type_name)))partial=true;
            size_t type_id=records;
            ROW();fprintf(json,"{\"kind\":\"type\",\"type_id\":%zu,\"qualified_name\":",type_id);quoted(json,type_name);fputs(",\"image\":",json);quoted(json,a.image_get_name(image));
            fputs(",\"namespace\":",json);quoted(json,a.class_get_namespace(klass));
            fputs(",\"name\":",json);quoted(json,a.class_get_name(klass));fputc('}',json);
            fputs("\n// Type ",text);quoted(text,a.class_get_namespace(klass));fputc('.',text);quoted(text,type_name);fputc('\n',text);
            void *iterator=NULL;const Object *method;
            while((method=a.class_get_methods(klass,&iterator))) {
                BUDGET();ROW();fprintf(json,"{\"kind\":\"method\",\"declaring_type_id\":%zu,\"declaring_type\":",type_id);quoted(json,type_name);
                fputs(",\"namespace\":",json);quoted(json,a.class_get_namespace(klass));
                fputs(",\"image\":",json);quoted(json,a.image_get_name(image));
                fputs(",\"name\":",json);quoted(json,a.method_get_name(method));
                fputs(",\"return_type\":",json);typename_json(json,&a,a.method_get_return_type(method));
                uint32_t count=a.method_get_param_count(method);
                fprintf(json,",\"parameter_count\":%u,\"parameter_types\":[",count);
                uint32_t cap=count>1024 ? 1024:count;if(cap!=count)partial=true;
                for(uint32_t p=0;p<cap;p++){if(p)fputc(',',json);typename_json(json,&a,a.method_get_param(method,p));}
                struct PxoNative offset;struct PxoEvidence evidence={0};const struct PxoEvidence *validation=NULL;
                if(a.method_get_class&&a.method_get_token&&a.method_get_flags){
                    evidence.name=(uintptr_t)a.method_get_name(method);evidence.klass=(uintptr_t)a.method_get_class(method);
                    evidence.return_type=(uintptr_t)a.method_get_return_type(method);evidence.parameter_count=count;
                    evidence.token=a.method_get_token(method);evidence.flags=a.method_get_flags(method,&evidence.iflags);
                    validation=&evidence;
                }
                pxo_native_resolve(native,method,validation,&offset);
                fputc(']',json);native_json(json,&offset);fputc('}',json);
                fputs("// Method ",text);quoted(text,a.method_get_name(method));
                if(offset.available){native_ok++;fprintf(text," (%u parameters); RVA: 0x%" PRIxPTR "; VA: 0x%" PRIxPTR "; conditional layout: %s\n",count,offset.rva,offset.address,offset.profile);}
                else {native_missing++;fprintf(text," (%u parameters); native offset unavailable: %s\n",count,offset.status);}
            }
            iterator=NULL;Object *field;
            while((field=a.class_get_fields(klass,&iterator))) {
                BUDGET();ROW();int flags=a.field_get_flags(field);size_t offset=a.field_get_offset(field);
                fprintf(json,"{\"kind\":\"field\",\"declaring_type_id\":%zu,\"declaring_type\":",type_id);quoted(json,type_name);
                fputs(",\"namespace\":",json);quoted(json,a.class_get_namespace(klass));
                fputs(",\"image\":",json);quoted(json,a.image_get_name(image));
                fputs(",\"name\":",json);quoted(json,a.field_get_name(field));
                fputs(",\"type\":",json);typename_json(json,&a,a.field_get_type(field));
                fprintf(json,",\"runtime_reported_offset\":%zu,\"flags\":%d,\"is_static\":%s,\"is_literal\":%s}",offset,flags,(flags&16)?"true":"false",(flags&64)?"true":"false");
                fputs("// Field ",text);quoted(text,a.field_get_name(field));fprintf(text," runtime offset: 0x%zx, flags: 0x%x\n",offset,flags);
            }
        }
    }
done:
    fprintf(json,"\n],\"record_count\":%zu,\"partial\":%s,\"native_offsets_validated\":%zu,\"native_offsets_unavailable\":%zu}\n",records,partial?"true":"false",native_ok,native_missing);
    pxo_native_close(native);
    fprintf(text,"// Records: %zu; partial: %s\n",records,partial?"true":"false");
    bool io_error=ferror(json)||ferror(text);if(fclose(json)!=0)io_error=true;if(fclose(text)!=0)io_error=true;
    a.thread_detach(thread);
    if(io_error){snprintf(error,error_size,"Output write failed; files may be incomplete");return 1;}
    snprintf(error,error_size,"%s: %zu records",partial?"Partial":"Complete",records);
    return partial?2:0;
}
