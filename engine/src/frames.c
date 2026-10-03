/*
 * frames.c - phonemes and a voice turned into frames: one column of
 * pitch, formant frequencies, amplitudes and consonant flags for each
 * frame, with the transitions between phonemes interpolated.
 *
 * Stage R.3 of the C17 rewrite (docs/c17/03-r3-frames.md). Rewritten from
 * native/src/sam_frames.c, which ports create_frames(),
 * create_transitions() and prepare_frames() in
 * nvda-addon/synthDrivers/sam/renderer.py. SAM (1982, Don't Ask
 * Software, Mark Barton), by way of Stefan Macke's C and Christian
 * Schiffler's JavaScript. The inflection setting is this project's
 * addition to SAM. See NOTICE.md.
 */

#include <assert.h>
#include <float.h>
#include <limits.h>
#include <stdbool.h>
#include <stdlib.h>
#include <string.h>

#include "frames.h"
#include "voice.h"

/*
 * The inflection setting scales by inflection / 50.0, in Python's float,
 * and truncates with int() (scaled() below). C's double is the same IEEE
 * binary64 on every leg, and so is the rounding, as long as the compiler
 * evaluates double expressions in double. All four legs are x64 or
 * ARM64, where it does; this stops a build where it would not.
 */
#if defined(FLT_EVAL_METHOD) && FLT_EVAL_METHOD != 0 && FLT_EVAL_METHOD != 1
#error "frames.c needs double arithmetic evaluated in double (FLT_EVAL_METHOD 0 or 1)"
#endif

#define PHONEME_PERIOD    1   /* '.' : falling inflection */
#define PHONEME_QUESTION  2   /* '?' : rising inflection */

#define RISING_INFLECTION   255
#define FALLING_INFLECTION    1

/* add_inflection reaches back this many frames from the '.' or '?'. */
#define INFLECTION_REACH     30

/* Pitch values add_inflection steps over: 127 at the start, 255 after. */
#define PITCH_SKIP_FIRST    127
#define PITCH_SKIP_LATER    255

/* The six byte rows create_transitions() ramps besides the pitch. */
#define FRAME_BYTE_ROWS       6

/*
 * The most frames one utterance may have. A ramp runs up to two blend
 * lengths (2 * 255) past the last frame, and int must hold that index.
 */
#define FRAMES_MAX  (INT_MAX - 2 * UINT8_MAX - 1)

/* x & 0xFF in the Python, for any integer: conversion to an unsigned
 * type is modular in C, so this needs no two's-complement assumption. */
static uint8_t low_byte(int64_t v)
{
    return (uint8_t)(uint64_t)v;
}

/*
 * int(x * scale) in the Python, where scale is inflection / 50.0.
 * Truncates toward zero as int() does. A product outside int's range
 * would make the conversion undefined, so it saturates. That needs an
 * inflection beyond about +-431 million (x is at most 249, from
 * sam_stress_pitch, or the rising inflection's 255, which is clamped to
 * 255 afterwards anyway), far outside sam_render.h's 0-100. Only there
 * does the result differ from the Python's.
 */
static int scaled(int x, double scale)
{
    const double v = (double)x * scale;

    if (v >= (double)INT_MAX) {
        return INT_MAX;
    }
    if (v <= (double)INT_MIN) {
        return INT_MIN;
    }
    return (int)v;
}

/* Q1 in quirks.h: a computed pitch goes into the row, saturating. */
static sam_pitch_t to_pitch(int64_t v)
{
    if (v > INT32_MAX) {
        return INT32_MAX;
    }
    if (v < INT32_MIN) {
        return INT32_MIN;
    }
    return (sam_pitch_t)v;
}

/* ------------------------------------------------------------------ */
/* create_frames                                                       */

/*
 * Add inflection to the last INFLECTION_REACH frames before frame n: a
 * '.' or '?' bends the pitch of what came before it.
 *
 * add_inflection() in the Python takes the position to stop at and the
 * row; the position is always the row's length so far, so here it is
 * one argument. The row holds bytes at this point (create_frames writes
 * nothing else), and this is SAM's byte arithmetic.
 */
