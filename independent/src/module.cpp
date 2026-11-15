#include <sys/types.h>
#include "zygisk.hpp"
#include "collector.h"
#include <android/log.h>
#include <sys/system_properties.h>
#include <sys/stat.h>
#include <pthread.h>
#include <dlfcn.h>
#include <unistd.h>
#include <time.h>
#include <string.h>
#include <stdlib.h>
#include <stdio.h>

static void *run_collector(void *context) {
    char *app_dir=static_cast<char *>(context);
    char directory[4096],files[4096];
    int base=snprintf(files,sizeof(files),"%s/files",app_dir);
    if(base<0||base>=(int)sizeof(files)){free(app_dir);return nullptr;}
    if(mkdir(files,0700)!=0 && access(files,W_OK)!=0){free(app_dir);return nullptr;}
    int count=snprintf(directory,sizeof(directory),"%s/files/pxojdumper",app_dir);free(app_dir);
    if(count<0||count>=(int)sizeof(directory))return nullptr;
    /* Parent files/ is created by Android/the app. Do not change its permissions. */
    if(mkdir(directory,0700)!=0 && access(directory,W_OK)!=0){
        __android_log_print(ANDROID_LOG_ERROR,"pxojdumper","Output directory unavailable");return nullptr;
    }
    char error[256]="Runtime not loaded";
    for(int attempt=0;attempt<120;attempt++) {
        void *handle=dlopen("libil2cpp.so",RTLD_NOW|RTLD_NOLOAD);
        if(handle) {
            void *(*domain_get)()=nullptr;
            *reinterpret_cast<void **>(&domain_get)=dlsym(handle,"il2cpp_domain_get");
            if(domain_get && domain_get()) {
                int status=pxo_collect(handle,directory,200000,error,sizeof(error));
                if(status==3){dlclose(handle);usleep(500000);continue;}
                __android_log_print(status==1?ANDROID_LOG_ERROR:ANDROID_LOG_INFO,"pxojdumper","%s",error);
                dlclose(handle);
                return nullptr;
            }
            dlclose(handle);
        }
        usleep(500000);
    }
    __android_log_print(ANDROID_LOG_ERROR,"pxojdumper","Runtime unavailable after 60 seconds; no loader bypass attempted");
    return nullptr;
}

class PxoModule final : public zygisk::ModuleBase {
    zygisk::Api *api=nullptr;
    JNIEnv *env=nullptr;
    char *directory=nullptr;
public:
    void onLoad(zygisk::Api *a,JNIEnv *e) override {api=a;env=e;}
    void preAppSpecialize(zygisk::AppSpecializeArgs *args) override {
        char target[PROP_VALUE_MAX]={0};
        __system_property_get("persist.pxojdumper.package",target);
        if(!target[0]||!args->nice_name||!args->app_data_dir){api->setOption(zygisk::Option::DLCLOSE_MODULE_LIBRARY);return;}
        const char *name=env->GetStringUTFChars(args->nice_name,nullptr);
        bool matches=name && strcmp(name,target)==0;
        if(name)env->ReleaseStringUTFChars(args->nice_name,name);
        if(matches){
            const char *dir=env->GetStringUTFChars(args->app_data_dir,nullptr);
            if(dir){directory=strdup(dir);env->ReleaseStringUTFChars(args->app_data_dir,dir);}
        }
        if(env->ExceptionCheck())env->ExceptionClear();
        if(!directory)api->setOption(zygisk::Option::DLCLOSE_MODULE_LIBRARY);
    }
    void postAppSpecialize(const zygisk::AppSpecializeArgs *) override {
        if(!directory)return;
        pthread_t thread;
        if(pthread_create(&thread,nullptr,run_collector,directory)==0){pthread_detach(thread);directory=nullptr;}
        else {free(directory);directory=nullptr;__android_log_print(ANDROID_LOG_ERROR,"pxojdumper","Could not start collector");}
    }
};
REGISTER_ZYGISK_MODULE(PxoModule)
