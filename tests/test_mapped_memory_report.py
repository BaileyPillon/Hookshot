"""Compile the real mapped-page accounting and budget report, with no guest/game allocation."""
import argparse
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
RUN_ALL_ARGS = ['--cc', 'gcc']


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--cc', default='gcc')
    args = parser.parse_args()
    memory = (ROOT / 'host/hos_mem.c').read_text(encoding='utf-8')
    source = memory[memory.index('#define PAGES_LEAF_SHIFT'):memory.index('/* nn::os::AllocateMemoryPages')]
    allocation = memory[memory.index('HLE(_ZN2nn2os19AllocateMemoryPagesEmm)'):memory.index('/* nn::os::FreeMemoryPages')]
    free = memory[memory.index('HLE(_ZN2nn2os15FreeMemoryPagesEmm)'):memory.index('/* nn::os::QueryMemoryInfo')]
    assert allocation.index('pages_update(a, n, 1)') > allocation.index('HOS_WRITTEN(GP(a), n)')
    assert free.index('pages_update(ARG(0), ARG(1), 0)') > free.index('!hos_guest_range')
    assert 'hos_used_memory(hos_program_size + (16ULL << 20), hos_program_size + (16ULL << 20))' in memory
    svc = (ROOT / 'host/hos_svc.c').read_text(encoding='utf-8')
    assert svc.count('hos_used_memory(hos_program_size, hos_program_size + hos_heap_size)') == 2
    fixture = r'''
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define HOS_GUEST_SPACE (512ULL << 30)
static int lock_depth, legacy_mode, fail_leaf;
static unsigned allocated_leaves;
static uint64_t hos_heap_size, hos_total_memory;
#define LOCK() do { assert(!lock_depth); ++lock_depth; } while(0)
#define UNLOCK() do { assert(lock_depth == 1); --lock_depth; } while(0)
static void hos_log(const char *format, ...) { (void)format; assert(lock_depth == 1); }
static int env_on(const char *key) { assert(!strcmp(key, "HOS_MEMINFO_OLD")); return legacy_mode; }
static void *leaf_calloc(size_t n, size_t size) {
    assert(n * size == 32768);
    if (fail_leaf) return NULL;
    allocated_leaves++;
    return calloc(n, size);
}
#define calloc leaf_calloc
/* REAL ACCOUNTING */
int main(int argc, char **argv) {
    (void)argv;
    legacy_mode = argc > 1;
    hos_total_memory = 10ULL << 30;
    hos_heap_size = 7ULL << 30;
    pages_update(0x10001, 0, 1);
    assert(mapped_bytes == 0 && allocated_leaves == 0);
    pages_update(0x10000, 8192, 1);
    pages_update(0x10000, 4096, 1);
    assert(mapped_bytes == 8192 && allocated_leaves == 1);
    pages_update(0x10001, 4095, 0); /* no full page inside the range */
    assert(mapped_bytes == 8192);
    pages_update(0x10000, 4096, 0);
    pages_update(0x10000, 4096, 0); /* freeing twice must not underflow */
    assert(mapped_bytes == 4096);
    pages_update(0x11000, 4096, 0);
    assert(mapped_bytes == 0);
    pages_update((1ULL << 30) - 4096, 8192, 1); /* crosses a leaf */
    assert(mapped_bytes == 8192 && allocated_leaves == 2);
    pages_update((1ULL << 30) - 4096, 8192, 0);
    fail_leaf = 1;
    pages_update(5ULL << 30, 4096, 1);
    assert(mapped_bytes == 0); /* accounting allocation failure errs low, without rejecting the guest allocation */
    fail_leaf = 0;
    pages_update(5ULL << 30, 4096, 1);
    assert(mapped_bytes == 4096 && allocated_leaves == 3);
    uint64_t base = 1ULL << 30;
    assert(hos_used_memory(base, 123) == (legacy_mode ? 123 : base + hos_heap_size + 4096));
    assert(hos_used_memory(base, base + hos_heap_size) ==
           (legacy_mode ? base + hos_heap_size : base + hos_heap_size + 4096));
    pages_update(8ULL << 30, 3ULL << 30, 1);
    assert(hos_used_memory(base, 456) == (legacy_mode ? 456 : hos_total_memory));
    assert(hos_used_memory(UINT64_MAX, 789) == (legacy_mode ? 789 : hos_total_memory));
    hos_heap_size = UINT64_MAX;
    assert(hos_used_memory(base, 12) == (legacy_mode ? 12 : hos_total_memory));
    hos_total_memory = 0;
    assert(hos_used_memory(0, 0) == 0);
    assert(lock_depth == 0);
    for (size_t i = 0; i < sizeof mapped_bits / sizeof mapped_bits[0]; ++i) free(mapped_bits[i]);
    puts("PASS: duplicate/partial/zero maps, leaf boundaries, allocation failure, saturation and exact legacy reports");
}
'''.replace('/* REAL ACCOUNTING */', source)
    with tempfile.TemporaryDirectory(prefix='longshot-mapped-memory-') as folder:
        folder = Path(folder)
        c, exe = folder / 'report.c', folder / 'report.exe'
        c.write_text(fixture, encoding='utf-8')
        subprocess.run([args.cc, '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror', str(c), '-o', str(exe)], check=True)
        subprocess.run([str(exe)], check=True)
        subprocess.run([str(exe), 'legacy'], check=True)


if __name__ == '__main__':
    main()
