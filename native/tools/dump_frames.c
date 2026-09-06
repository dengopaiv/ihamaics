/*
 * dump_frames.c - print a checksum of sam_set_mouth_throat's output for
 * every (mouth, throat) pair, so verify_frames.py can compare all 65536
 * cases against Python without moving 15 million numbers around.
 *
 * Host tool, not shipped in the DLL.
 */
#include <stdio.h>
#include "sam_internal.h"

/* FNV-1a over the three formant rows, little-endian per value. */
static uint32_t checksum(const sam_freqdata_t *fd)
{
    uint32_t h = 2166136261u;
    int i, row;
    const uint16_t *rows[3];
    rows[0] = fd->f1; rows[1] = fd->f2; rows[2] = fd->f3;

    for (row = 0; row < 3; row++) {
        for (i = 0; i < SAM_PHONEME_COUNT; i++) {
            uint16_t v = rows[row][i];
            h ^= (uint32_t)(v & 0xFF);       h *= 16777619u;
            h ^= (uint32_t)((v >> 8) & 0xFF); h *= 16777619u;
        }
    }
    return h;
}

int main(void)
{
    sam_freqdata_t fd;
    int mouth, throat;

    for (mouth = 0; mouth < 256; mouth++) {
        for (throat = 0; throat < 256; throat++) {
            sam_set_mouth_throat((uint8_t)mouth, (uint8_t)throat, &fd);
            printf("%d %d %u\n", mouth, throat, (unsigned)checksum(&fd));
        }
    }
    return 0;
}
