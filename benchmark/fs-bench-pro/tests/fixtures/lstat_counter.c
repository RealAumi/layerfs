/* Test-only observer for the native verifier; no product instrumentation. */
#include <stdint.h>
#include <stdatomic.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>

extern int original_lstat(const char *, struct stat *) __asm("_lstat");
static const char *root;
static size_t root_length;
static _Atomic uint64_t calls;

__attribute__((constructor)) static void begin_counter(void) {
    root = getenv("FSBP_LSTAT_ROOT");
    if (root != NULL && root[0] != '\0') {
        root_length = strlen(root);
        fprintf(stderr, "FSBP_LSTAT_COUNTER_ACTIVE=1\n");
    }
}

static int counted_lstat(const char *path, struct stat *metadata) {
    if (root != NULL && strncmp(path, root, root_length) == 0 &&
        (path[root_length] == '/' || path[root_length] == '\0')) {
        atomic_fetch_add_explicit(&calls, 1, memory_order_relaxed);
    }
    return original_lstat(path, metadata);
}

__attribute__((destructor)) static void finish_counter(void) {
    if (root != NULL && root[0] != '\0') {
        fprintf(stderr, "FSBP_LSTAT_COUNTER_COUNT=%llu\n",
                (unsigned long long)atomic_load_explicit(&calls, memory_order_relaxed));
    }
}

__attribute__((used, section("__DATA,__interpose"))) static const struct {
    const void *replacement;
    const void *original;
} interpose = {(const void *)(uintptr_t)&counted_lstat,
               (const void *)(uintptr_t)&original_lstat};
