/*
 * sam_parser.c - phoneme string to the renderer's [phoneme, length, stress]
 * triples. Port of nvda-addon/synthDrivers/sam/parser.py.
 *
 * The Python is written around closures over three parallel lists, and
 * its behaviour at the edges of those lists is load-bearing rather than
 * incidental: reads past either end yield None or 0, and one write in
 * adjust_lengths goes through index -1, which in Python means the last
 * element. That write is reachable - parse(".") returns a length of 1
 * where the table says 18, entirely because of it - so it is reproduced
 * here rather than tidied away. See py_set().
 */

#include <stdlib.h>
#include <string.h>

#include "sam_frontend.h"

/* Phoneme indices the rules name directly. */
#define pR 23
#define pD 57
#define pT 69

/* Flags, from the comments in parser_tables.py. */
#define FLAG_FRICATIVE          0x2000
#define FLAG_LIQUID             0x1000
#define FLAG_NASAL              0x0800
#define FLAG_ALVEOLAR           0x0400
#define FLAG_PUNCT              0x0100
#define FLAG_VOWEL              0x0080
#define FLAG_CONSONANT          0x0040
#define FLAG_DIP_YX             0x0020
#define FLAG_DIPHTHONG          0x0010
#define FLAG_0008               0x0008
#define FLAG_VOICED             0x0004
#define FLAG_STOPCONS           0x0002
#define FLAG_UNVOICED_STOPCONS  0x0001

/* --------------------------------------------------------------------- */
/* The working lists                                                     */
/* --------------------------------------------------------------------- */

void sam_plist_init(sam_plist_t *pl)
{
    memset(pl, 0, sizeof(*pl));
}

void sam_plist_free(sam_plist_t *pl)
{
    free(pl->phoneme);
    free(pl->length);
    free(pl->stress);
    memset(pl, 0, sizeof(*pl));
}

static int plist_reserve(sam_plist_t *pl, int need)
{
    int cap = pl->capacity;
    int *p;

    if (need <= cap) {
        return 0;
    }
    if (cap == 0) {
        cap = 64;
    }
    while (cap < need) {
        cap *= 2;
    }

    p = (int *)realloc(pl->phoneme, (size_t)cap * sizeof(int));
    if (p == NULL) {
        return -1;
    }
    pl->phoneme = p;

    p = (int *)realloc(pl->length, (size_t)cap * sizeof(int));
    if (p == NULL) {
        return -1;
    }
    pl->length = p;

    p = (int *)realloc(pl->stress, (size_t)cap * sizeof(int));
    if (p == NULL) {
        return -1;
    }
    pl->stress = p;

    pl->capacity = cap;
    return 0;
}

static int plist_append(sam_plist_t *pl, int phoneme)
{
    if (plist_reserve(pl, pl->count + 1) != 0) {
        return -1;
    }
    pl->phoneme[pl->count] = phoneme;
    pl->length[pl->count] = 0;
    pl->stress[pl->count] = 0;
    pl->count++;
    return 0;
}

/* list.insert(pos, ...) on all three rows at once. */
static int plist_insert(sam_plist_t *pl, int pos, int phoneme, int stress,
                        int length)
{
    int tail;

    if (plist_reserve(pl, pl->count + 1) != 0) {
        return -1;
    }
    if (pos < 0) {
        pos = 0;
    }
    if (pos > pl->count) {
        pos = pl->count;   /* Python clamps an over-large insert index too */
    }
    tail = pl->count - pos;
    if (tail > 0) {
        memmove(pl->phoneme + pos + 1, pl->phoneme + pos,
                (size_t)tail * sizeof(int));
        memmove(pl->length + pos + 1, pl->length + pos,
                (size_t)tail * sizeof(int));
        memmove(pl->stress + pos + 1, pl->stress + pos,
                (size_t)tail * sizeof(int));
    }
    pl->phoneme[pos] = phoneme;
    pl->length[pos] = length;
    pl->stress[pos] = stress;
    pl->count++;
    return 0;
}

/*
 * Python's `row[pos] = value`, negative indices and all.
 *
 * adjust_lengths reaches this with pos == -1 (a punctuation phoneme at
 * position 0 walks the cursor off the front), and Python quietly writes
 * the LAST element. Dropping that write, or clamping it to 0, changes
 * the rendered length of any utterance that opens with punctuation.
 *
 * An index still out of range after the wrap would be an IndexError in
 * Python, which parse() does not catch - the program would stop. No
 * input reaches it: verify_parser.py runs the whole dictionary and the
 * punctuation corpus through both implementations and they agree, which
 * is the evidence for that claim rather than the argument above.
 */
