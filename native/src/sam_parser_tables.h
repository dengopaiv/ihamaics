/*
 * sam_parser_tables.h - GENERATED FILE, DO NOT EDIT.
 *
 * Produced by native/tools/gen_frontend_tables.py from
 * nvda-addon/synthDrivers/sam/parser_tables.py. Edit the Python tables and
 * regenerate; hand-editing these numbers is how the voice changes by
 * accident.
 */

#ifndef SAM_PARSER_TABLES_H
#define SAM_PARSER_TABLES_H

#include <stdint.h>

#define SAM_PHONEME_NAME_COUNT   81
#define SAM_PHONEME_LENGTH_COUNT 80
#define SAM_STRESS_COUNT         9

/* Two characters and a NUL, so they compare with strncmp. */
extern const char     sam_phoneme_names[SAM_PHONEME_NAME_COUNT][3];
extern const uint16_t sam_phoneme_flags[SAM_PHONEME_NAME_COUNT];

/*
 * Low byte is the unstressed length, high byte the stressed one.
 *
 * This table is one entry SHORTER than the name and flag tables: Python
 * has 80 entries against 81 phonemes, so UN (80) has no length. It never
 * reaches set_phoneme_length because parser2 rewrites UN to AX N* first.
 * The count is kept separate rather than padded so a C bounds check and
 * a Python IndexError describe the same table.
 */
extern const uint16_t sam_phoneme_length_combined[SAM_PHONEME_LENGTH_COUNT];

/* "*12345678" - index into this is the stress value. */
extern const char sam_stress_chars[SAM_STRESS_COUNT + 1];

#endif /* SAM_PARSER_TABLES_H */
