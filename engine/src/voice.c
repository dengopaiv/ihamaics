/*
 * voice.c - SAM's mouth and throat settings, applied to the formant
 * table.
 *
 * Stage R.2 of the C17 rewrite (docs/c17/02-r2-voice.md). Rewritten from
 * native/src/sam_frames.c (sam_set_mouth_throat and trans), which ports
 * set_mouth_throat() in nvda-addon/synthDrivers/sam/renderer.py. SAM
 * (1982, Don't Ask Software, Mark Barton), by way of Stefan Macke's C
 * and Christian Schiffler's JavaScript. See NOTICE.md.
 */

#include <string.h>

#include "voice.h"

/*
 * The phonemes a voice alters, as half-open ranges: IY..NX (5..29), the
 * vowels and sonorants, and EY..UW (48..53), the diphthongs.
 */
#define VOICED_FIRST     5
#define VOICED_END      30
#define DIPHTHONG_FIRST 48
#define DIPHTHONG_END   54

/*
 * The new frequency is (factor * f) >> 8, doubled: factor / 128 times
 * the table value, rounded down to an even number.
 *
 * The Python writes ((factor * f) >> 8 & 0xFF) << 1 on unbounded
 * integers, and native/ kept the result in uint16_t because that can
 * reach 510 in principle. Here it is a byte, and two facts make that
 * exact rather than a change:
 *
 *   - factor and f are bytes, so factor * f <= 255 * 255 and the shift
 *     alone leaves less than 256; the Python's & 0xFF never changes a
 *     value, and is not written.
 *   - Doubling stays within a byte while f <= 128. SAM_FREQ_MAX is the
 *     largest value in the tables, written by gen_tables.py, so the
 *     assertion below fails the build if a table ever breaks this.
 *
 * Measured over all 65,536 (mouth, throat) pairs on 2026-10-03, the
 * largest result is 170: F2 of NX (86) at throat 254 or 255.
 */
_Static_assert((((255 * SAM_FREQ_MAX) >> 8) << 1) <= UINT8_MAX,
               "a scaled formant frequency must fit in a byte");

static uint8_t scale(uint8_t factor, uint8_t f)
{
    return (uint8_t)((((unsigned)factor * f) >> 8) << 1);
}

static void scale_range(uint8_t mouth, uint8_t throat, sam_freqdata_t *fd,
                        int first, int end)
{
    for (int i = first; i < end; i++) {
        fd->f1[i] = scale(mouth, fd->f1[i]);
        fd->f2[i] = scale(throat, fd->f2[i]);
    }
}

void sam_set_mouth_throat(uint8_t mouth, uint8_t throat, sam_freqdata_t *out)
{
    memcpy(out->f1, sam_freq1, sizeof out->f1);
    memcpy(out->f2, sam_freq2, sizeof out->f2);
    memcpy(out->f3, sam_freq3, sizeof out->f3);
    scale_range(mouth, throat, out, VOICED_FIRST, VOICED_END);
    scale_range(mouth, throat, out, DIPHTHONG_FIRST, DIPHTHONG_END);
}