static void py_set(int *row, int count, int pos, int value)
{
    if (pos < 0) {
        pos += count;
    }
    if (pos < 0 || pos >= count) {
        return;
    }
    row[pos] = value;
}

/* Reads are bounds-checked in Python and yield None / 0 off the ends. */

static int get_phoneme(const sam_plist_t *pl, int pos)
{
    return (pos >= 0 && pos < pl->count) ? pl->phoneme[pos] : SAM_NO_PHONEME;
}

static int get_stress(const sam_plist_t *pl, int pos)
{
    return (pos >= 0 && pos < pl->count) ? pl->stress[pos] : 0;
}

static int get_length(const sam_plist_t *pl, int pos)
{
    return (pos >= 0 && pos < pl->count) ? pl->length[pos] : 0;
}

static void set_phoneme(sam_plist_t *pl, int pos, int value)
{
    py_set(pl->phoneme, pl->count, pos, value);
}

static void set_length(sam_plist_t *pl, int pos, int value)
{
    py_set(pl->length, pl->count, pos, value);
}

static void set_stress(sam_plist_t *pl, int pos, int value)
{
    py_set(pl->stress, pl->count, pos, value);
}

/* SAM_NO_PHONEME is negative, so this is false for it, as it is for None. */
static int has_flag(int phoneme, int flag)
{
    if (phoneme < 0 || phoneme >= SAM_PHONEME_NAME_COUNT) {
        return 0;
    }
    return (sam_phoneme_flags[phoneme] & flag) != 0;
}

/* --------------------------------------------------------------------- */
/* parser1 - phoneme string to indices                                   */
/* --------------------------------------------------------------------- */

/*
 * Python builds `target = sign1 + sign2` and compares it with each name.
 * When sign2 is empty the target is one character and can never equal a
 * two-character name, so the whole two-character pass is skipped.
 */
static int full_match(char sign1, char sign2)
{
    int i;

    if (sign2 == '\0') {
        return -1;
    }
    for (i = 0; i < SAM_PHONEME_NAME_COUNT; i++) {
        const char *name = sam_phoneme_names[i];
        if (name[0] == sign1 && name[1] == sign2 && name[1] != '*') {
            return i;
        }
    }
    return -1;
}

static int single_match(char sign1)
{
    int i;

    for (i = 0; i < SAM_PHONEME_NAME_COUNT; i++) {
        const char *name = sam_phoneme_names[i];
        if (name[0] == sign1 && name[1] == '*') {
            return i;
        }
    }
    return -1;
}

static int parser1(const char *input, sam_plist_t *pl)
{
    int len = (int)strlen(input);
    int src = 0;

    while (src < len) {
        char sign1 = input[src];
        char sign2 = (src + 1 < len) ? input[src + 1] : '\0';
        int match = full_match(sign1, sign2);

        if (match >= 0) {
            src += 2;
            if (plist_append(pl, match) != 0) {
                return -1;
            }
            continue;
        }

        match = single_match(sign1);
        if (match >= 0) {
            src += 1;
            if (plist_append(pl, match) != 0) {
                return -1;
            }
            continue;
        }

        /* Must be a stress digit; index 0 of the table is '*', which
         * single_match already consumed, so reaching 0 is the failure. */
        match = SAM_STRESS_COUNT - 1;
        while (match > 0 && sign1 != sam_stress_chars[match]) {
            match--;
        }
        if (match == 0) {
            return -1;   /* Python raises ValueError; parse() returns False */
        }
        if (pl->count > 0) {
            pl->stress[pl->count - 1] = match;
        }
        src += 1;
    }
    return 0;
}

/* --------------------------------------------------------------------- */
/* parser2 - phoneme rewriting                                           */
/* --------------------------------------------------------------------- */

static int handle_uw_ch_j(sam_plist_t *pl, int phoneme, int pos)
{
    if (phoneme == 53) {            /* UW after an alveolar becomes UX */
        if (has_flag(get_phoneme(pl, pos - 1), FLAG_ALVEOLAR)) {
            set_phoneme(pl, pos, 16);
        }
    } else if (phoneme == 42) {     /* CH */
        return plist_insert(pl, pos + 1, 43, get_stress(pl, pos), 0);
    } else if (phoneme == 44) {     /* J* */
        return plist_insert(pl, pos + 1, 45, get_stress(pl, pos), 0);
    }
    return 0;
}

