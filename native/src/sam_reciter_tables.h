/*
 * sam_reciter_tables.h - GENERATED FILE, DO NOT EDIT.
 *
 * Produced by native/tools/gen_frontend_tables.py from
 * nvda-addon/synthDrivers/sam/reciter_tables.py. Edit the Python tables and
 * regenerate; hand-editing these numbers is how the voice changes by
 * accident.
 */

#ifndef SAM_RECITER_TABLES_H
#define SAM_RECITER_TABLES_H

#include <stdint.h>

#define SAM_RULE_COUNT  403
#define SAM_RULE2_COUNT 41

/*
 * One reciter rule, "xxx(yyy)zzz=foobar" already split at the brackets:
 * pre is xxx, match is yyy, post is zzz and target is the phonemes to
 * emit. Splitting here rather than at match time is the whole reason
 * this file is generated.
 */
typedef struct {
    const char   *pre;
    const char   *match;
    const char   *post;
    const char   *target;
    unsigned char match_len;
} sam_rule_t;

/* Indexed by character; entries Python left out of char_flags are 0. */
extern const uint8_t sam_char_flags[256];

/*
 * The main rule set, grouped by the first character of match. Rules for
 * character c are sam_rules[sam_rule_off[c] .. + sam_rule_cnt[c]), in
 * the order Python stores them - the engine takes the first match, so
 * that order is behaviour and not presentation.
 */
extern const sam_rule_t sam_rules[SAM_RULE_COUNT];
extern const int16_t    sam_rule_off[256];
extern const int16_t    sam_rule_cnt[256];

/* Punctuation, digits and symbols: one flat list, tried in order. */
extern const sam_rule_t sam_rules2[SAM_RULE2_COUNT];

#endif /* SAM_RECITER_TABLES_H */
