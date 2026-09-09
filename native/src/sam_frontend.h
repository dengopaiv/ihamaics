/*
 * sam_frontend.h - declarations shared inside the native front end.
 *
 * Not part of the public ABI (see include/sam_text.h). The verification
 * harnesses in native/tools compile these translation units directly so
 * each stage can be checked against the Python implementation without
 * exporting test hooks from the shipped DLL, exactly as sam_internal.h
 * does for the renderer.
 */

#ifndef SAM_FRONTEND_H
#define SAM_FRONTEND_H

#include <stdint.h>

#include "sam_render.h"
#include "sam_parser_tables.h"
#include "sam_reciter_tables.h"

/*
 * "There is no phoneme here."
 *
 * Python's get_phoneme() returns None past either end of the list, and
 * several rules in parser2 and adjust_lengths distinguish None from the
 * pause phoneme 0 - `next_phoneme == 0` and `next_phoneme is not None`
 * are separate tests on the same value. A sentinel keeps that distinction
 * in C, and -1 also falls out of phoneme_has_flag() as false the way
 * None does.
 */
#define SAM_NO_PHONEME (-1)

/*
 * The parser's working lists.
 *
 * int, not uint8_t, for all three rows: Python computes lengths and
 * stresses as unbounded integers and the arithmetic in adjust_lengths
 * (`(length >> 1) + length + 1`) can leave the byte range. Narrowing
 * happens once, where the triples are handed to the renderer, which is
 * also where the existing verified ctypes path narrows them.
 */
typedef struct {
    int *phoneme;
    int *length;
    int *stress;
    int  count;
    int  capacity;
} sam_plist_t;

void sam_plist_init(sam_plist_t *pl);
void sam_plist_free(sam_plist_t *pl);

/*
 * Parse a phoneme string into the renderer's [phoneme, length, stress]
 * triples, leaving them in pl. Returns 0 on success and -1 if the string
 * contains a character that is neither a phoneme nor a stress digit
 * (Python raises ValueError there and parse() returns False) or if an
 * allocation fails.
 *
 * Port of parse() in parser.py. Entries whose phoneme is 0 are dropped,
 * as Python's final `if phoneme:` filter does.
 */
int sam_parse_phonemes(const char *input, sam_plist_t *pl);

/*
 * Rules-only text to phonemes, the port of _rule_based_phonemes().
 *
 * Writes a NUL-terminated string and returns its length, or -1 if the
 * input contains a character the rules reject (Python returns False) or
 * the buffer is too small. The caller sizes the buffer; the rules can
 * expand one character into as many as 15.
 */
int sam_reciter_rules(const char *text, char *out, int out_capacity);

/*
 * The dictionary blob: a sorted, NUL-separated word list with a
 * fixed-width offset table, searched in place. See native/tools/gen_dict.py
 * for the layout and the reason it is not a compiled C array.
 *
 * Returns the ARPABET pronunciation for word (uppercase, NUL-terminated)
 * or NULL when it is absent. The returned pointer is into the blob and is
 * valid as long as the blob is.
 */
const char *sam_dict_lookup(const void *dict, int dict_len,
                            const char *word, int *out_len);

/*
 * ARPABET to SAM phonemes, the port of arpabet_to_sam(). arp is a
 * space-separated pronunciation as it appears in the blob. Returns the
 * written length or -1 if the buffer is too small.
 */
int sam_arpabet_to_sam(const char *arp, int arp_len, char *out, int out_capacity);

#endif /* SAM_FRONTEND_H */