static void add_inflection(sam_pitch_t *pitch, int n, int inflection)
{
    int pos = (n < INFLECTION_REACH) ? 0 : n - INFLECTION_REACH;

    while (pos < n && pitch[pos] == PITCH_SKIP_FIRST) {
        pos++;
    }
    while (pos < n) {
        pitch[pos] = low_byte((int64_t)pitch[pos] + inflection);
        pos++;
        while (pos < n && pitch[pos] == PITCH_SKIP_LATER) {
            pos++;
        }
    }
}

/*
 * One phoneme's table values, the same in each of its frames.
 *
 * A phoneme past the tables is outside what the Python defines: it
 * raises IndexError reading the frequency row. sam_render() does not
 * reject one, and native/ gave it all zeros, so the rewrite does too;
 * the parser never emits one.
 */
typedef struct {
    uint8_t freq[3], ampl[3], flags;
} phoneme_values_t;

static phoneme_values_t phoneme_values(const sam_freqdata_t *fd, int p)
{
    phoneme_values_t v = { { 0, 0, 0 }, { 0, 0, 0 }, 0 };

    if (p < SAM_PHONEME_COUNT) {
        v.freq[0] = fd->f1[p];
        v.freq[1] = fd->f2[p];
        v.freq[2] = fd->f3[p];
        v.ampl[0] = sam_ampl1[p];
        v.ampl[1] = sam_ampl2[p];
        v.ampl[2] = sam_ampl3[p];
        v.flags = sam_sampled_consonant_flags[p];
    }
    return v;
}

/*
 * Each phoneme becomes `length` identical frames, its pitch raised by
 * its stress. create_frames() in renderer.py.
 */
static void create_frames(sam_frames_t *fr, const sam_phoneme_t *phonemes,
                          int count, const sam_freqdata_t *fd,
                          uint8_t base_pitch, double scale)
{
    int rising = 0;
    int falling = 0;
    int n = 0;

    if (scale > 0) {
        rising = scaled(RISING_INFLECTION, scale);
        falling = scaled(FALLING_INFLECTION, scale);
    }
    rising = (rising > UINT8_MAX) ? UINT8_MAX : rising;
    falling = (falling > UINT8_MAX) ? UINT8_MAX : falling;

    for (int i = 0; i < count; i++) {
        const sam_phoneme_t *ph = &phonemes[i];
        const phoneme_values_t v = phoneme_values(fd, ph->phoneme);
        const int stress = (ph->stress < SAM_STRESS_LEVELS)
                         ? sam_stress_pitch[ph->stress] : 0;
        const sam_pitch_t pitch =
            low_byte((int64_t)base_pitch + scaled(stress, scale));

        if (ph->phoneme == PHONEME_PERIOD) {
            add_inflection(fr->pitch, n, falling);
        } else if (ph->phoneme == PHONEME_QUESTION) {
            add_inflection(fr->pitch, n, rising);
        }

        for (int k = 0; k < ph->length; k++, n++) {
            fr->pitch[n] = pitch;
            for (int f = 0; f < 3; f++) {
                fr->freq[f][n] = v.freq[f];
                fr->ampl[f][n] = v.ampl[f];
            }
            fr->flags[n] = v.flags;
        }
    }
    assert(n == fr->count);
}

/* ------------------------------------------------------------------ */
/* create_transitions                                                  */

/*
 * One row of frames, as interpolate() sees it: the pitch row or one of
 * the six byte rows.
 */
typedef struct {
    sam_pitch_t *wide;   /* the pitch row, or NULL */
    uint8_t     *byte;   /* a formant row, or NULL */
    int          n;
} row_t;

/* read() in the Python: 0 outside the row, on either side. */
static int64_t row_read(row_t r, int i)
{
    if (i < 0 || i >= r.n) {
        return 0;
    }
    return r.wide ? r.wide[i] : r.byte[i];
}

