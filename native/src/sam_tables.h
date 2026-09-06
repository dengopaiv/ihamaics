/*
 * sam_tables.h - GENERATED FILE, DO NOT EDIT.
 *
 * Produced by native/tools/gen_tables.py from
 * nvda-addon/synthDrivers/sam/renderer_tables.py. Edit the Python tables
 * and regenerate; hand-editing these numbers is how the voice changes by
 * accident.
 */

#ifndef SAM_TABLES_H
#define SAM_TABLES_H

#include <stdint.h>
#define SAM_PHONEME_COUNT 80
#define SAM_SAMPLE_TABLE_SIZE 1280
extern const uint8_t sam_freq1[80];
extern const uint8_t sam_freq2[80];
extern const uint8_t sam_freq3[80];
extern const uint8_t sam_ampl1[80];
extern const uint8_t sam_ampl2[80];
extern const uint8_t sam_ampl3[80];
extern const uint8_t sam_sampled_consonant_flags[80];
extern const uint8_t sam_blend_rank[80];
extern const uint8_t sam_in_blend_length[80];
extern const uint8_t sam_out_blend_length[80];
extern const uint8_t sam_sample_table[1280];
extern const int8_t sam_sinus[256];
extern const uint8_t sam_stress_pitch[10];
extern const uint8_t sam_amplitude_rescale[16];
extern const uint8_t sam_sampled_consonant_values0[5];
extern const uint8_t sam_time_table[5][5];

#endif /* SAM_TABLES_H */
