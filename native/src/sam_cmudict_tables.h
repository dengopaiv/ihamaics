/*
 * sam_cmudict_tables.h - GENERATED FILE, DO NOT EDIT.
 *
 * Produced by native/tools/gen_frontend_tables.py from
 * nvda-addon/synthDrivers/sam/cmudict.py. Edit the Python tables and
 * regenerate; hand-editing these numbers is how the voice changes by
 * accident.
 */

#ifndef SAM_CMUDICT_TABLES_H
#define SAM_CMUDICT_TABLES_H

#define SAM_ARPABET_COUNT 39

/* ARPABET base phoneme to the SAM spelling of the same sound. */
typedef struct {
    const char *arpabet;
    const char *sam;
} sam_arpabet_map_t;

/* Sorted by arpabet, so a binary search and Python's dict agree. */
extern const sam_arpabet_map_t sam_arpabet_map[SAM_ARPABET_COUNT];

/*
 * CMU stress digit to the SAM stress marker, indexed by digit - '0'.
 * "" for unstressed, "4" for primary, "2" for secondary.
 */
extern const char *const sam_stress_markers[3];

#endif /* SAM_CMUDICT_TABLES_H */
