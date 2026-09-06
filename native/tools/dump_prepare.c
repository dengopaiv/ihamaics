/*
 * dump_prepare.c - run sam_prepare_frames over cases read from a file and
 * print per-row checksums, so verify_prepare.py can diff every row
 * against Python without moving millions of numbers.
 *
 * Case file format, one case per line:
 *   pitch mouth throat speed singmode inflection count p1 l1 s1 p2 l2 s2 ...
 *
 * Host tool, not shipped in the DLL.
 */
#include <stdio.h>
#include <stdlib.h>
#include "sam_internal.h"

static uint32_t fnv_int(uint32_t h, int v)
{
    /* Hash as 32-bit two's complement, little-endian, so Python can match. */
    uint32_t u = (uint32_t)v;
    int b;
    for (b = 0; b < 4; b++) {
        h ^= (u >> (8 * b)) & 0xFF;
        h *= 16777619u;
    }
    return h;
}

static uint32_t hash_int_row(const int *row, int n)
{
    uint32_t h = 2166136261u;
    int i;
    for (i = 0; i < n; i++) h = fnv_int(h, row[i]);
    return h;
}

static uint32_t hash_u8_row(const uint8_t *row, int n)
{
    uint32_t h = 2166136261u;
    int i;
    for (i = 0; i < n; i++) h = fnv_int(h, (int)row[i]);
    return h;
}

int main(int argc, char **argv)
{
    FILE *f;
    sam_phoneme_t ph[4096];
    int pitch, mouth, throat, speed, singmode, inflection, count;

    if (argc < 2) { fprintf(stderr, "usage: dump_prepare <casefile>\n"); return 2; }
    f = fopen(argv[1], "r");
    if (!f) { fprintf(stderr, "cannot open %s\n", argv[1]); return 2; }

    while (fscanf(f, "%d %d %d %d %d %d %d",
                  &pitch, &mouth, &throat, &speed, &singmode, &inflection, &count) == 7) {
        sam_voice_t voice;
        sam_frames_t fr;
        int i, t;

        if (count < 0 || count > (int)(sizeof ph / sizeof ph[0])) { fclose(f); return 3; }
        for (i = 0; i < count; i++) {
            int p, l, s;
            if (fscanf(f, "%d %d %d", &p, &l, &s) != 3) { fclose(f); return 3; }
            ph[i].phoneme = (unsigned char)p;
            ph[i].length  = (unsigned char)l;
            ph[i].stress  = (unsigned char)s;
        }

        voice.pitch = (unsigned char)pitch;
        voice.mouth = (unsigned char)mouth;
        voice.throat = (unsigned char)throat;
        voice.speed = (unsigned char)speed;
        voice.singmode = singmode;
        voice.inflection = inflection;

        t = sam_prepare_frames(ph, count, &voice, &fr);
        if (t < 0) { fclose(f); return 4; }

        printf("%d %d %u %u %u %u %u %u %u %u\n",
               t, fr.count,
               (unsigned)hash_int_row(fr.pitches, fr.count),
               (unsigned)hash_int_row(fr.freq[0], fr.count),
               (unsigned)hash_int_row(fr.freq[1], fr.count),
               (unsigned)hash_int_row(fr.freq[2], fr.count),
               (unsigned)hash_int_row(fr.ampl[0], fr.count),
               (unsigned)hash_int_row(fr.ampl[1], fr.count),
               (unsigned)hash_int_row(fr.ampl[2], fr.count),
               (unsigned)hash_u8_row(fr.flags, fr.count));
        sam_frames_free(&fr);
    }
    fclose(f);
    return 0;
}
