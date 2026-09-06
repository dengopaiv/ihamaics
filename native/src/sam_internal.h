/*
 * sam_internal.h - declarations shared inside the native renderer.
 *
 * Not part of the public ABI (see include/sam_render.h). Test harnesses
 * in native/tools compile these translation units directly so they can
 * check each stage against the Python implementation without exporting
 * test hooks from the shipped DLL.
 */

#ifndef SAM_INTERNAL_H
#define SAM_INTERNAL_H

#include <stdint.h>

#include "sam_tables.h"

/*
 * Working formant frequencies, one row per formant.
 *
 * uint16_t rather than uint8_t on purpose: set_mouth_throat's transform
 * is ((factor * f) >> 8 & 0xFF) << 1, which can reach 510. The real
 * tables never get there, but Python and JavaScript both compute this in
 * unbounded integers, and matching that exactly is cheaper than proving
 * a bound that a future table edit could invalidate.
 */
typedef struct {
    uint16_t f1[SAM_PHONEME_COUNT];
    uint16_t f2[SAM_PHONEME_COUNT];
    uint16_t f3[SAM_PHONEME_COUNT];
} sam_freqdata_t;

/*
 * Alter the mouth (F1) and throat (F2) formants.
 *
 * Only the vowel/diphthong and sonorant phonemes (5..29 and 48..53) are
 * touched; every other entry keeps its table value. Port of
 * set_mouth_throat() in renderer.py.
 */
void sam_set_mouth_throat(uint8_t mouth, uint8_t throat, sam_freqdata_t *out);

#endif /* SAM_INTERNAL_H */