static int change_ax(sam_plist_t *pl, int position, int suffix)
{
    set_phoneme(pl, position, 13);   /* AX */
    return plist_insert(pl, position + 1, suffix, get_stress(pl, position), 0);
}

static int parser2(sam_plist_t *pl)
{
    int pos = -1;

    for (;;) {
        int phoneme, prior;

        pos++;
        phoneme = get_phoneme(pl, pos);
        if (phoneme == SAM_NO_PHONEME) {
            break;
        }
        if (phoneme == 0) {
            continue;   /* pause */
        }

        if (has_flag(phoneme, FLAG_DIPHTHONG)) {
            int suffix = has_flag(phoneme, FLAG_DIP_YX) ? 21 : 20;
            if (plist_insert(pl, pos + 1, suffix, get_stress(pl, pos), 0) != 0) {
                return -1;
            }
            if (handle_uw_ch_j(pl, phoneme, pos) != 0) {
                return -1;
            }
            continue;
        }

        if (phoneme == 78) {                    /* UL -> AX L* */
            if (change_ax(pl, pos, 24) != 0) {
                return -1;
            }
            continue;
        }
        if (phoneme == 79) {                    /* UM -> AX M* */
            if (change_ax(pl, pos, 27) != 0) {
                return -1;
            }
            continue;
        }
        if (phoneme == 80) {                    /* UN -> AX N* */
            if (change_ax(pl, pos, 28) != 0) {
                return -1;
            }
            continue;
        }

        /* <STRESSED VOWEL> <SILENCE> <STRESSED VOWEL> gets a Q between. */
        if (has_flag(phoneme, FLAG_VOWEL) && get_stress(pl, pos)) {
            if (get_phoneme(pl, pos + 1) == 0) {
                int next = get_phoneme(pl, pos + 2);
                if (next != SAM_NO_PHONEME && has_flag(next, FLAG_VOWEL)) {
                    if (get_stress(pl, pos + 2)) {
                        if (plist_insert(pl, pos + 2, 31, 0, 0) != 0) {
                            return -1;
                        }
                    }
                }
            }
            continue;
        }

        prior = (pos > 0) ? get_phoneme(pl, pos - 1) : SAM_NO_PHONEME;

        if (phoneme == pR) {
            if (prior == pT) {
                set_phoneme(pl, pos - 1, 42);        /* T R -> CH R */
            } else if (prior == pD) {
                set_phoneme(pl, pos - 1, 44);        /* D R -> J R  */
            } else if (has_flag(prior, FLAG_VOWEL)) {
                set_phoneme(pl, pos, 18);            /* <VOWEL> R -> RX */
            }
            continue;
        }

        if (phoneme == 24 && has_flag(prior, FLAG_VOWEL)) {
            set_phoneme(pl, pos, 19);                /* <VOWEL> L -> LX */
            continue;
        }

        if (prior == 60 && phoneme == 32) {
            set_phoneme(pl, pos, 38);                /* G S -> G Z */
            continue;
        }

        if (phoneme == 60) {
            int next = get_phoneme(pl, pos + 1);
            if (!has_flag(next, FLAG_DIP_YX) && next != SAM_NO_PHONEME) {
                set_phoneme(pl, pos, 63);            /* G* -> GX */
            }
            continue;
        }

        /*
         * The K* test is the mirror of the G* one with `and not None`
         * turned into `or is None`, so a trailing K becomes KX where a
         * trailing G stays G. That asymmetry is in the Python and in the
         * JavaScript it was ported from; it is kept.
         */
        if (phoneme == 72) {
            int next = get_phoneme(pl, pos + 1);
            if (!has_flag(next, FLAG_DIP_YX) || next == SAM_NO_PHONEME) {
                set_phoneme(pl, pos, 75);            /* K* -> KX */
                phoneme = 75;
            }
            /* deliberately falls through */
        }

        if (has_flag(phoneme, FLAG_UNVOICED_STOPCONS) && prior == 32) {
            set_phoneme(pl, pos, phoneme - 12);      /* soften after S* */
        } else if (!has_flag(phoneme, FLAG_UNVOICED_STOPCONS)) {
            if (handle_uw_ch_j(pl, phoneme, pos) != 0) {
                return -1;
            }
        }

        if (phoneme == 69 || phoneme == 57) {        /* T* / D* -> DX */
            if (pos > 0 && has_flag(get_phoneme(pl, pos - 1), FLAG_VOWEL)) {
                int next = get_phoneme(pl, pos + 1);
                if (next == 0) {
                    next = get_phoneme(pl, pos + 2);
                }
                if (has_flag(next, FLAG_VOWEL) && !get_stress(pl, pos + 1)) {
                    set_phoneme(pl, pos, 30);
                }
            }
            continue;
        }
    }
    return 0;
}

