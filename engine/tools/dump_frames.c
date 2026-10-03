/*
 * dump_frames.c - a checksum of sam_set_mouth_throat's formant table for
 * every (mouth, throat) pair, for native/tools/verify_frames.py
 * --impl engine to compare all 65,536 with the Python.
 *
 * The output format is native/tools/dump_frames.c's, line for line,
 * checksum included (docs/c17-rewrite-plan.md section 5). Rewritten from
 * that file for stage R.2. A host tool; not in the library.
 */

#include <stdio.h>

#include "voice.h"

#define FNV_OFFSET 2166136261u
#define FNV_PRIME  16777619u

static uint32_t fnv1a(uint32_t h, uint32_t byte)
{
    return (h ^ byte) * FNV_PRIME;
}

/*
 * FNV-1a over the three rows, each value as two little-endian bytes:
 * native/ held them in uint16_t and the verifier hashes them that way.
 * Here the values are bytes, so the high byte is always 0.
 */
static uint32_t checksum(const sam_freqdata_t *fd)
{
    const uint8_t *rows[3] = { fd->f1, fd->f2, fd->f3 };
    uint32_t h = FNV_OFFSET;

    for (int r = 0; r < 3; r++) {
        for (int i = 0; i < SAM_PHONEME_COUNT; i++) {
            h = fnv1a(h, rows[r][i]);
            h = fnv1a(h, 0);
        }
    }
    return h;
}

int main(void)
{
    sam_freqdata_t fd;

    for (int mouth = 0; mouth < 256; mouth++) {
        for (int throat = 0; throat < 256; throat++) {
            sam_set_mouth_throat((uint8_t)mouth, (uint8_t)throat, &fd);
            printf("%d %d %lu\n", mouth, throat, (unsigned long)checksum(&fd));
        }
    }
    return 0;
}