/*
 * `if frame < len(t): t[frame] = val` in the Python, negative frames
 * included: Q2 in quirks.h.
 *
 * A byte row never receives a value outside a byte. Section 3.2 of the
 * chapter proves it: every value interpolate() writes into a formant
 * or amplitude row lies between 0 and the row's largest value, so the
 * rows stay what create_frames() wrote, bytes.
 */
static void row_write(row_t r, int i, int64_t v)
{
    if (i >= r.n) {
        return;
    }
    i = sam_py_index(i, r.n);
    if (i < 0) {
        return;
    }
    if (r.wide) {
        r.wide[i] = to_pitch(v);
    } else {
        assert(v >= 0 && v <= UINT8_MAX);
        r.byte[i] = (uint8_t)v;
    }
}

/*
 * Step `change` across `width` frames, starting after `frame`: each
 * frame gets the one before it plus change / width, and the remainder
 * is spread with an error term, Bresenham's way. interpolate() in the
 * Python, which is SAM's.
 *
 * The Python's int(change / width) is C's change / width: both truncate
 * toward zero, and the float quotient cannot cross an integer while
 * |change| < 2^53 (chapter section 3.2). The step reads the frame just
 * written, so each value builds on the last; where that frame was
 * outside the row the read gives 0 and the ramp starts over from 0.
 */
static void interpolate(row_t r, int width, int frame, int64_t change)
{
    if (width == 0) {
        return;
    }

    const bool falling = change < 0;
    const int64_t step = change / width;
    const int64_t remainder = (falling ? -change : change) % width;
    int64_t error = 0;

    for (int k = 1; k < width; k++) {
        int64_t val = row_read(r, frame) + step;

        error += remainder;
        if (error >= width) {
            error -= width;
            if (falling) {
                val--;
            } else if (val != 0) {
                /*
                 * A rising ramp never lifts a 0. `elif val:` in the
                 * Python. Reached: section 3.2 of the chapter.
                 */
                val++;
            }
        }
        frame++;
        row_write(r, frame, val);
    }
}

/* A blend table entry, 0 for a phoneme past the table, as the Python. */
static int blend(const uint8_t *table, int phoneme)
{
    return (phoneme < SAM_PHONEME_COUNT) ? table[phoneme] : 0;
}

/*
 * Smooth each boundary between two phonemes: the last out_blend frames
 * of one and the first in_blend frames of the next ramp from one to the
 * other. Pitch ramps from the middle of one phoneme to the middle of
 * the next instead. create_transitions() in renderer.py.
 */
static void create_transitions(sam_frames_t *fr, const sam_phoneme_t *phonemes,
                               int count)
{
    const int n = fr->count;
    const row_t pitch = { fr->pitch, NULL, n };
    row_t rows[FRAME_BYTE_ROWS];
    int boundary = 0;

    for (int f = 0; f < 3; f++) {
        rows[f] = (row_t){ NULL, fr->freq[f], n };
        rows[3 + f] = (row_t){ NULL, fr->ampl[f], n };
    }

    for (int i = 0; i + 1 < count; i++) {
        const int p = phonemes[i].phoneme;
        const int next = phonemes[i + 1].phoneme;
        const int rank = blend(sam_blend_rank, p);
        const int next_rank = blend(sam_blend_rank, next);
        int out_blend, in_blend;

        /* The lower rank is the stronger phoneme, and sets the blend. */
        if (rank == next_rank) {
            out_blend = blend(sam_out_blend_length, p);
            in_blend = blend(sam_out_blend_length, next);
        } else if (rank < next_rank) {
            out_blend = blend(sam_in_blend_length, next);
            in_blend = blend(sam_out_blend_length, next);
        } else {
            out_blend = blend(sam_out_blend_length, p);
            in_blend = blend(sam_in_blend_length, p);
        }

        boundary += phonemes[i].length;
        const int trans_end = boundary + in_blend;
        const int trans_start = boundary - out_blend;
        const int trans_length = out_blend + in_blend;

        /*
         * SAM's sign test on a byte: no transition when bit 7 of
         * trans_length - 2 is set. The unsigned conversion gives the
         * two's-complement bits Python's & sees for any int.
         */
        if (((unsigned)(trans_length - 2) & 0x80u) != 0) {
            continue;
        }

        const int cur_width = phonemes[i].length >> 1;
        const int next_width = phonemes[i + 1].length >> 1;
        const int pitch_end = boundary + next_width;
        const int pitch_start = boundary - cur_width;

        /* The change is measured middle to middle, but the ramp starts
         * at trans_start, as in the Python. */
        if (pitch_end < n && pitch_start >= 0) {
            interpolate(pitch, cur_width + next_width, trans_start,
                        (int64_t)fr->pitch[pitch_end] - fr->pitch[pitch_start]);
        }
        for (int r = 0; r < FRAME_BYTE_ROWS; r++) {
            interpolate(rows[r], trans_length, trans_start,
                        row_read(rows[r], trans_end) - row_read(rows[r], trans_start));
        }
    }

    /*
     * The Python returns boundary plus the last phoneme's length as the
     * frame count: the sum of the lengths, which is the row length too.
     * native/ kept both numbers; here they are one.
     */
    assert(count == 0 || boundary + phonemes[count - 1].length == n);
}

