#include "collector.h"
#include <dlfcn.h>
#include <stdio.h>
int main(int argc,char **argv){
    if(argc!=3)return 2;
    void *lib=dlopen(argv[1],RTLD_NOW);if(!lib)return 3;
    void (*mode)(int)=NULL;*(void **)(&mode)=dlsym(lib,"mock_mode");if(mode)mode(5);
    char error[256];int result=pxo_collect(lib,argv[2],100,error,sizeof(error));
    puts(error);dlclose(lib);return result;
}
