/*
 * dump_render.c - run sam_render over cases read from a file and print
 * the length and a checksum of each one's PCM.
 *
 * Case file format, one case per line, as dump_prepare.c reads it:
 *   pitch mouth throat speed singmode inflection count p1 l1 s1 p2 l2 s2 ...
 *
 * Output, one line per case: the sample count, or the negative SAM_E_*
 * code, then FNV-1a over the samples (0 when there are none).
 *
 * native/ has no namesake: verify_render.py loads the DLL through ctypes
 * instead. This one is for what ctypes cannot do: the same cases on the
 * Linux legs and under the sanitizers, and native/ against the rewrite
 * past what the Python can check (engine/tools/diff_render.py,
 * engine/tools/sanitize.py; docs/c17/04-r4-renderer.md). Stage R.4. A
 * host tool; not in the library.
 */

#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

#include "sam_render.h"

#define FNV_OFFSET 2166136261u
#define FNV_PRIME  16777619u
#define MAX_PHONEMES 4096

static uint32_t fnv_bytes(const unsigned char *p, int n)
{
    uint32_t h = FNV_OFFSET;

    for (int i = 0; i < n; i++) {
        h = (h ^ p[i]) * FNV_PRIME;
    }
    return h;
}

int main(int argc, char **argv)
{
    static sam_phoneme_t ph[MAX_PHONEMES];
    int pitch, mouth, throat, speed, singmode, inflection, count;
    FILE *f;

    if (argc < 2) {
        fprintf(stderr, "usage: dump_render <casefile>\n");
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

        /* As the addon calls it: ask for the size, then render. */
        int n = sam_render(ph, count, &voice, NULL, 0);
        uint32_t h = 0;
        if (n > 0) {
            unsigned char *buf = malloc((size_t)n);
            if (buf == NULL) {
                fclose(f);
                return 4;
            }
            n = sam_render(ph, count, &voice, buf, n);
            if (n > 0) {
                h = fnv_bytes(buf, n);
            }
            free(buf);
        }
        printf("%d %lu\n", n, (unsigned long)h);
    }
    fclose(f);
    return 0;
}
