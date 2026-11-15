//
// Created by Perfare on 2020/7/4.
//

#ifndef PXOJDUMPER_LOG_H
#define PXOJDUMPER_LOG_H

#include <android/log.h>

#define LOG_TAG "pxojdumper"
#define LOGD(...) __android_log_print(ANDROID_LOG_DEBUG, LOG_TAG, __VA_ARGS__)
#define LOGW(...) __android_log_print(ANDROID_LOG_WARN, LOG_TAG, __VA_ARGS__)
#define LOGE(...) __android_log_print(ANDROID_LOG_ERROR, LOG_TAG, __VA_ARGS__)
#define LOGI(...) __android_log_print(ANDROID_LOG_INFO, LOG_TAG, __VA_ARGS__)

#endif //PXOJDUMPER_LOG_H
