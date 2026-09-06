/*
 * sam_frames.c - frame preparation for the native renderer.
 *
 * Ported from nvda-addon/synthDrivers/sam/renderer.py. Every function
 * here is checked against its Python counterpart by the harnesses in
 * native/tools; see docs/c-engine-port.md.
 */

#include <stdlib.h>
#include <string.h>

#include "sam_internal.h"

#define SAM_PHONEME_PERIOD    1
#define SAM_PHONEME_QUESTION  2

#define RISING_INFLECTION   255
#define FALLING_INFLECTION    1

/*
 * ((factor * initial_frequency) >> 8 & 0xFF) << 1
 *
 * Kept in int arithmetic to mirror Python and JavaScript exactly. The
 * mask happens before the shift, so the result can exceed a byte.
 */
static uint16_t trans(uint8_t factor, uint8_t initial_frequency)
{
    return (uint16_t)(((((int)factor * (int)initial_frequency) >> 8) & 0xFF) << 1);
}

void sam_set_mouth_throat(uint8_t mouth, uint8_t throat, sam_freqdata_t *out)
{
    int pos;

    for (pos = 0; pos < SAM_PHONEME_COUNT; pos++) {
        out->f1[pos] = sam_freq1[pos];
        out->f2[pos] = sam_freq2[pos];
        out->f3[pos] = sam_freq3[pos];
    }

    /* Recalculate formant frequencies 5..29 for mouth (F1) and throat (F2). */
    for (pos = 5; pos < 30; pos++) {
        out->f1[pos] = trans(mouth, (uint8_t)out->f1[pos]);
        out->f2[pos] = trans(throat, (uint8_t)out->f2[pos]);
    }

    /* And again for 48..53. */
    for (pos = 48; pos < 54; pos++) {
        out->f1[pos] = trans(mouth, (uint8_t)out->f1[pos]);
        out->f2[pos] = trans(throat, (uint8_t)out->f2[pos]);
    }
}

/* ------------------------------------------------------------------ */

int sam_frames_alloc(sam_frames_t *fr, int total_frames)
{
    int i;

    memset(fr, 0, sizeof(*fr));
    if (total_frames <= 0) {
        return 0;
    }

    /* One block, carved up: seven int rows plus the flag row. */
    fr->pitches = (int *)calloc((size_t)total_frames * 7, sizeof(int));
    if (fr->pitches == NULL) {
        return -1;
    }
    for (i = 0; i < 3; i++) {
        fr->freq[i] = fr->pitches + (size_t)total_frames * (1 + i);
        fr->ampl[i] = fr->pitches + (size_t)total_frames * (4 + i);
    }
    fr->flags = (uint8_t *)calloc((size_t)total_frames, 1);
    if (fr->flags == NULL) {
        free(fr->pitches);
        fr->pitches = NULL;
        return -1;
    }
    fr->capacity = total_frames;
    return 0;
}

void sam_frames_free(sam_frames_t *fr)
{
    free(fr->pitches);
    free(fr->flags);
    memset(fr, 0, sizeof(*fr));
}

/*
 * Create a rising or falling inflection 30 frames prior to index.
 *
 * `n` is how much of the pitch row is populated so far: create_frames
 * calls this while the row is still growing, and Python's bounds checks
 * are against the current length, not the capacity.
 */
static void add_inflection(int inflection, int end, int *pitches, int n)
{
    int pos = (end < 30) ? 0 : end - 30;

    /* Skip invalid pitch values (127). */
    while (pos < n && pitches[pos] == 127) {
        pos++;
    }

    while (pos != end && pos < n) {
        int a = pitches[pos] + inflection;
        pitches[pos] = a & 0xFF;

        pos++;
        while (pos != end && pos < n && pitches[pos] == 255) {
            pos++;
        }
    }
}

