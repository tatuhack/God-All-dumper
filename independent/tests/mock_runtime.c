/* Independent test double. This is not Unity and does not validate a game. */
#include <stddef.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
static int domain,thread,assembly,image,klass,klass2,outer1,outer2,method,field,type;
static const void *assemblies[]={&assembly};
static int mode;
void mock_mode(int m){mode=m;}
void *il2cpp_domain_get(void){return mode==1?NULL:&domain;}
const void **il2cpp_domain_get_assemblies(void *d,size_t *n){(void)d;*n=mode==2?0:1;return assemblies;}
void *il2cpp_thread_attach(void *d){(void)d;return &thread;}
void il2cpp_thread_detach(void *t){(void)t;}
const void *il2cpp_assembly_get_image(const void *a){(void)a;return &image;}
const char *il2cpp_image_get_name(const void *i){(void)i;return "Game.dll";}
size_t il2cpp_image_get_class_count(const void *i){(void)i;return mode==3?2:1;}
void *il2cpp_image_get_class(const void *i,size_t n){(void)i;return n?&klass2:&klass;}
const char *il2cpp_class_get_name(void *k){return mode!=3?"Player":k==&outer1?"A":k==&outer2?"B":"Inner";}
const char *il2cpp_class_get_namespace(void *k){(void)k;return "Example";}
const void *il2cpp_class_get_methods(void *k,void **it){(void)k;if(*it && mode!=4)return NULL;*it=&method;return &method;}
void *il2cpp_class_get_fields(void *k,void **it){(void)k;if(*it)return NULL;*it=&field;return &field;}
const char *il2cpp_method_get_name(const void *m){(void)m;return "Jump\"\n日本";}
uint32_t il2cpp_method_get_param_count(const void *m){(void)m;return 1;}
const void *il2cpp_method_get_return_type(const void *m){(void)m;return &type;}
const void *il2cpp_method_get_param(const void *m,uint32_t n){(void)m;(void)n;return &type;}
const char *il2cpp_field_get_name(void *f){(void)f;return "Health";}
size_t il2cpp_field_get_offset(void *f){(void)f;return 0x24;}
const void *il2cpp_field_get_type(void *f){(void)f;return &type;}
int il2cpp_field_get_flags(void *f){(void)f;return 16;}
char *il2cpp_type_get_name(const void *t){(void)t;return strdup("System.Int32");}
void il2cpp_free(void *p){free(p);}

void *il2cpp_class_get_declaring_type(void *k){if(mode!=3)return NULL;return k==&klass?&outer1:k==&klass2?&outer2:NULL;}
