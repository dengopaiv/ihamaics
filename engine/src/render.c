/*
 * render.c - frames turned into sound: SAM's formant synthesizer and its
 * sampled consonants, written to 8-bit unsigned PCM at 22,050 Hz.
 *
 * Stage R.4 of the C17 rewrite (docs/c17/04-r4-renderer.md). Rewritten
 * from native/src/sam_render.c, which ports process_frames(),
 * render_sample(), OutputBuffer and render() in
 * nvda-addon/synthDrivers/sam/renderer.py. SAM (1982, Don't Ask
 * Software, Mark Barton), by way of Stefan Macke's C and Christian
 * Schiffler's JavaScript. See NOTICE.md.
 */

#include <assert.h>
#include <float.h>
#include <limits.h>
#include <stdlib.h>
#include <string.h>

#include "frames.h"
#include "tables.h"

/*
 * The buffer size is int(176.4 * frames * speed) in Python's float.
 * Same reason, and the same check, as in frames.c.
 */
#if defined(FLT_EVAL_METHOD) && FLT_EVAL_METHOD != 0 && FLT_EVAL_METHOD != 1
#error "render.c needs double arithmetic evaluated in double (FLT_EVAL_METHOD 0 or 1)"
#endif

/* Samples reserved per frame and unit of speed: 8 ms at 22,050 Hz. */
#define SAMPLES_PER_FRAME_SPEED  176.4

/* The time table counts in fiftieths of a sample. */
#define TIME_UNITS_PER_SAMPLE  50

/* Each write puts five values, the first at the write position. */
#define WRITE_SPAN  5

/*
 * Rows and columns of sam_time_table: what the previous and this write
 * were. Named for the bit of noise each is used for, from the calls in
 * render_sample(); renderer.py's comments on the table call rows 3 and 4
 * "voiced sample 0" and "1", which is the other way round (section 4.5).
 */
enum {
    WRITE_FORMANTS    = 0,
    WRITE_UNVOICED_0  = 1,   /* unvoiced sample, a 0 bit */
    WRITE_UNVOICED_1  = 2,   /* unvoiced sample, a 1 bit */
    WRITE_VOICED_1    = 3,   /* voiced sample, a 1 bit */
    WRITE_VOICED_0    = 4    /* voiced sample, a 0 bit */
};

/* sam_sampled_consonant_flags: high five bits set is an unvoiced one. */
#define FLAGS_UNVOICED_MASK  0xF8u
#define FLAGS_KIND_MASK      0x07u

/* What a voiced sample writes for a 1 and a 0 bit, and an unvoiced
 * one for a 1 bit (its 0 bit is sam_sampled_consonant_values0). */
#define VOICED_VALUE_1     26
#define VOICED_VALUE_0      6
#define UNVOICED_VALUE_1    5

/* Formant 3 is a square wave of this height. */
#define SQUARE_HEIGHT    0x70

/* ------------------------------------------------------------------ */
/* Output                                                              */

/*
 * OutputBuffer in the Python: a zeroed buffer of `size` bytes, written
 * five values at a time at a position the time table moves along.
 *
 * Here the buffer is not zeroed up front. It is 176.4 * speed bytes per
 * frame, and SAM uses a few per cent of it (the golden cases 1 to 2,
 * section 4.3), so zeroing it all would cost more than rendering. Bytes
 * are zeroed as the write position passes them instead, and `zeroed`
 * says how far that has gone: every byte below it has been zeroed or
 * written, which is what the Python's buffer holds there.
 */
typedef struct {
    uint8_t *buf;
    int64_t  size;
    int64_t  zeroed;
    int64_t  time;        /* bufferpos: the position in fiftieths */
    int      last_write;  /* old_timetable_index */
} output_t;

static void zero_to(output_t *o, int64_t end)
{
    if (end > o->size) {
        end = o->size;
    }
    if (end > o->zeroed) {
        memset(o->buf + o->zeroed, 0, (size_t)(end - o->zeroed));
        o->zeroed = end;
    }
}

