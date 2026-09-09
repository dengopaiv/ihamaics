/*
 * sam_reciter.c - rules-based text to phonemes. Port of
 * _rule_based_phonemes() and ReciterRule in
 * nvda-addon/synthDrivers/sam/reciter.py.
 *
 * Two things about the Python drive the shape of this file.
 *
 * It leans on slice semantics: `text[pos:pos+2] == 'CH'` is false rather
 * than an error when fewer than two characters remain, and the guards
 * around those slices are not uniform. Each one is reproduced with the
 * bound the slice implied, not with a bound that looks tidier.
 *
 * And the driving loop does not advance the cursor when no rule matches,
 * so it relies on an iteration cap to terminate. The cap is part of the
 * output for any input that reaches it, so it is kept at the same value.
 */

#include <stdlib.h>
#include <string.h>

#include "sam_frontend.h"

/* Character flags, from the comments in reciter_tables.py. */
#define FLAG_NUMERIC        0x01
#define FLAG_RULESET2       0x02
#define FLAG_VOICED         0x04
#define FLAG_0X08           0x08
#define FLAG_DIPHTHONG      0x10
#define FLAG_CONSONANT      0x20
#define FLAG_VOWEL_OR_Y     0x40
#define FLAG_ALPHA_OR_QUOT  0x80

/* Python's `while input_pos < len(text) and iteration_count < 10000`. */
#define MAX_ITERATIONS 10000

static int chflags(char c, int flg)
{
    return (sam_char_flags[(unsigned char)c] & flg) != 0;
}

static int flags_at(const char *text, int len, int pos, int flg)
{
    if (pos < 0 || pos >= len) {
        return 0;
    }
    return chflags(text[pos], flg);
}

/* text[pos:pos+n] == lit, with Python's clamping on a short slice. */
static int slice_eq(const char *text, int len, int pos, const char *lit, int n)
{
    if (pos < 0 || pos + n > len) {
        return 0;
    }
    return memcmp(text + pos, lit, (size_t)n) == 0;
}

static int is_eiy(char c)
{
    return c == 'E' || c == 'I' || c == 'Y';
}

/* --------------------------------------------------------------------- */
/* Rule prefix                                                           */
/* --------------------------------------------------------------------- */

static int check_prefix(const sam_rule_t *r, const char *text, int len, int pos)
{
    int rule_pos;
    int pre_len = (int)strlen(r->pre);

    for (rule_pos = pre_len - 1; rule_pos >= 0; rule_pos--) {
        char rule_byte = r->pre[rule_pos];

        if (chflags(rule_byte, FLAG_ALPHA_OR_QUOT)) {
            pos--;
            if (pos < 0 || text[pos] != rule_byte) {
                return 0;
            }
            continue;
        }

        switch (rule_byte) {
        case ' ':   /* not alpha or quote */
            pos--;
            if (flags_at(text, len, pos, FLAG_ALPHA_OR_QUOT)) {
                return 0;
            }
            break;

        case '#':   /* vowel or Y */
            pos--;
            if (!flags_at(text, len, pos, FLAG_VOWEL_OR_Y)) {
                return 0;
            }
            break;

        case '.':
            pos--;
            if (!flags_at(text, len, pos, FLAG_0X08)) {
                return 0;
            }
            break;

        case '&':   /* diphthong, or the digraphs CH / SH */
            pos--;
            if (!flags_at(text, len, pos, FLAG_DIPHTHONG)) {
                pos--;
                if (!(pos >= 0 && (slice_eq(text, len, pos, "CH", 2)
                                   || slice_eq(text, len, pos, "SH", 2)))) {
                    return 0;
                }
            }
            break;

        case '@':
            /*
             * "Voiced and not H" - except the H branch always fails,
             * because it tests the character it just established is 'H'
             * for membership of [T, C, S]. The JavaScript this was ported
             * from has the same shape. Reproduced, not repaired: fixing
             * it here would change the pronunciation of every word the
             * rule touches, which is a decision about the voice.
             */
            pos--;
            if (!flags_at(text, len, pos, FLAG_VOICED)) {
                return 0;
            }
            break;

        case '^':   /* consonant */
            pos--;
            if (!flags_at(text, len, pos, FLAG_CONSONANT)) {
                return 0;
            }
            break;

        case '+':   /* E, I or Y */
            pos--;
            if (pos < 0 || pos >= len || !is_eiy(text[pos])) {
                return 0;
            }
            break;

        case ':':   /* walk left over consonants */
            while (pos >= 0 && flags_at(text, len, pos - 1, FLAG_CONSONANT)) {
                pos--;
            }
            break;

        default:
            return 0;
        }
    }
    return 1;
}