void sam_create_frames(uint8_t pitch, const sam_phoneme_t *phonemes, int count,
                       const sam_freqdata_t *fd, int inflection,
                       sam_frames_t *fr)
{
    /* Scale inflection: 0 monotone, 50 normal, 100 dramatic. */
    const double scale = (double)inflection / 50.0;
    int rising = 0;
    int falling = 0;
    int i, k, n = 0;

    if (scale > 0) {
        rising = (int)(RISING_INFLECTION * scale);
        falling = (int)(FALLING_INFLECTION * scale);
    }
    if (rising < 0)   rising = 0;
    if (rising > 255) rising = 255;
    if (falling < 0)   falling = 0;
    if (falling > 255) falling = 255;

    for (i = 0; i < count; i++) {
        const int phoneme = phonemes[i].phoneme;
        const int stress = phonemes[i].stress;
        const int frames = phonemes[i].length;
        int phase1;
        int f1, f2, f3, a1, a2, a3, scf;

        if (phoneme == SAM_PHONEME_PERIOD) {
            add_inflection(falling, n, fr->pitches, n);
        } else if (phoneme == SAM_PHONEME_QUESTION) {
            add_inflection(rising, n, fr->pitches, n);
        }

        /* More stress means higher pitch, scaled by the inflection amount. */
        phase1 = (stress < 10) ? sam_stress_pitch[stress] : 0;
        phase1 = (int)(phase1 * scale);

        /*
         * The parser only emits phonemes below SAM_PHONEME_COUNT. Python
         * would raise on an out-of-range index into the frequency rows;
         * guarding here keeps identical behaviour on valid input without
         * reading out of bounds on invalid input.
         */
        if (phoneme >= 0 && phoneme < SAM_PHONEME_COUNT) {
            f1 = fd->f1[phoneme];
            f2 = fd->f2[phoneme];
            f3 = fd->f3[phoneme];
            a1 = sam_ampl1[phoneme];
            a2 = sam_ampl2[phoneme];
            a3 = sam_ampl3[phoneme];
            scf = sam_sampled_consonant_flags[phoneme];
        } else {
            f1 = f2 = f3 = a1 = a2 = a3 = scf = 0;
        }

        for (k = 0; k < frames && n < fr->capacity; k++, n++) {
            fr->freq[0][n] = f1;
            fr->freq[1][n] = f2;
            fr->freq[2][n] = f3;
            fr->ampl[0][n] = a1;
            fr->ampl[1][n] = a2;
            fr->ampl[2][n] = a3;
            fr->flags[n] = (uint8_t)scf;
            fr->pitches[n] = ((int)pitch + phase1) & 0xFF;
        }
    }

    fr->count = n;
}

/* ------------------------------------------------------------------ */

static int read_table(int *const *tables, int n, int table, int pos)
{
    if (pos < 0 || pos >= n) {
        return 0;
    }
    return tables[table][pos];
}

/* Linearly interpolate values across `width` frames. */
static void interpolate(int *const *tables, int n, int width, int table,
                        int frame, int change)
{
    int sign, remainder, div, error, pos;

    if (width == 0) {
        return;
    }

    sign = (change < 0);
    remainder = (change < 0 ? -change : change) % width;
    /*
     * Python computes int(change / width): true division truncated toward
     * zero. C integer division truncates toward zero too (C99 6.5.5), so
     * these agree, including for negative change.
     */
    div = change / width;

    error = 0;
    pos = width;

    while (pos > 1) {
        int val;
        pos--;
        val = read_table(tables, n, table, frame) + div;
        error += remainder;
        if (error >= width) {
            error -= width;
            if (sign) {
                val -= 1;
            } else if (val) {   /* Python's `elif val:` - nonzero, not >0 */
                val += 1;
            }
        }

        frame++;
        if (frame < n) {
            /*
             * trans_start is boundary - out_blend_frames and goes negative
             * when a phoneme is shorter than the blend leading into it, so
             * `frame` can be negative here.
             *
             * Python guards the read (read() returns 0 for pos < 0) but not
             * this write: `if frame < len(t): t[frame] = val` with a
             * negative frame is Python negative indexing, which writes near
             * the END of the row. That is odd, but it is the behaviour that
             * produced the golden vectors, so reproduce it exactly rather
             * than "fixing" it and changing the voice. Below -n Python
             * raises IndexError; skip instead of writing out of bounds.
             */
            const int idx = (frame < 0) ? frame + n : frame;
            if (idx >= 0 && idx < n) {
                tables[table][idx] = val;
            }
        }
    }
}