static void write_five(output_t *o, int kind, const uint8_t values[WRITE_SPAN])
{
    o->time += sam_time_table[o->last_write][kind];

    const int64_t pos = o->time / TIME_UNITS_PER_SAMPLE;
    if (pos > o->size) {
        /*
         * The Python raises RuntimeError("Buffer overflow") here, so
         * nothing past this point is defined by the oracle. native/
         * skipped the write and kept the time moving, and so does the
         * rewrite, which keeps it equal to native/ on every input
         * (section 4.4). 10 of verify_render.py's 485 random cases get
         * here, all at speed 1.
         */
        return;
    }
    o->last_write = kind;

    zero_to(o, pos);
    for (int k = 0; k < WRITE_SPAN && pos + k < o->size; k++) {
        o->buf[pos + k] = values[k];
    }
    if (pos + WRITE_SPAN > o->zeroed) {
        o->zeroed = (pos + WRITE_SPAN < o->size) ? pos + WRITE_SPAN : o->size;
    }
}

/* One sample of a sampled consonant: a 4-bit level, five times. */
static void write_level(output_t *o, int kind, uint8_t level)
{
    const uint8_t v = (uint8_t)((level & 0x0Fu) * 16u);
    const uint8_t five[WRITE_SPAN] = { v, v, v, v, v };

    write_five(o, kind, five);
}

/* ------------------------------------------------------------------ */
/* Sampled consonants                                                  */

/* Eight samples from one byte of noise, high bit first. */
static void write_noise_byte(output_t *o, uint8_t noise,
                             int kind1, uint8_t value1,
                             int kind0, uint8_t value0)
{
    for (int bit = 0; bit < 8; bit++) {
        if (noise & 0x80u) {
            write_level(o, kind1, value1);
        } else {
            write_level(o, kind0, value0);
        }
        noise = (uint8_t)(noise << 1);
    }
}

/*
 * A sampled consonant. render_sample() in renderer.py.
 *
 * The kind of a nonzero flag is 0..4 for every phoneme (section 4.2:
 * the table's twelve nonzero flags, enumerated), so the page is always
 * inside sam_sample_table and sam_sampled_consonant_values0. The
 * Python's guards against both, and native/'s reading of kind -1 as
 * values0[-1], are for flags no phoneme has.
 *
 * Returns the offset a following voiced sample continues from.
 */
static uint8_t render_sample(output_t *o, uint8_t last_offset,
                             uint8_t flags, sam_pitch_t pitch)
{
    const int kind = (int)(flags & FLAGS_KIND_MASK) - 1;
    assert(kind >= 0 && kind < SAM_SAMPLED_CONSONANT_KINDS);
    const uint8_t *page = sam_sample_table + (size_t)kind * 256u;
    uint8_t off = (uint8_t)(flags & FLAGS_UNVOICED_MASK);

    if (off == 0) {
        /*
         * Voiced: Z, ZH, V, DH. As many bytes as the pitch is long, in
         * sixteenths, continuing from the last offset.
         *
         * Python's pitch >> 4 floors, and & 0xFF keeps bits 4..11 of
         * the pitch in two's complement. The pitch can be negative or
         * past a byte (Q1 in quirks.h; both are reached, section 4.3).
         * The conversion to uint32_t is modular, so its bits 4..11 are
         * the same ones, with no right shift of a negative number.
         */
        uint8_t left = (uint8_t)~(uint8_t)((uint32_t)pitch >> 4);
        off = last_offset;
        do {
            write_noise_byte(o, page[off], WRITE_VOICED_1, VOICED_VALUE_1,
                             WRITE_VOICED_0, VOICED_VALUE_0);
            off++;
            left++;
        } while (left != 0);
        return off;
    }

    /* Unvoiced: from the flag's offset to the end of the page. */
    const uint8_t value0 = sam_sampled_consonant_values0[kind];
    off = (uint8_t)~off;
    do {
        write_noise_byte(o, page[off], WRITE_UNVOICED_1, UNVOICED_VALUE_1,
                         WRITE_UNVOICED_0, value0);
        off++;
    } while (off != 0);
    return last_offset;
}

