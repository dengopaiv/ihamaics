/*
 * quirks.h - every Python idiom the rewrite reproduces, in one place.
 *
 * The C17 rewrite (docs/c17-rewrite-plan.md sections 1.1 and 1.2) sorts
 * each idiom native/ took from the Python oracle into one of two bins:
 * the voice depends on it, or no input reaches it. The ones in the first
 * bin are here, each named, with the Python line it reproduces and the
 * measurement that put it here. Each call site carries a comment too.
 * This file is the list to read when a quirk is ever reconsidered (plan
 * section 8, decision D5).
 *
 * The idioms that were dropped are not here. Each is in the chapter of
 * the stage that dropped it, with the bound that made it safe:
 *   R.2  uint16_t formant rows             docs/c17/02-r2-voice.md 2.2
 *   R.3  int formant and amplitude rows,
 *        negative amplitude indexing,
 *        int(change / width)               docs/c17/03-r3-frames.md 3.2
 *   R.4  unbounded formant phases,
 *        sampled-consonant kind -1 and
 *        the sample table guard,
 *        the pos < n guards in the loop    docs/c17/04-r4-renderer.md 4.2
 */

#ifndef SAM_QUIRKS_H
#define SAM_QUIRKS_H

#include <stdint.h>

/*
 * Q1 (R.3). The pitch row is wider than a byte.
 *
 * SAM's pitch is a byte, but create_transitions() in renderer.py writes
 * interpolated pitches back unmasked, in Python's unbounded int, and in
 * sing mode prepare_frames() hands them to the renderer that way. Over
 * verify_prepare.py's 3,000 random cases they range from -480 to 658,
 * and a hill-climbing search reached 3,470 (docs/c17/03-r3-frames.md
 * section 3.2), so a byte is not enough and the voice depends on it.
 *
 * No bound has been proved: one transition can stretch the row's range
 * to three times its width. int32_t holds everything measured, by a
 * factor of over 600,000. The interpolation computes in 64 bits and
 * saturates on the way into the row (frames.c), so an input beyond that
 * is defined behaviour rather than overflow; there the rewrite and the
 * Python disagree, as native/ did.
 */
typedef int32_t sam_pitch_t;

/*
 * Q2 (R.3). A negative list index counts from the end.
 *
 * interpolate() in renderer.py guards its write with
 * `if frame < len(t): t[frame] = val`, and frame goes negative when a
 * phoneme is shorter than the blend leading into it. Python then writes
 * t[len + frame], near the end of the row. 236 of verify_prepare.py's
 * 3,000 random cases write that way, so the voice depends on it.
 *
 * Returns the index Python's t[i] = v writes, for i < n. Below -n Python
 * raises IndexError; that is outside what the oracle defines, and, as in
 * native/, the write is skipped: -1 is returned.
 */
static inline int sam_py_index(int i, int n)
{
    if (i >= 0) {
        return i;
    }
    return (i + n >= 0) ? i + n : -1;
}

/*
 * Q3 (R.4). The glottal pulse counters do not wrap.
 *
 * process_frames() in renderer.py counts the glottal pulse down from the
 * frame's pitch, and mem38 from three quarters of it, and resets both
 * when the pulse reaches 0. In Python's unbounded int a pulse that
 * starts at 0 or below (a pitch of 0, or a negative one from Q1) only
 * goes further down, so it never resets again until the utterance ends:
 * the formants' phases keep running and no voiced consonant is sampled.
 * Over verify_render.py's 485 random cases, 10 start that way and 68
 * reset into it, and 78 cases render 1,734,241 formant steps while
 * stuck (docs/c17/04-r4-renderer.md section 4.3), so the voice depends
 * on it. A byte counter, which would come round to 0 again, is a
 * mutant that dies.
 *
 * int64_t: the counters start within int32_t (Q1) and fall by one per
 * formant step, of which an utterance has fewer than 2^40 (FRAMES_MAX
 * frames, at most 255 steps each), so they cannot overflow.
 */
typedef int64_t sam_pulse_t;

#endif /* SAM_QUIRKS_H */
