#define _GNU_SOURCE
#include <dlfcn.h>
#include <stdio.h>
#include <stdint.h>
#include <unistd.h>
__attribute__((noinline)) int phantom_add(int x) { return x + 1; }
__attribute__((noinline)) int phantom_instance(void *self, int x) { return self == (void*)0x1234 ? x + 2 : -999; }
int main(void) {
    Dl_info info;
    if (!dladdr((void *)phantom_add,&info)) return 2;
    printf("%p %p %p\n",info.dli_fbase,(void *)phantom_add,(void *)phantom_instance); fflush(stdout);
    int mode, value;
    while (scanf("%d %d", &mode, &value)==2) {
        printf("%d\n",mode ? phantom_instance((void*)0x1234,value) : phantom_add(value)); fflush(stdout);
    }
    return 0;
}
