/*
 * bench_render.c - time sam_render() called directly, with no ctypes in
 * the way. Driven by native/tools/measure.py, which also times the same
 * call through ctypes, the way the NVDA driver pays for it.
 *
 * stdin:  pitch mouth throat speed singmode inflection reps
 *         count
 *         phoneme length stress     (count lines)
 * stdout: samples min_ns median_ns
 *
 * Renders once untimed to size the buffer and warm the caches, then reps
 * times timed. Timing uses timespec_get(), the C11 clock, so the same
 * file builds against native/ and against the C17 rewrite.
 */

#include <stdio.h>
#include <stdlib.h>
#include <time.h>

#include "sam_render.h"

static int cmp_ll(const void *a, const void *b)
{
    const long long x = *(const long long *)a, y = *(const long long *)b;
    return (x > y) - (x < y);
}

static long long now_ns(void)
{
    struct timespec ts;
    timespec_get(&ts, TIME_UTC);
    return (long long)ts.tv_sec * 1000000000LL + ts.tv_nsec;
}

int main(void)
{
    int pitch, mouth, throat, speed, singmode, inflection, reps, count, i;
    sam_voice_t voice;
    sam_phoneme_t *ph;
    unsigned char *out;
    long long *t;
    int cap, n = 0;

    if (scanf("%d %d %d %d %d %d %d", &pitch, &mouth, &throat, &speed,
              &singmode, &inflection, &reps) != 7 || reps < 1 ||
        scanf("%d", &count) != 1 || count < 1) {
        return 2;
    }
    ph = malloc(sizeof *ph * (size_t)count);
    t = malloc(sizeof *t * (size_t)reps);
    if (!ph || !t) {
        return 4;
    }
    for (i = 0; i < count; i++) {
        int p, l, s;
        if (scanf("%d %d %d", &p, &l, &s) != 3) {
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

    cap = sam_render(ph, count, &voice, NULL, 0);
    if (cap <= 0 || !(out = malloc((size_t)cap))) {
        return 4;
    }
    n = sam_render(ph, count, &voice, out, cap);
    if (n < 0) {
        return 4;
    }
    for (i = 0; i < reps; i++) {
        const long long t0 = now_ns();
        sam_render(ph, count, &voice, out, cap);
        t[i] = now_ns() - t0;
    }
    qsort(t, (size_t)reps, sizeof *t, cmp_ll);
    printf("%d %lld %lld\n", n, t[0], t[reps / 2]);
    free(out);
    free(t);
    free(ph);
    return 0;
}