/* --------------------------------------------------------------------- */
/* copy_stress, set_phoneme_length                                       */
/* --------------------------------------------------------------------- */

static void copy_stress(sam_plist_t *pl)
{
    int position = 0;

    for (;;) {
        int phoneme = get_phoneme(pl, position);

        if (phoneme == SAM_NO_PHONEME) {
            break;
        }
        if (has_flag(phoneme, FLAG_CONSONANT)) {
            int next = get_phoneme(pl, position + 1);
            if (next != SAM_NO_PHONEME && has_flag(next, FLAG_VOWEL)) {
                int stress = get_stress(pl, position + 1);
                if (stress != 0 && stress < 0x80) {
                    set_stress(pl, position, stress + 1);
                }
            }
        }
        position++;
    }
}

static void set_phoneme_length(sam_plist_t *pl)
{
    int position = 0;

    for (;;) {
        int phoneme = get_phoneme(pl, position);
        int stress, length;

        if (phoneme == SAM_NO_PHONEME) {
            break;
        }
        stress = get_stress(pl, position);

        if (phoneme >= 0 && phoneme < SAM_PHONEME_LENGTH_COUNT) {
            if (stress == 0 || stress > 0x7F) {
                length = sam_phoneme_length_combined[phoneme] & 0xFF;
            } else {
                length = sam_phoneme_length_combined[phoneme] >> 8;
            }
        } else {
            /* Python would raise IndexError here: the length table has 80
             * entries against 81 phonemes. Only UN (80) is missing and
             * parser2 has already rewritten it to AX N*, so this is
             * unreachable - verify_parser.py is what says so. */
            length = 0;
        }

        set_length(pl, position, length);
        position++;
    }
}

/* --------------------------------------------------------------------- */
/* adjust_lengths                                                        */
/* --------------------------------------------------------------------- */

static void adjust_lengths(sam_plist_t *pl)
{
    int position = 0;
    int loop_index;

    /* Lengthen everything from the last vowel up to a punctuation mark. */
    while (get_phoneme(pl, position) != SAM_NO_PHONEME) {
        if (!has_flag(get_phoneme(pl, position), FLAG_PUNCT)) {
            position++;
            continue;
        }

        loop_index = position;
        position--;
        while (position > 1
               && !has_flag(get_phoneme(pl, position), FLAG_VOWEL)) {
            position--;
        }
        if (position == 0) {
            break;
        }

        /* position is -1 when the punctuation is the first phoneme, and
         * the write below then lands on the last element. See py_set(). */
        while (position < loop_index) {
            int phoneme = get_phoneme(pl, position);
            if (!has_flag(phoneme, FLAG_FRICATIVE)
                || has_flag(phoneme, FLAG_VOICED)) {
                int length = get_length(pl, position);
                set_length(pl, position, (length >> 1) + length + 1);
            }
            position++;
        }
        position = loop_index + 1;
    }

    loop_index = -1;
    for (;;) {
        int phoneme;

        loop_index++;
        phoneme = get_phoneme(pl, loop_index);
        if (phoneme == SAM_NO_PHONEME) {
            break;
        }
        position = loop_index;

        if (has_flag(phoneme, FLAG_VOWEL)) {
            int next, flags, length;

            position++;
            next = get_phoneme(pl, position);

            if (!has_flag(next, FLAG_CONSONANT)) {
                /* <VOWEL> <RX|LX> <CONSONANT> shortens the vowel by one. */
                if (next == 18 || next == 19) {
                    position++;
                    if (has_flag(get_phoneme(pl, position), FLAG_CONSONANT)) {
                        set_length(pl, loop_index,
                                   get_length(pl, loop_index) - 1);
                    }
                }
                continue;
            }

            flags = (next != SAM_NO_PHONEME)
                    ? sam_phoneme_flags[next]
                    : (FLAG_CONSONANT | FLAG_UNVOICED_STOPCONS);

            if ((flags & FLAG_VOICED) == 0) {
                if ((flags & FLAG_UNVOICED_STOPCONS) != 0) {
                    /* <VOWEL> <UNVOICED PLOSIVE>: down by an eighth. */
                    length = get_length(pl, loop_index);
                    set_length(pl, loop_index, length - (length >> 3));
                }
                continue;
            }

            /* <VOWEL> <VOICED CONSONANT>: up by a quarter plus one. */
            length = get_length(pl, loop_index);
            set_length(pl, loop_index, (length >> 2) + length + 1);
            continue;
        }

        if (has_flag(phoneme, FLAG_NASAL)) {
            int next;

            position++;
            next = get_phoneme(pl, position);
            if (next != SAM_NO_PHONEME && has_flag(next, FLAG_STOPCONS)) {
                set_length(pl, position, 6);
                set_length(pl, position - 1, 5);
            }
            continue;
        }

        if (has_flag(phoneme, FLAG_STOPCONS)) {
            int next;

            position++;
            while (get_phoneme(pl, position) == 0) {
                position++;
            }
            next = get_phoneme(pl, position);
            if (next != SAM_NO_PHONEME && has_flag(next, FLAG_STOPCONS)) {
                set_length(pl, position, (get_length(pl, position) >> 1) + 1);
                set_length(pl, loop_index,
                           (get_length(pl, loop_index) >> 1) + 1);
            }
            continue;
        }

        if (position > 0 && has_flag(phoneme, FLAG_LIQUID)) {
            if (has_flag(get_phoneme(pl, position - 1), FLAG_STOPCONS)) {
                set_length(pl, position, get_length(pl, position) - 2);
            }
        }
    }
}