/* --------------------------------------------------------------------- */
/* Rule suffix                                                           */
/* --------------------------------------------------------------------- */

static int check_suffix(const sam_rule_t *r, const char *text, int len, int pos)
{
    int rule_pos;
    int post_len = (int)strlen(r->post);

    for (rule_pos = 0; rule_pos < post_len; rule_pos++) {
        char rule_byte = r->post[rule_pos];

        if (chflags(rule_byte, FLAG_ALPHA_OR_QUOT)) {
            pos++;
            if (pos >= len || text[pos] != rule_byte) {
                return 0;
            }
            continue;
        }

        switch (rule_byte) {
        case ' ':
            pos++;
            if (flags_at(text, len, pos, FLAG_ALPHA_OR_QUOT)) {
                return 0;
            }
            break;

        case '#':
            pos++;
            if (!flags_at(text, len, pos, FLAG_VOWEL_OR_Y)) {
                return 0;
            }
            break;

        case '.':
            pos++;
            if (!flags_at(text, len, pos, FLAG_0X08)) {
                return 0;
            }
            break;

        case '&':
            /* Mirror of the prefix case, and the digraphs are reversed
             * because it reads back from the character after pos. */
            pos++;
            if (!flags_at(text, len, pos, FLAG_DIPHTHONG)) {
                pos++;
                if (!(pos >= 2 && slice_eq(text, len, pos - 1, "HC", 2))
                    && !(pos >= 2 && slice_eq(text, len, pos - 1, "HS", 2))) {
                    return 0;
                }
            }
            break;

        case '@':   /* the same always-false H branch as check_prefix */
            pos++;
            if (!flags_at(text, len, pos, FLAG_VOICED)) {
                return 0;
            }
            break;

        case '^':
            pos++;
            if (!flags_at(text, len, pos, FLAG_CONSONANT)) {
                return 0;
            }
            break;

        case '+':
            pos++;
            if (pos >= len || !is_eiy(text[pos])) {
                return 0;
            }
            break;

        case ':':
            while (flags_at(text, len, pos + 1, FLAG_CONSONANT)) {
                pos++;
            }
            break;

        case '%':   /* ING, E, ER/ES/ED, ELY, EFUL */
            if (pos + 1 >= len) {
                return 0;
            }
            if (text[pos + 1] != 'E') {
                if (slice_eq(text, len, pos + 1, "ING", 3)) {
                    pos += 3;
                } else {
                    return 0;
                }
            } else if (!flags_at(text, len, pos + 2, FLAG_ALPHA_OR_QUOT)) {
                pos += 1;
            } else if (pos + 2 < len && (text[pos + 2] == 'R'
                                         || text[pos + 2] == 'S'
                                         || text[pos + 2] == 'D')) {
                pos += 2;
            } else if (pos + 2 < len && text[pos + 2] == 'L') {
                if (pos + 3 < len && text[pos + 3] == 'Y') {
                    pos += 3;
                } else {
                    return 0;
                }
            } else if (slice_eq(text, len, pos + 2, "FUL", 3)) {
                pos += 4;
            } else {
                return 0;
            }
            break;

        default:
            return 0;
        }
    }
    return 1;
}

