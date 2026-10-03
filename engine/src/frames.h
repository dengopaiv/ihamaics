/*
 * frames.h - the frames: one row of values per synthesis parameter, one
 * column per 10 ms (at the default speed) of speech.
 *
 * Stage R.3 of the C17 rewrite (docs/c17/03-r3-frames.md). Not part of
 * the public API; the renderer (R.4) is its one caller.
 */

#ifndef SAM_FRAMES_H
#define SAM_FRAMES_H

#include <stdint.h>

#include "sam_render.h"
#include "quirks.h"

/*
 * The frames for one utterance, as prepare_frames() in renderer.py
 * returns them.
 *
 * Formant frequencies and amplitudes are bytes, as in SAM. native/ kept
 * them in int, after the Python; section 3.2 of the chapter proves no
 * interpolation leaves a byte. The pitch row is Q1 in quirks.h.
 */
typedef struct {
    sam_pitch_t *pitch;     /* the voice's pitch, after inflection and F1 */
    uint8_t     *freq[3];   /* formant frequencies F1..F3 */
    uint8_t     *ampl[3];   /* formant amplitudes, after rescaling */
    uint8_t     *flags;     /* sam_sampled_consonant_flags of the phoneme */
    int          count;     /* frames: the sum of the phoneme lengths */
} sam_frames_t;

/*
 * Turn a phoneme list and a voice into frames: create_frames(),
 * create_transitions() and the rest of prepare_frames() in renderer.py.
 *
 * Allocates fr's rows; release them with sam_frames_free(), also on
 * failure. Returns the frame count, which may be 0, or -1 if the rows
 * could not be allocated.
 */
int  sam_prepare_frames(const sam_phoneme_t *phonemes, int count,
                        const sam_voice_t *voice, sam_frames_t *fr);
void sam_frames_free(sam_frames_t *fr);

#endif /* SAM_FRAMES_H */
