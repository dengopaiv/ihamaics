/*
 * dump_prepare.c - run sam_prepare_frames over cases read from a file and
 * print a checksum of each of its eight rows, for
 * native/tools/verify_prepare.py --impl engine to compare with the
 * Python, row by row.
 *
 * Case file format, one case per line:
 *   pitch mouth throat speed singmode inflection count p1 l1 s1 p2 l2 s2 ...
 *
 * The output format is native/tools/dump_prepare.c's, line for line:
 * the frame count twice (native/ kept create_transitions' count and the
 * row length apart; the rewrite has one, docs/c17/03-r3-frames.md), then
 * FNV-1a over each row with every value as four little-endian bytes of
 * a 32-bit two's-complement int. Rewritten from that file for stage
 * R.3. A host tool; not in the library.
 */

#include <stdio.h>

#include "frames.h"

#define FNV_OFFSET 2166136261u
#define FNV_PRIME  16777619u
#define MAX_PHONEMES 4096

/* v as Python's v & 0xFFFFFFFF: the conversion to unsigned is modular. */
static uint32_t fnv_int(uint32_t h, int64_t v)
{
    const uint32_t u = (uint32_t)(uint64_t)v;

    for (int b = 0; b < 4; b++) {
        h = (h ^ ((u >> (8 * b)) & 0xFFu)) * FNV_PRIME;
    }
    return h;
}

static uint32_t hash_pitch(const sam_pitch_t *row, int n)
{
    uint32_t h = FNV_OFFSET;

    for (int i = 0; i < n; i++) {
        h = fnv_int(h, row[i]);
    }
    return h;
}

static uint32_t hash_bytes(const uint8_t *row, int n)
{
    uint32_t h = FNV_OFFSET;

    for (int i = 0; i < n; i++) {
        h = fnv_int(h, row[i]);
    }
    return h;
}

int main(int argc, char **argv)
{
    static sam_phoneme_t ph[MAX_PHONEMES];
    int pitch, mouth, throat, speed, singmode, inflection, count;
    FILE *f;

    if (argc < 2) {
        fprintf(stderr, "usage: dump_prepare <casefile>\n");
        return 2;
    }
    f = fopen(argv[1], "r");
    if (f == NULL) {
        fprintf(stderr, "cannot open %s\n", argv[1]);
        return 2;
    }

    while (fscanf(f, "%d %d %d %d %d %d %d", &pitch, &mouth, &throat, &speed,
                  &singmode, &inflection, &count) == 7) {
        sam_voice_t voice;
        sam_frames_t fr;

        if (count < 0 || count > MAX_PHONEMES) {
            fclose(f);
            return 3;
        }
        for (int i = 0; i < count; i++) {
            int p, l, s;
            if (fscanf(f, "%d %d %d", &p, &l, &s) != 3) {
                fclose(f);
                return 3;
            }
            ph[i].phoneme = (unsigned char)p;
            ph[i].length = (unsigned char)l;
            ph[i].stress = (unsigned char)s;
        }

        voice.pitch = (unsigned char)pitch;
        voice.mouth = (unsigned char)mouth;
        voice.throat = (unsigned char)throat;
        voice.speed = (unsigned char)speed;
        voice.singmode = singmode;
        voice.inflection = inflection;

        const int t = sam_prepare_frames(ph, count, &voice, &fr);
        if (t < 0) {
            fclose(f);
            return 4;
        }

        printf("%d %d %lu", t, fr.count,
               (unsigned long)hash_pitch(fr.pitch, fr.count));
        for (int r = 0; r < 3; r++) {
            printf(" %lu", (unsigned long)hash_bytes(fr.freq[r], fr.count));
        }
        for (int r = 0; r < 3; r++) {
            printf(" %lu", (unsigned long)hash_bytes(fr.ampl[r], fr.count));
        }
        printf(" %lu\n", (unsigned long)hash_bytes(fr.flags, fr.count));
        sam_frames_free(&fr);
    }
    fclose(f);
    return 0;
}
