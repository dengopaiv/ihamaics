/*
 * voice.h - the formant frequencies of one voice.
 *
 * Stage R.2 of the C17 rewrite (docs/c17/02-r2-voice.md). Not part of
 * the public API; the frames stage (R.3) is its one caller.
 */

#ifndef SAM_VOICE_H
#define SAM_VOICE_H

#include <stdint.h>

#include "tables.h"

/*
 * The three formant frequencies of every phoneme, one row per formant,
 * after the voice's mouth and throat settings. Bytes, like the tables:
 * native/ kept these in uint16_t because the Python computes them
 * unbounded, and voice.c proves no input needs more than a byte
 * (docs/c17/02-r2-voice.md section 2.2).
 */
typedef struct {
    uint8_t f1[SAM_PHONEME_COUNT];
    uint8_t f2[SAM_PHONEME_COUNT];
    uint8_t f3[SAM_PHONEME_COUNT];
} sam_freqdata_t;

/*
 * Fill out with sam_freq1..3, then scale formant 1 by mouth and formant
 * 2 by throat for the vowels, diphthongs and sonorants (phonemes 5..29
 * and 48..53). Formant 3 and every other phoneme keep their table value.
 * Python: set_mouth_throat() in renderer.py.
 */
void sam_set_mouth_throat(uint8_t mouth, uint8_t throat, sam_freqdata_t *out);

#endif /* SAM_VOICE_H */