/* ------------------------------------------------------------------ */
/* prepare_frames                                                      */

void sam_frames_free(sam_frames_t *fr)
{
    free(fr->pitch);
    memset(fr, 0, sizeof *fr);
}

/* One block: the pitch row, then seven byte rows (F1..F3, A1..A3, flags). */
static int frames_alloc(sam_frames_t *fr, int n)
{
    memset(fr, 0, sizeof *fr);
    if (n == 0) {
        return 0;
    }

    unsigned char *block = calloc((size_t)n, sizeof(sam_pitch_t) + 7);
    if (block == NULL) {
        return -1;
    }
    uint8_t *bytes = block + (size_t)n * sizeof(sam_pitch_t);

    fr->pitch = (sam_pitch_t *)(void *)block;
    for (int f = 0; f < 3; f++) {
        fr->freq[f] = bytes + (size_t)n * (size_t)f;
        fr->ampl[f] = bytes + (size_t)n * (size_t)(3 + f);
    }
    fr->flags = bytes + (size_t)n * 6;
    fr->count = n;
    return 0;
}

int sam_prepare_frames(const sam_phoneme_t *phonemes, int count,
                       const sam_voice_t *voice, sam_frames_t *fr)
{
    const double scale = (double)voice->inflection / 50.0;
    sam_freqdata_t fd;
    int64_t total = 0;

    for (int i = 0; i < count; i++) {
        total += phonemes[i].length;
    }
    if (total > FRAMES_MAX || frames_alloc(fr, (int)total) != 0) {
        memset(fr, 0, sizeof *fr);
        return -1;
    }

    sam_set_mouth_throat(voice->mouth, voice->throat, &fd);
    create_frames(fr, phonemes, count, &fd, voice->pitch, scale);
    create_transitions(fr, phonemes, count);

    if (!voice->singmode) {
        /* Take half of F1 off the pitch, scaled by the inflection: the
         * pitch row becomes bytes again here, and only here. */
        for (int i = 0; i < fr->count; i++) {
            const int adjust = scaled(fr->freq[0][i] >> 1, scale);
            fr->pitch[i] = low_byte((int64_t)fr->pitch[i] - adjust);
        }
    }

    /*
     * Amplitude, from the table's 0..15 steps to the level the mixer
     * uses. A value of 16 or more is left as it is, as in the Python;
     * 494 of verify_prepare.py's random cases have one (A3 up to 19).
     * No value is negative (chapter section 3.2), so native/'s wrap of
     * a negative index into the table is gone.
     */
    for (int f = 0; f < 3; f++) {
        for (int i = 0; i < fr->count; i++) {
            const uint8_t a = fr->ampl[f][i];
            if (a < SAM_AMPLITUDE_LEVELS) {
                fr->ampl[f][i] = sam_amplitude_rescale[a];
            }
        }
    }
    return fr->count;
}