/* ------------------------------------------------------------------ */
/* Formants                                                            */

/*
 * Five samples of the three formants: two sines and a square wave, each
 * at its frame's frequency and amplitude, summed.
 *
 * phase[] is the Python's phase1..3 modulo 256. The Python keeps them
 * unbounded (section 4.3 measured 7,443,690, and native/'s int phase
 * * 256 came within 12% of overflowing), but reads each only through
 * ((phase * 256 + k * d) >> 8) & 0xFF with k * d >= 0, which is
 * (phase + ((k * d) >> 8)) mod 256: only phase mod 256 reaches the
 * output (section 4.2). The fixed-point position is likewise kept in
 * uint32_t, where its bits 8..15, the only ones read, wrap exactly.
 */
static void render_formants(output_t *o, const sam_frames_t *fr, int pos,
                            const uint8_t phase[3])
{
    uint32_t p[3];
    uint32_t step[3];
    int amp[3];
    uint8_t out[WRITE_SPAN];

    for (int f = 0; f < 3; f++) {
        p[f] = (uint32_t)phase[f] << 8;
        step[f] = (uint32_t)fr->freq[f][pos] * 64u;   /* int(freq * 256 / 4) */
        amp[f] = fr->ampl[f][pos] & 0x0F;
    }

    for (int k = 0; k < WRITE_SPAN; k++) {
        const int s1 = sam_sinus[(p[0] >> 8) & 0xFFu];
        const int s2 = sam_sinus[(p[1] >> 8) & 0xFFu];
        const int s3 = (((p[2] >> 8) & 0xFFu) < 129u) ? -SQUARE_HEIGHT : SQUARE_HEIGHT;

        /*
         * int(sum / 32) in the Python truncates toward zero; so does
         * C's division. |sum| <= 5,490 here, and a division by 32 of an
         * integer that size is exact in a double, so the two agree
         * (section 4.2).
         */
        const int mux = (s1 * amp[0] + s2 * amp[1] + s3 * amp[2]) / 32 + 128;

        /*
         * The tables allow -43..299; the corpus reached only 3..252
         * (section 4.3). Not proved unreachable, so the Python's clamp
         * stays.
         */
        out[k] = (uint8_t)(mux < 0 ? 0 : (mux > UINT8_MAX ? UINT8_MAX : mux));

        for (int f = 0; f < 3; f++) {
            p[f] += step[f];
        }
    }
    write_five(o, WRITE_FORMANTS, out);
}

/* int(g * 0.75) in the Python: exact in a double for any int32 g, and
 * truncated toward zero, as C's division truncates 3 * g / 4. */
static int64_t three_quarters(int64_t g)
{
    return g * 3 / 4;
}

/* ------------------------------------------------------------------ */
/* The frame loop                                                      */

/*
 * process_frames() in renderer.py.
 *
 * The Python counts frames down in frame_count and up in pos, and checks
 * pos against each row before reading it. Its frame_count starts at the
 * frame count, which is the row length (R.3, section 3.2(c)), and the
 * two always move together, so pos + frame_count is the row length
 * throughout. Every check is then pos < n, which the loop condition and
 * the return after pos++ already guarantee (section 4.2): none is
 * needed, and none of them ever failed over the corpus (section 4.3).
 */
