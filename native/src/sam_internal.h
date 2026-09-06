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

#include "sam_render.h"
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

/*
 * The per-frame working set.
 *
 * The seven interpolated rows are int, not uint8_t. create_transitions()
 * writes interpolated values back unmasked, and pitches has been measured
 * from -194 to 366 across the golden cases and randomised phoneme
 * sequences. Python computes these as unbounded integers; int matches
 * that without having to prove a bound.
 */
typedef struct {
    int     *pitches;      /* row 0, and the base of the single allocation */
    int     *freq[3];      /* rows 1..3 */
    int     *ampl[3];      /* rows 4..6 */
    uint8_t *flags;        /* sampled consonant flags */
    int      capacity;     /* frames allocated */
    int      count;        /* frames written by create_frames */
    int      total;        /* frame count returned by create_transitions */
} sam_frames_t;

int  sam_frames_alloc(sam_frames_t *fr, int total_frames);
void sam_frames_free(sam_frames_t *fr);

void sam_create_frames(uint8_t pitch, const sam_phoneme_t *phonemes, int count,
                       const sam_freqdata_t *fd, int inflection,
                       sam_frames_t *fr);

int sam_create_transitions(sam_frames_t *fr, const sam_phoneme_t *phonemes,
                           int count);

/*
 * Run the whole preparation pipeline. Allocates fr; the caller must
 * sam_frames_free() it. Returns the frame count, or -1 on allocation
 * failure.
 */
int sam_prepare_frames(const sam_phoneme_t *phonemes, int count,
                       const sam_voice_t *voice, sam_frames_t *fr);

#endif /* SAM_INTERNAL_H */
