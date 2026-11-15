#pragma once
#include <stddef.h>
#ifdef __cplusplus
extern "C" {
#endif
/* 0 complete, 2 bounded/partial output, 1 error, 3 runtime not ready; no assumed MethodInfo layout. */
int pxo_collect(void *library, const char *directory, size_t max_records, char *error, size_t error_size);
#ifdef __cplusplus
}
#endif