static void process_frames(output_t *o, const sam_frames_t *fr, int speed)
{
    const int n = fr->count;
    int pos = 0;
    int speedcounter = speed;
    uint8_t phase[3] = { 0, 0, 0 };
    uint8_t last_offset = 0;

    if (n <= 0) {
        return;
    }

    /* Q3 in quirks.h: the glottal pulse counters do not wrap. */
    sam_pulse_t glottal_pulse = fr->pitch[0];
    sam_pulse_t mem38 = three_quarters(glottal_pulse);

    while (pos < n) {
        const uint8_t flags = fr->flags[pos];

        if (flags & FLAGS_UNVOICED_MASK) {
            /*
             * The pitch is read at pos & 0xFF: SAM's 8-bit index
             * register, kept by every port. Reached in 149 of the 485
             * random cases. pos & 0xFF <= pos < n, so the Python's
             * "else 0" never applies.
             */
            last_offset = render_sample(o, last_offset, flags, fr->pitch[pos & 0xFF]);
            pos += 2;
            speedcounter = speed;
            continue;
        }

        render_formants(o, fr, pos, phase);

        if (--speedcounter == 0) {
            pos++;
            if (pos == n) {
                return;
            }
            speedcounter = speed;
        }

        glottal_pulse--;
        if (glottal_pulse != 0) {
            mem38--;
            if (mem38 != 0 || flags == 0) {
                for (int f = 0; f < 3; f++) {
                    phase[f] = (uint8_t)(phase[f] + fr->freq[f][pos]);
                }
                continue;
            }
            /* A voiced sampled consonant, three quarters into the pulse. */
            last_offset = render_sample(o, last_offset, flags, fr->pitch[pos & 0xFF]);
        }

        /* The glottal pulse starts again: the formants' phases reset. */
        glottal_pulse = fr->pitch[pos];
        mem38 = three_quarters(glottal_pulse);
        phase[0] = phase[1] = phase[2] = 0;
    }
}

/* ------------------------------------------------------------------ */
/* Entry point                                                         */

/*
 * render() in renderer.py, with sam_render.h's contract around it: a
 * query for the size, error codes, and nothing written to out on
 * SAM_E_SHORTBUF.
 */
SAM_API int sam_render(const sam_phoneme_t *phonemes,
                       int                  count,
                       const sam_voice_t   *voice,
                       unsigned char       *out,
                       int                  out_capacity)
{
    if (phonemes == NULL || count <= 0 || voice == NULL) {
        return SAM_E_BADARG;
    }
    if (voice->speed == 0) {
        return SAM_E_BADSPEED;
    }

    int64_t frames = 0;
    for (int i = 0; i < count; i++) {
        frames += phonemes[i].length;
    }

    /* Left to right, as the Python multiplies: (176.4 * frames) * speed.
     * frames <= 255 * INT_MAX, so the product stays below 2^63. */
    const int64_t size = (int64_t)(SAMPLES_PER_FRAME_SPEED * (double)frames
                                   * (double)voice->speed);
    if (size <= 0) {
        return 0;
    }
    if (out == NULL) {
        /* Upper bound: the exact length is only known once rendered. */
        return (size > INT_MAX) ? SAM_E_SHORTBUF : (int)size;
    }

    sam_frames_t fr;
    if (sam_prepare_frames(phonemes, count, voice, &fr) < 0) {
        sam_frames_free(&fr);
        return SAM_E_NOMEM;
    }

    /*
     * Render straight into out when it holds the whole buffer, which it
     * does after a size query. Otherwise into a buffer of our own, so
     * that a call that ends in SAM_E_SHORTBUF writes nothing to out.
     */
    output_t o = { NULL, size, 0, 0, WRITE_FORMANTS };
    const int direct = (int64_t)out_capacity >= size;
    o.buf = direct ? out : malloc((size_t)size);
    if (o.buf == NULL) {
        sam_frames_free(&fr);
        return SAM_E_NOMEM;
    }

    process_frames(&o, &fr, voice->speed);
    sam_frames_free(&fr);

    /* get(): buffer[:bufferpos // 50], which a slice cuts at the size. */
    int64_t produced = o.time / TIME_UNITS_PER_SAMPLE;
    if (produced > size) {
        produced = size;
    }
    zero_to(&o, produced);

    int result = SAM_E_SHORTBUF;
    if (produced <= out_capacity) {
        result = (int)produced;
        if (!direct) {
            memcpy(out, o.buf, (size_t)produced);
        }
    }
    if (!direct) {
        free(o.buf);
    }
    return result;
}