int sam_create_transitions(sam_frames_t *fr, const sam_phoneme_t *phonemes,
                           int count)
{
    int *tables[7];
    const int n = fr->count;
    int boundary = 0;
    int pos;

    tables[0] = fr->pitches;
    tables[1] = fr->freq[0];
    tables[2] = fr->freq[1];
    tables[3] = fr->freq[2];
    tables[4] = fr->ampl[0];
    tables[5] = fr->ampl[1];
    tables[6] = fr->ampl[2];

    for (pos = 0; pos < count - 1; pos++) {
        const int phoneme = phonemes[pos].phoneme;
        const int next_phoneme = phonemes[pos + 1].phoneme;
        int next_rank, rank;
        int out_blend_frames, in_blend_frames;
        int trans_end, trans_start, trans_length;

        next_rank = (next_phoneme < SAM_PHONEME_COUNT) ? sam_blend_rank[next_phoneme] : 0;
        rank = (phoneme < SAM_PHONEME_COUNT) ? sam_blend_rank[phoneme] : 0;

        /* Lower rank is stronger. */
        if (rank == next_rank) {
            out_blend_frames = (phoneme < SAM_PHONEME_COUNT) ? sam_out_blend_length[phoneme] : 0;
            in_blend_frames = (next_phoneme < SAM_PHONEME_COUNT) ? sam_out_blend_length[next_phoneme] : 0;
        } else if (rank < next_rank) {
            out_blend_frames = (next_phoneme < SAM_PHONEME_COUNT) ? sam_in_blend_length[next_phoneme] : 0;
            in_blend_frames = (next_phoneme < SAM_PHONEME_COUNT) ? sam_out_blend_length[next_phoneme] : 0;
        } else {
            out_blend_frames = (phoneme < SAM_PHONEME_COUNT) ? sam_out_blend_length[phoneme] : 0;
            in_blend_frames = (phoneme < SAM_PHONEME_COUNT) ? sam_in_blend_length[phoneme] : 0;
        }

        boundary += phonemes[pos].length;
        trans_end = boundary + in_blend_frames;
        trans_start = boundary - out_blend_frames;
        trans_length = out_blend_frames + in_blend_frames;

        if (((trans_length - 2) & 128) == 0) {
            /* Pitch interpolates from the middle of one phoneme to the next. */
            const int cur_width = phonemes[pos].length >> 1;
            const int next_width = phonemes[pos + 1].length >> 1;
            const int pitch_end = boundary + next_width;
            const int pitch_start = boundary - cur_width;
            int table;

            if (pitch_end < n && pitch_start >= 0) {
                const int pitch_diff = fr->pitches[pitch_end] - fr->pitches[pitch_start];
                interpolate(tables, n, cur_width + next_width, 0, trans_start, pitch_diff);
            }

            for (table = 1; table < 7; table++) {
                const int value = read_table(tables, n, table, trans_end)
                                - read_table(tables, n, table, trans_start);
                interpolate(tables, n, trans_length, table, trans_start, value);
            }
        }
    }

    /* Add the length of the last phoneme. */
    if (count > 0) {
        return boundary + phonemes[count - 1].length;
    }
    return boundary;
}

/* ------------------------------------------------------------------ */

int sam_prepare_frames(const sam_phoneme_t *phonemes, int count,
                       const sam_voice_t *voice, sam_frames_t *fr)
{
    sam_freqdata_t fd;
    int total_frames = 0;
    int t, i;

    for (i = 0; i < count; i++) {
        total_frames += phonemes[i].length;
    }
    if (sam_frames_alloc(fr, total_frames) != 0) {
        return -1;
    }

    sam_set_mouth_throat(voice->mouth, voice->throat, &fd);
    sam_create_frames(voice->pitch, phonemes, count, &fd, voice->inflection, fr);
    t = sam_create_transitions(fr, phonemes, count);

    if (!voice->singmode) {
        /* Subtract half the F1 frequency from the pitch contour for variety. */
        const double scale = (double)voice->inflection / 50.0;
        for (i = 0; i < fr->count; i++) {
            const int f1_adjust = (int)((fr->freq[0][i] >> 1) * scale);
            fr->pitches[i] = (fr->pitches[i] - f1_adjust) & 0xFF;
        }
    }

    /* Rescale amplitude from decibels to a linear scale. */
    for (i = fr->count - 1; i >= 0; i--) {
        int row;
        for (row = 0; row < 3; row++) {
            const int v = fr->ampl[row][i];
            /*
             * Python guards this with `if v < len(AMPLITUDE_RESCALE)` and
             * no lower bound, so a negative value there indexes from the
             * end of the list rather than being skipped. interpolate()
             * writes unmasked and can go negative, so reproduce that
             * wrap rather than diverging. Below -16 Python would raise;
             * leave the value alone instead of reading out of bounds.
             */
            if (v < 16) {
                const int idx = (v < 0) ? v + 16 : v;
                if (idx >= 0 && idx < 16) {
                    fr->ampl[row][i] = sam_amplitude_rescale[idx];
                }
            }
        }
    }

    fr->total = t;
    return t;
}
