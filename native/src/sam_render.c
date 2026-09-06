/*
 * sam_render.c - native SAM renderer.
 *
 * Ported from nvda-addon/synthDrivers/sam/renderer.py and checked against
 * it by native/tools/verify_render.py and the golden vectors in
 * native/tests/golden. See docs/c-engine-port.md.
 */

#include <stdlib.h>
#include <string.h>

#include "sam_internal.h"

/* ------------------------------------------------------------------ */
/* Output buffer                                                       */

/*
 * bufferpos accumulates timetable increments and is divided by 50 to get
 * a sample index, so it runs 50x the buffer length. int64 keeps that
 * exact for even absurd frame counts; Python uses unbounded integers.
 */
typedef struct {
    uint8_t *buffer;
    int64_t  size;
    int64_t  bufferpos;
    int      old_timetable_index;
} sam_output_t;

static void output_write_array(sam_output_t *o, int index, const int *values)
{
    int64_t pos;
    int k;

    o->bufferpos += sam_time_table[o->old_timetable_index][index];
    pos = o->bufferpos / 50;
    if (pos > o->size) {
        /* Python raises RuntimeError("Buffer overflow") here. */
        return;
    }
    o->old_timetable_index = index;

    /* Write a little bit in advance. */
    for (k = 0; k < 5; k++) {
        if (pos + k < o->size) {
            o->buffer[pos + k] = (uint8_t)values[k];
        }
    }
}

/* Scale by 16 and write five times. */
static void output_write(sam_output_t *o, int index, int value)
{
    const int scaled = (value & 15) * 16;
    int five[5];
    five[0] = five[1] = five[2] = five[3] = five[4] = scaled;
    output_write_array(o, index, five);
}

/* ------------------------------------------------------------------ */
/* Sampled consonants                                                  */

static void render_sample_inner(sam_output_t *o, int sample_page, int off,
                                int index1, int value1, int index0, int value0)
{
    int sample_idx = sample_page + off;
    int sample, bit;

    if (sample_idx < 0 || sample_idx >= SAM_SAMPLE_TABLE_SIZE) {
        return;
    }
    sample = sam_sample_table[sample_idx];

    for (bit = 8; bit > 0; bit--) {
        if ((sample & 128) != 0) {
            output_write(o, index1, value1);
        } else {
            output_write(o, index0, value0);
        }
        sample = (sample << 1) & 0xFF;
    }
}

static int render_sample(sam_output_t *o, int last_sample_offset,
                         int consonant_flag, int pitch)
{
    /* Mask the low three bits and subtract 1: this is -1 when they are 0. */
    const int kind = (consonant_flag & 7) - 1;
    const int sample_page = (kind * 256) & 0xFFFF;
    int off = consonant_flag & 248;

    if (off == 0) {
        /* Voiced phoneme: Z*, ZH, V*, DH */
        int phase1 = ((pitch >> 4) ^ 255) & 0xFF;
        off = last_sample_offset & 0xFF;
        for (;;) {
            render_sample_inner(o, sample_page, off, 3, 26, 4, 6);
            off = (off + 1) & 0xFF;
            phase1 = (phase1 + 1) & 0xFF;
            if (phase1 == 0) {
                break;
            }
        }
        return off;
    }

    /* Unvoiced. */
    off = (off ^ 255) & 0xFF;
    {
        /*
         * Python indexes SAMPLED_CONSONANT_VALUES0[kind] guarded only by
         * `kind < len(...)`, so kind == -1 selects the LAST entry via
         * negative indexing rather than being rejected. Reproduce that.
         */
        int value0 = 0;
        const int n = 5;   /* len(SAMPLED_CONSONANT_VALUES0) */
        if (kind < n) {
            const int idx = (kind < 0) ? kind + n : kind;
            if (idx >= 0 && idx < n) {
                value0 = sam_sampled_consonant_values0[idx] & 0xFF;
            }
        }

        for (;;) {
            render_sample_inner(o, sample_page, off, 2, 5, 1, value0);
            off = (off + 1) & 0xFF;
            if (off == 0) {
                break;
            }
        }
    }

    return last_sample_offset;
}

/* ------------------------------------------------------------------ */
/* Main loop                                                           */

