/*
 * test_render.c - sam_render's contract around the rendering, on two
 * golden cases.
 *
 *   test_render <golden directory>
 *
 * verify_render.py checks the samples against the Python, but always
 * with the capacity the size query returned. This checks the rest of
 * sam_render.h: the query, a capacity between the rendered length and
 * the query's bound (rendered through the library's own buffer), one
 * byte short (SAM_E_SHORTBUF, and out untouched), and the argument
 * errors. It runs on every leg, so the Linux legs compare two golden
 * vectors byte for byte too. Stage R.4 (docs/c17/04-r4-renderer.md).
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "sam_render.h"

#define FILL 0xA5

static int failures;

static void check(int ok, const char *what)
{
    if (!ok) {
        printf("FAIL %s\n", what);
        failures++;
    }
}

static unsigned char *read_file(const char *dir, const char *name, long *len)
{
    char path[1024];
    FILE *f;
    unsigned char *buf;

    snprintf(path, sizeof path, "%s/%s", dir, name);
    f = fopen(path, "rb");
    if (f == NULL) {
        printf("cannot open %s\n", path);
        return NULL;
    }
    fseek(f, 0, SEEK_END);
    *len = ftell(f);
    fseek(f, 0, SEEK_SET);
    buf = malloc((size_t)*len);
    if (buf != NULL && fread(buf, 1, (size_t)*len, f) != (size_t)*len) {
        free(buf);
        buf = NULL;
    }
    fclose(f);
    return buf;
}

static int all(const unsigned char *p, int n, unsigned char v)
{
    for (int i = 0; i < n; i++) {
        if (p[i] != v) {
            return 0;
        }
    }
    return 1;
}

static void golden(const char *dir, const char *name,
                   const sam_phoneme_t *ph, int count, const sam_voice_t *voice)
{
    long len;
    unsigned char *want = read_file(dir, name, &len);
    if (want == NULL) {
        failures++;
        return;
    }

    const int need = sam_render(ph, count, voice, NULL, 0);
    printf("%s: query %d, golden %ld\n", name, need, len);
    check(need >= len, "the query is at least the rendered length");

    unsigned char *buf = malloc((size_t)need + 1);
    if (buf == NULL) {
        free(want);
        failures++;
        return;
    }

    /* The query's capacity: rendered in place. */
    memset(buf, FILL, (size_t)need + 1);
    int n = sam_render(ph, count, voice, buf, need);
    check(n == len && memcmp(buf, want, (size_t)len) == 0,
          "with the query's capacity, the golden samples");
    check(buf[need] == FILL, "nothing past the capacity");

    /* Exactly the rendered length: through the library's buffer. */
    memset(buf, FILL, (size_t)need + 1);
    n = sam_render(ph, count, voice, buf, (int)len);
    check(n == len && memcmp(buf, want, (size_t)len) == 0,
          "with the rendered length as capacity, the golden samples");
    check(all(buf + len, need + 1 - (int)len, FILL), "nothing past the rendered length");

    /* One short: SAM_E_SHORTBUF, and out untouched. */
    memset(buf, FILL, (size_t)need + 1);
    n = sam_render(ph, count, voice, buf, (int)len - 1);
    check(n == SAM_E_SHORTBUF, "one byte short is SAM_E_SHORTBUF");
    check(all(buf, need + 1, FILL), "and writes nothing");

    free(buf);
    free(want);
}

int main(int argc, char **argv)
{
    if (argc < 2) {
        printf("usage: test_render <golden directory>\n");
        return 2;
    }

    /* native/tests/golden/a_fast.in.json and hello_default.in.json */
    static const sam_phoneme_t a[] = { { 10, 6, 0 } };
    static const sam_phoneme_t hello[] = {
        { 36, 2, 0 }, { 10, 6, 0 }, { 19, 9, 0 }, { 52, 14, 4 }, { 20, 8, 4 }
    };
    const sam_voice_t a_voice = { 64, 128, 128, 10, 0, 50 };
    const sam_voice_t voice = { 64, 128, 128, 72, 0, 50 };

    golden(argv[1], "a_fast.pcm", a, 1, &a_voice);
    golden(argv[1], "hello_default.pcm", hello, 5, &voice);

    unsigned char out[16];
    sam_voice_t slow = voice;
    slow.speed = 0;
    static const sam_phoneme_t silent[] = { { 10, 0, 0 }, { 36, 0, 0 } };

    check(sam_render(NULL, 5, &voice, out, 16) == SAM_E_BADARG, "NULL phonemes");
    check(sam_render(hello, 0, &voice, out, 16) == SAM_E_BADARG, "count 0");
    check(sam_render(hello, 5, NULL, out, 16) == SAM_E_BADARG, "NULL voice");
    check(sam_render(hello, 5, &slow, out, 16) == SAM_E_BADSPEED, "speed 0");
    check(sam_render(silent, 2, &voice, NULL, 0) == 0, "no frames: query 0");
    check(sam_render(silent, 2, &voice, out, 16) == 0, "no frames: 0 samples");

    printf(failures ? "%d FAILED\n" : "all passed\n", failures);
    return failures ? 1 : 0;
}