static int rule_matches(const sam_rule_t *r, const char *text, int len, int pos)
{
    if (!slice_eq(text, len, pos, r->match, r->match_len)) {
        return 0;
    }
    if (!check_prefix(r, text, len, pos)) {
        return 0;
    }
    return check_suffix(r, text, len, pos + r->match_len - 1);
}

/* --------------------------------------------------------------------- */
/* The driving loop                                                      */
/* --------------------------------------------------------------------- */

/*
 * Try each rule in a list; on the first match append its target and
 * advance the cursor. Returns 1 if a rule fired, 0 if none did - in
 * which case the cursor does not move, exactly as in Python.
 */
static int apply_rules(const sam_rule_t *rules, int count,
                       const char *text, int len, int *pos,
                       char *out, int out_capacity, int *out_len)
{
    int i;

    for (i = 0; i < count; i++) {
        const sam_rule_t *r = &rules[i];
        int target_len;

        if (!rule_matches(r, text, len, *pos)) {
            continue;
        }
        target_len = (int)strlen(r->target);
        if (*out_len + target_len >= out_capacity) {
            return -1;
        }
        memcpy(out + *out_len, r->target, (size_t)target_len);
        *out_len += target_len;
        *pos += r->match_len;
        return 1;
    }
    return 0;
}

int sam_reciter_rules(const char *input, char *out, int out_capacity)
{
    /*
     * Python builds `' ' + input_text.upper()`. Only A-Z are uppercased
     * here: every byte outside ASCII has a character flag of zero either
     * way, so it becomes a space in both implementations regardless of
     * case. The exceptions are the handful of characters whose Unicode
     * uppercase is ASCII and longer than one character - 'ss' for
     * example - which Python would expand and this does not. Nothing the
     * reciter can pronounce is in that set; see docs/native-gui.md.
     */
    int in_len, len, pos = 0, out_len = 0, iterations = 0;
    char *text;
    int i;
    char stackbuf[512];
    char *heap = NULL;

    if (input == NULL || out == NULL || out_capacity <= 0) {
        return -1;
    }

    in_len = (int)strlen(input);
    len = in_len + 1;

    if (len < (int)sizeof(stackbuf)) {
        text = stackbuf;
    } else {
        heap = (char *)malloc((size_t)len + 1);
        if (heap == NULL) {
            return -1;
        }
        text = heap;
    }

    text[0] = ' ';
    for (i = 0; i < in_len; i++) {
        char c = input[i];
        text[i + 1] = (c >= 'a' && c <= 'z') ? (char)(c - 'a' + 'A') : c;
    }
    text[len] = '\0';

    while (pos < len && iterations < MAX_ITERATIONS) {
        char current = text[pos];
        int fired;

        iterations++;

        /* A '.' that is not followed by a digit is spoken as a full stop
         * rather than run through the rules. */
        if (current == '.' && !flags_at(text, len, pos + 1, FLAG_NUMERIC)) {
            if (out_len + 1 >= out_capacity) {
                goto fail;
            }
            out[out_len++] = '.';
            pos++;
            continue;
        }

        if (chflags(current, FLAG_RULESET2)) {
            fired = apply_rules(sam_rules2, SAM_RULE2_COUNT, text, len, &pos,
                                out, out_capacity, &out_len);
            if (fired < 0) {
                goto fail;
            }
            continue;
        }

        if (sam_char_flags[(unsigned char)current] != 0) {
            if (!chflags(current, FLAG_ALPHA_OR_QUOT)) {
                goto fail;   /* Python returns False */
            }
            fired = apply_rules(sam_rules + sam_rule_off[(unsigned char)current],
                                sam_rule_cnt[(unsigned char)current],
                                text, len, &pos, out, out_capacity, &out_len);
            if (fired < 0) {
                goto fail;
            }
            continue;
        }

        if (out_len + 1 >= out_capacity) {
            goto fail;
        }
        out[out_len++] = ' ';
        pos++;
    }

    out[out_len] = '\0';
    free(heap);
    return out_len;

fail:
    free(heap);
    return -1;
}
