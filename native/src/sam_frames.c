/*
 * sam_frames.c - frame preparation for the native renderer.
 *
 * Ported from nvda-addon/synthDrivers/sam/renderer.py. Every function
 * here is checked against its Python counterpart by the harnesses in
 * native/tools; see docs/c-engine-port.md.
 */

#include "sam_internal.h"

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
