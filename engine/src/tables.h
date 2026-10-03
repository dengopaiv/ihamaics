/*
 * tables.h - GENERATED FILE, DO NOT EDIT.
 *
 * Written by engine/tools/gen_tables.py from
 * nvda-addon/synthDrivers/sam/renderer_tables.py. Change a value there,
 * then regenerate; `gen_tables.py --check` (ctest label "quick") fails
 * while the two disagree.
 *
 * SAM's tables (1982, Don't Ask Software, Mark Barton), as published by
 * Stefan Macke's C and Christian Schiffler's JavaScript. See NOTICE.md.
 */

#ifndef SAM_TABLES_H
#define SAM_TABLES_H

#include <stdint.h>

#define SAM_PHONEME_COUNT            80
#define SAM_SAMPLE_TABLE_SIZE        1280
#define SAM_SINUS_SIZE               256
#define SAM_STRESS_LEVELS            10
#define SAM_AMPLITUDE_LEVELS         16
#define SAM_SAMPLED_CONSONANT_KINDS  5
#define SAM_TIME_TABLE_ROWS          5
#define SAM_TIME_TABLE_COLS          5

/*
 * The largest value in sam_freq1..3, measured here so the C can
 * state a bound on it. voice.c relies on it (R.2): the mouth and
 * throat transform keeps any frequency up to 128 within a byte.
 */
#define SAM_FREQ_MAX                 127

/*
 * Formant 1 frequency of each phoneme, before the voice's mouth
 * setting scales it (R.2). Byte 0 of FREQUENCY_DATA.
 */
extern const uint8_t sam_freq1[SAM_PHONEME_COUNT];

/*
 * Formant 2 frequency, before the throat setting scales it.
 * Byte 1 of FREQUENCY_DATA.
 */
extern const uint8_t sam_freq2[SAM_PHONEME_COUNT];

/*
 * Formant 3 frequency; no voice setting touches it. Byte 2 of
 * FREQUENCY_DATA.
 */
extern const uint8_t sam_freq3[SAM_PHONEME_COUNT];

/*
 * Formant 1 amplitude of each phoneme, as an index into
 * sam_amplitude_rescale. Byte 0 of AMPLITUDE_DATA.
 */
extern const uint8_t sam_ampl1[SAM_PHONEME_COUNT];

/*
 * Formant 2 amplitude, the same way. Byte 1 of AMPLITUDE_DATA.
 */
extern const uint8_t sam_ampl2[SAM_PHONEME_COUNT];

/*
 * Formant 3 amplitude, the same way. Byte 2 of AMPLITUDE_DATA.
 */
extern const uint8_t sam_ampl3[SAM_PHONEME_COUNT];

/*
 * Per phoneme, for a sampled consonant: the low three bits pick
 * the 256-byte section of sam_sample_table (1..5), the high five
 * bits where in it an unvoiced one starts. High bits zero is a
 * voiced one (Z, ZH, V, DH), which continues from where the last
 * sample stopped. 0 for a phoneme with no sample.
 */
extern const uint8_t sam_sampled_consonant_flags[SAM_PHONEME_COUNT];

/*
 * Per phoneme: between two phonemes, the one with the lower rank
 * decides the length of the transition.
 */
extern const uint8_t sam_blend_rank[SAM_PHONEME_COUNT];

/*
 * Per phoneme: frames at its start used to interpolate from the
 * phoneme before.
 */
extern const uint8_t sam_in_blend_length[SAM_PHONEME_COUNT];

/*
 * Per phoneme: frames at its end used to interpolate to the next.
 */
extern const uint8_t sam_out_blend_length[SAM_PHONEME_COUNT];

/*
 * The sampled consonants: five 256-byte sections of one-bit
 * noise, eight samples per byte.
 */
extern const uint8_t sam_sample_table[SAM_SAMPLE_TABLE_SIZE];

/*
 * One cycle of sine, int(127 * sin(2 pi x / 256)), indexed by the
 * high byte of the phase of formant 1 or 2 (formant 3 is a square
 * wave). Computed by the Python, so the engine needs no libm and
 * no agreement with it about rounding.
 */
extern const int8_t sam_sinus[SAM_SINUS_SIZE];

/*
 * Pitch offset for each stress value 0..9. Scaled by inflection / 50,
 * truncated, then added to the pitch modulo 256, so at the default
 * inflection 0xE0 takes 32 off the pitch value.
 */
extern const uint8_t sam_stress_pitch[SAM_STRESS_LEVELS];

/*
 * Indexed by amplitude 0..15 from sam_ampl*: the level the mixer
 * uses. The Python calls it "decibels to linear".
 */
extern const uint8_t sam_amplitude_rescale[SAM_AMPLITUDE_LEVELS];

/*
 * For each kind of sampled consonant: the value output for a
 * zero bit of its noise.
 */
extern const uint8_t sam_sampled_consonant_values0[SAM_SAMPLED_CONSONANT_KINDS];

/*
 * The output timetable: how far the write position moves, in
 * fiftieths of a sample, indexed by the kind of the previous write
 * and of this one.
 */
extern const uint8_t sam_time_table[SAM_TIME_TABLE_ROWS][SAM_TIME_TABLE_COLS];

#endif /* SAM_TABLES_H */