static void process_frames(sam_output_t *o, int frame_count, int speed,
                           const sam_frames_t *fr)
{
    const int n = fr->count;
    const int *pitches = fr->pitches;
    int speedcounter = speed;
    int phase1 = 0, phase2 = 0, phase3 = 0;
    int last_sample_offset = 0;
    int pos = 0;
    int glottal_pulse, mem38;

    if (n <= 0) {
        return;
    }

    glottal_pulse = pitches[0];
    /* int() truncates toward zero, and so does the C cast. */
    mem38 = (int)(glottal_pulse * 0.75);

    while (frame_count > 0) {
        int flags;
        if (pos >= n) {
            break;
        }
        flags = fr->flags[pos];

        /* Unvoiced sampled phoneme? */
        if ((flags & 248) != 0) {
            const int pitch_val = ((pos & 0xFF) < n) ? pitches[pos & 0xFF] : 0;
            last_sample_offset = render_sample(o, last_sample_offset, flags, pitch_val);
            pos += 2;
            frame_count -= 2;
            speedcounter = speed;
        } else {
            int ary[5];
            int p1 = phase1 * 256;   /* fixed point */
            int p2 = phase2 * 256;
            int p3 = phase3 * 256;
            int k;

            /* pos is fixed across the five iterations, so hoist the reads. */
            const int amp0 = (pos < n) ? (fr->ampl[0][pos] & 0x0F) : 0;
            const int amp1 = (pos < n) ? (fr->ampl[1][pos] & 0x0F) : 0;
            const int amp2 = (pos < n) ? (fr->ampl[2][pos] & 0x0F) : 0;
            const int freq0 = (pos < n) ? fr->freq[0][pos] : 0;
            const int freq1 = (pos < n) ? fr->freq[1][pos] : 0;
            const int freq2 = (pos < n) ? fr->freq[2][pos] : 0;
            const int d1 = freq0 * 256 / 4;
            const int d2 = freq1 * 256 / 4;
            const int d3 = freq2 * 256 / 4;

            for (k = 0; k < 5; k++) {
                const int sp1 = sam_sinus[(p1 >> 8) & 0xFF];
                const int sp2 = sam_sinus[(p2 >> 8) & 0xFF];
                const int rp3 = (((p3 >> 8) & 0xFF) < 129) ? -0x70 : 0x70;
                /*
                 * Python divides as float then truncates with int().
                 * C integer division truncates toward zero too (C99
                 * 6.5.5), so these agree for negative sums as well.
                 */
                int mux = (sp1 * amp0 + sp2 * amp1 + rp3 * amp2) / 32 + 128;
                ary[k] = (mux < 0) ? 0 : ((mux > 255) ? 255 : mux);

                p1 += d1;
                p2 += d2;
                p3 += d3;
            }

            output_write_array(o, 0, ary);

            speedcounter--;
            if (speedcounter == 0) {
                pos++;
                frame_count--;
                if (frame_count == 0) {
                    return;
                }
                speedcounter = speed;
            }

            glottal_pulse--;

            if (glottal_pulse != 0) {
                mem38--;
                if (mem38 != 0 || flags == 0) {
                    /* Update the phase of the formants. */
                    const int nf0 = (pos < n) ? fr->freq[0][pos] : 0;
                    const int nf1 = (pos < n) ? fr->freq[1][pos] : 0;
                    const int nf2 = (pos < n) ? fr->freq[2][pos] : 0;
                    phase1 += nf0;
                    phase2 += nf1;
                    phase3 += nf2;
                    continue;
                }

                /* Voiced sampled phonemes. */
                {
                    const int pitch_val = ((pos & 0xFF) < n) ? pitches[pos & 0xFF] : 0;
                    last_sample_offset = render_sample(o, last_sample_offset,
                                                       flags, pitch_val);
                }
            }

            /* Reset at the glottal pulse boundary. */
            glottal_pulse = (pos < n) ? pitches[pos] : 0;
            mem38 = (int)(glottal_pulse * 0.75);

            phase1 = 0;
            phase2 = 0;
            phase3 = 0;
        }
    }
}

/* ------------------------------------------------------------------ */
/* Public entry points                                                 */

SAM_API int sam_abi_version(void)
{
    return SAM_ABI_VERSION;
}

SAM_API int sam_render(const sam_phoneme_t *phonemes,
                       int                  count,
                       const sam_voice_t   *voice,
                       unsigned char       *out,
                       int                  out_capacity)
{
    sam_frames_t fr;
    sam_output_t o;
    int64_t buffersize;
    int total_frames = 0;
    int produced;
    int t, i;

    if (phonemes == NULL || count <= 0 || voice == NULL) {
        return SAM_E_BADARG;
    }
    if (voice->speed == 0) {
        return SAM_E_BADSPEED;
    }

    for (i = 0; i < count; i++) {
        total_frames += phonemes[i].length;
    }

    /* Reserve 176.4 * speed samples (8 * speed ms) for each frame. */
    buffersize = (int64_t)(176.4 * (double)total_frames * (double)voice->speed);
    if (buffersize <= 0) {
        return 0;
    }
    if (out == NULL) {
        /* Upper bound: the exact length is only known once rendered. */
        return (buffersize > 0x7FFFFFFF) ? SAM_E_SHORTBUF : (int)buffersize;
    }

    t = sam_prepare_frames(phonemes, count, voice, &fr);
    if (t < 0) {
        return SAM_E_NOMEM;
    }

    memset(&o, 0, sizeof(o));
    o.buffer = (uint8_t *)calloc((size_t)buffersize, 1);
    if (o.buffer == NULL) {
        sam_frames_free(&fr);
        return SAM_E_NOMEM;
    }
    o.size = buffersize;

    process_frames(&o, t, voice->speed, &fr);

    produced = (int)(o.bufferpos / 50);
    if (produced > buffersize) {
        produced = (int)buffersize;
    }
    if (produced > out_capacity) {
        free(o.buffer);
        sam_frames_free(&fr);
        return SAM_E_SHORTBUF;
    }
    memcpy(out, o.buffer, (size_t)produced);

    free(o.buffer);
    sam_frames_free(&fr);
    return produced;
}