/* --------------------------------------------------------------------- */
/* prolong_plosive_stop_consonants                                       */
/* --------------------------------------------------------------------- */

static int prolong_plosive_stop_consonants(sam_plist_t *pl)
{
    int pos = -1;

    for (;;) {
        int index, length1, length2;

        pos++;
        index = get_phoneme(pl, pos);
        if (index == SAM_NO_PHONEME) {
            break;
        }
        if (!has_flag(index, FLAG_STOPCONS)) {
            continue;
        }

        if (has_flag(index, FLAG_UNVOICED_STOPCONS)) {
            int x = pos;
            int next;

            for (;;) {
                x++;
                next = get_phoneme(pl, x);
                if (next != 0) {
                    break;
                }
            }
            if (next != SAM_NO_PHONEME) {
                if (has_flag(next, FLAG_0008) || next == 36 || next == 37) {
                    continue;
                }
            }
        }

        length1 = (index + 1 < SAM_PHONEME_LENGTH_COUNT)
                  ? (sam_phoneme_length_combined[index + 1] & 0xFF) : 0;
        length2 = (index + 2 < SAM_PHONEME_LENGTH_COUNT)
                  ? (sam_phoneme_length_combined[index + 2] & 0xFF) : 0;

        if (plist_insert(pl, pos + 1, index + 1, get_stress(pl, pos),
                         length1) != 0) {
            return -1;
        }
        if (plist_insert(pl, pos + 2, index + 2, get_stress(pl, pos),
                         length2) != 0) {
            return -1;
        }
        pos += 2;
    }
    return 0;
}

/* --------------------------------------------------------------------- */
/* parse                                                                 */
/* --------------------------------------------------------------------- */

int sam_parse_phonemes(const char *input, sam_plist_t *pl)
{
    int i, out;

    sam_plist_init(pl);
    if (input == NULL || input[0] == '\0') {
        return -1;   /* Python: `if not input_str: return False` */
    }

    if (parser1(input, pl) != 0) {
        sam_plist_free(pl);
        return -1;
    }
    if (parser2(pl) != 0) {
        sam_plist_free(pl);
        return -1;
    }

    copy_stress(pl);
    set_phoneme_length(pl);
    adjust_lengths(pl);

    if (prolong_plosive_stop_consonants(pl) != 0) {
        sam_plist_free(pl);
        return -1;
    }

    /* Python's final `if phoneme:` drops the pauses. */
    out = 0;
    for (i = 0; i < pl->count; i++) {
        if (pl->phoneme[i] != 0) {
            pl->phoneme[out] = pl->phoneme[i];
            pl->length[out] = pl->length[i];
            pl->stress[out] = pl->stress[i];
            out++;
        }
    }
    pl->count = out;
    return 0;
}
