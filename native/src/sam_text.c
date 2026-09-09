/*
 * sam_text.c - the front end: dictionary lookup, number expansion, the
 * text pipeline, and the public entry points in include/sam_text.h.
 *
 * Ports cmudict.py, expand_numbers() and text_to_phonemes() from
 * nvda-addon/synthDrivers/sam/. The rule engine lives in sam_reciter.c
 * and the phoneme parser in sam_parser.c.
 *
 * Two decisions worth stating up front.
 *
 * Numbers are converted from their decimal digits rather than from an
 * integer. Python's int is unbounded and _number_to_words() recurses on
 * n // 1000000, so "one million million" is a reachable answer; no C
 * integer type reproduces that. Splitting the digit string at the same
 * places gives the same words for any length of input.
 *
 * The dictionary blob is borrowed, never owned. The GUI passes a pointer
 * into its own resources and the test tools pass a pointer into a file
 * they read; nothing here copies or frees it.
 */

#include <stdlib.h>
#include <string.h>

#include "sam_text.h"
#include "sam_frontend.h"
#include "sam_cmudict_tables.h"

/* Must match MAGIC in native/tools/gen_dict.py. */
static const unsigned char DICT_MAGIC[8] = {
    'S', 'A', 'M', 'D', 'I', 'C', 0x00, 0x01
};
#define DICT_HEADER_LEN 16

/* --------------------------------------------------------------------- */
/* A growable string                                                     */
/* --------------------------------------------------------------------- */

typedef struct {
    char *p;
    int   len;
    int   cap;
    int   failed;   /* sticky, so callers can check once at the end */
} strbuf_t;

static void sb_init(strbuf_t *sb)
{
    memset(sb, 0, sizeof(*sb));
}

static void sb_free(strbuf_t *sb)
{
    free(sb->p);
    memset(sb, 0, sizeof(*sb));
}

static int sb_reserve(strbuf_t *sb, int need)
{
    int cap = sb->cap;
    char *p;

    if (sb->failed) {
        return -1;
    }
    if (need <= cap) {
        return 0;
    }
    if (cap == 0) {
        cap = 128;
    }
    while (cap < need) {
        cap *= 2;
    }
    p = (char *)realloc(sb->p, (size_t)cap);
    if (p == NULL) {
        sb->failed = 1;
        return -1;
    }
    sb->p = p;
    sb->cap = cap;
    return 0;
}

static int sb_put(strbuf_t *sb, const char *s, int n)
{
    if (n <= 0) {
        return sb->failed ? -1 : 0;
    }
    if (sb_reserve(sb, sb->len + n + 1) != 0) {
        return -1;
    }
    memcpy(sb->p + sb->len, s, (size_t)n);
    sb->len += n;
    sb->p[sb->len] = '\0';
    return 0;
}

static int sb_puts(strbuf_t *sb, const char *s)
{
    return sb_put(sb, s, (int)strlen(s));
}

static int sb_putc(strbuf_t *sb, char c)
{
    return sb_put(sb, &c, 1);
}

/* An empty strbuf has never allocated, so p may be NULL. */
static const char *sb_str(const strbuf_t *sb)
{
    return sb->p != NULL ? sb->p : "";
}

/*
 * Hand a finished string to a caller-allocated buffer under the
 * out == NULL convention: return the length either way, and only copy
 * when there is somewhere to copy to.
 */
static int emit(const strbuf_t *sb, char *out, int out_capacity)
{
    if (sb->failed) {
        return -1;
    }
    if (out == NULL) {
        return sb->len;
    }
    if (out_capacity <= sb->len) {
        return -1;
    }
    memcpy(out, sb_str(sb), (size_t)sb->len);
    out[sb->len] = '\0';
    return sb->len;
}

/* --------------------------------------------------------------------- */
/* The dictionary blob                                                   */
/* --------------------------------------------------------------------- */

static unsigned read_u32(const unsigned char *p)
{
    /* Byte-wise: the blob may sit at any alignment in a resource. */
    return (unsigned)p[0] | ((unsigned)p[1] << 8)
           | ((unsigned)p[2] << 16) | ((unsigned)p[3] << 24);
}

typedef struct {
    const unsigned char *offsets;   /* count * 4 bytes, little-endian */
    const char          *pool;
    unsigned             count;
    unsigned             pool_len;
} dict_t;

static int dict_open(const void *dict, int dict_len, dict_t *d)
{
    const unsigned char *b = (const unsigned char *)dict;

    if (dict == NULL || dict_len < DICT_HEADER_LEN) {
        return -1;
    }
    if (memcmp(b, DICT_MAGIC, sizeof(DICT_MAGIC)) != 0) {
        return -1;
    }
    d->count = read_u32(b + 8);
    d->pool_len = read_u32(b + 12);

    /* Every arithmetic step here is in unsigned 64-bit so a corrupt
     * header cannot wrap the bounds check it is being checked against. */
    {
        unsigned long long need = (unsigned long long)DICT_HEADER_LEN
                                  + (unsigned long long)d->count * 4u
                                  + (unsigned long long)d->pool_len;
        if (need > (unsigned long long)dict_len) {
            return -1;
        }
    }
    if (d->count == 0 || d->pool_len == 0) {
        return -1;
    }
    d->offsets = b + DICT_HEADER_LEN;
    d->pool = (const char *)(d->offsets + (size_t)d->count * 4u);

    /* The pool must end on a NUL or a lookup could run off the end. */
    if (d->pool[d->pool_len - 1] != '\0') {
        return -1;
    }
    return 0;
}

static const char *dict_word_at(const dict_t *d, unsigned i)
{
    unsigned off = read_u32(d->offsets + (size_t)i * 4u);

    if (off >= d->pool_len) {
        return NULL;
    }
    return d->pool + off;
}

/* Unsigned comparison, so the ordering matches the one gen_dict.py checked. */
static int word_cmp(const char *a, const char *b)
{
    const unsigned char *x = (const unsigned char *)a;
    const unsigned char *y = (const unsigned char *)b;

    while (*x != '\0' && *x == *y) {
        x++;
        y++;
    }
    return (int)*x - (int)*y;
}

const char *sam_dict_lookup(const void *dict, int dict_len,
                            const char *word, int *out_len)
{
    dict_t d;
    unsigned lo, hi;

    if (word == NULL || word[0] == '\0') {
        return NULL;
    }
    if (dict_open(dict, dict_len, &d) != 0) {
        return NULL;
    }

    lo = 0;
    hi = d.count;
    while (lo < hi) {
        unsigned mid = lo + (hi - lo) / 2;
        const char *key = dict_word_at(&d, mid);
        int c;

        if (key == NULL) {
            return NULL;
        }
        c = word_cmp(key, word);
        if (c == 0) {
            const char *pron = key + strlen(key) + 1;
            size_t used = (size_t)(pron - d.pool);

            if (used >= d.pool_len) {
                return NULL;
            }
            if (out_len != NULL) {
                *out_len = (int)strlen(pron);
            }
            return pron;
        }
        if (c < 0) {
            lo = mid + 1;
        } else {
            hi = mid;
        }
    }
    return NULL;
}

/* --------------------------------------------------------------------- */
/* ARPABET to SAM                                                        */
/* --------------------------------------------------------------------- */

static const char *arpabet_sam(const char *base, int len)
{
    int lo = 0, hi = SAM_ARPABET_COUNT;

    while (lo < hi) {
        int mid = lo + (hi - lo) / 2;
        const char *k = sam_arpabet_map[mid].arpabet;
        int klen = (int)strlen(k);
        int n = (len < klen) ? len : klen;
        int c = memcmp(k, base, (size_t)n);

        if (c == 0) {
            c = klen - len;
        }
        if (c == 0) {
            return sam_arpabet_map[mid].sam;
        }
        if (c < 0) {
            lo = mid + 1;
        } else {
            hi = mid;
        }
    }
    return NULL;   /* Python's .get(base, base): the caller emits base */
}

static int arpabet_to_sam_buf(const char *arp, int arp_len, strbuf_t *sb)
{
    int i = 0;

    while (i < arp_len) {
        int start, end, stress = -1;
        const char *mapped;

        while (i < arp_len && arp[i] == ' ') {
            i++;
        }
        if (i >= arp_len) {
            break;
        }
        start = i;
        while (i < arp_len && arp[i] != ' ') {
            i++;
        }
        end = i;

        /* A trailing 0, 1 or 2 is the stress digit, not the phoneme. */
        if (end > start) {
            char last = arp[end - 1];
            if (last == '0' || last == '1' || last == '2') {
                stress = last - '0';
                end--;
            }
        }

        /*
         * An unmapped token is emitted verbatim, because Python's
         * ARPABET_TO_SAM.get(base, base) falls back to the key. That is
         * how the sixteen dictionary entries carrying a trailing
         * "# place, danish" comment end up with phonemes the parser
         * cannot read. See docs/native-gui.md.
         */
        mapped = arpabet_sam(arp + start, end - start);
        if (mapped != NULL) {
            if (sb_puts(sb, mapped) != 0) {
                return -1;
            }
        } else if (sb_put(sb, arp + start, end - start) != 0) {
            return -1;
        }

        if (stress >= 0 && sb_puts(sb, sam_stress_markers[stress]) != 0) {
            return -1;
        }
    }
    return 0;
}

int sam_arpabet_to_sam(const char *arp, int arp_len, char *out,
                       int out_capacity)
{
    strbuf_t sb;
    int rc;

    sb_init(&sb);
    if (arpabet_to_sam_buf(arp, arp_len, &sb) != 0) {
        sb_free(&sb);
        return -1;
    }
    rc = emit(&sb, out, out_capacity);
    sb_free(&sb);
    return rc;
}

/* --------------------------------------------------------------------- */
/* Numbers to words                                                      */
/* --------------------------------------------------------------------- */

static const char *const ONES[20] = {
    "", "one", "two", "three", "four", "five", "six", "seven", "eight",
    "nine", "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen",
    "sixteen", "seventeen", "eighteen", "nineteen"
};

static const char *const TENS[10] = {
    "", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy",
    "eighty", "ninety"
};

/* Drop leading zeros, leaving at least nothing at all for a pure-zero run. */
static void strip_zeros(const char **s, int *n)
{
    while (*n > 0 && **s == '0') {
        (*s)++;
        (*n)--;
    }
}

static int digits_to_words(const char *s, int n, strbuf_t *sb);

/* Append `word` to sb, with a separating space if sb already has parts. */
static int join(strbuf_t *sb, int *first, const char *word)
{
    if (!*first && sb_putc(sb, ' ') != 0) {
        return -1;
    }
    *first = 0;
    return sb_puts(sb, word);
}

static int join_digits(strbuf_t *sb, int *first, const char *s, int n)
{
    if (!*first && sb_putc(sb, ' ') != 0) {
        return -1;
    }
    *first = 0;
    return digits_to_words(s, n, sb);
}

/*
 * The port of _number_to_words(), working on decimal digits.
 *
 * n // 1000000 is the digits with the last six removed and n % 1000000 is
 * the last six, so every split Python does with arithmetic is a split of
 * the string here - and the recursion carries on past 10^9 the way
 * Python's does, giving "one million million" rather than overflowing.
 *
 * s must hold digits only, with no sign.
 */
static int digits_to_words(const char *s, int n, strbuf_t *sb)
{
    int first = 1;
    int value;

    strip_zeros(&s, &n);
    if (n == 0) {
        return sb_puts(sb, "zero");
    }

    if (n > 6) {                       /* n >= 1,000,000 */
        if (join_digits(sb, &first, s, n - 6) != 0) {
            return -1;
        }
        if (sb_puts(sb, " million") != 0) {
            return -1;
        }
        s += n - 6;
        n = 6;
        strip_zeros(&s, &n);
    }

    if (n > 3) {                       /* n >= 1,000 */
        if (join_digits(sb, &first, s, n - 3) != 0) {
            return -1;
        }
        if (sb_puts(sb, " thousand") != 0) {
            return -1;
        }
        s += n - 3;
        n = 3;
        strip_zeros(&s, &n);
    }

    if (n == 3) {                      /* n >= 100 */
        if (join(sb, &first, ONES[s[0] - '0']) != 0) {
            return -1;
        }
        if (sb_puts(sb, " hundred") != 0) {
            return -1;
        }
        s += 1;
        n = 2;
        strip_zeros(&s, &n);
    }

    value = 0;
    {
        int i;
        for (i = 0; i < n; i++) {
            value = value * 10 + (s[i] - '0');
        }
    }

    if (value >= 20) {
        if (join(sb, &first, TENS[value / 10]) != 0) {
            return -1;
        }
        if (value % 10 != 0) {
            if (sb_putc(sb, ' ') != 0 || sb_puts(sb, ONES[value % 10]) != 0) {
                return -1;
            }
        }
    } else if (value > 0) {
        if (join(sb, &first, ONES[value]) != 0) {
            return -1;
        }
    }
    return 0;
}

/* digits_to_words with an optional leading '-'. */
static int signed_to_words(const char *s, int n, strbuf_t *sb)
{
    int negative = 0;

    if (n > 0 && s[0] == '-') {
        negative = 1;
        s++;
        n--;
    }
    {
        const char *t = s;
        int m = n;
        strip_zeros(&t, &m);
        if (m == 0) {
            /* Python tests `n == 0` before `n < 0`, so "-0" is "zero". */
            return sb_puts(sb, "zero");
        }
    }
    if (negative && sb_puts(sb, "negative ") != 0) {
        return -1;
    }
    return digits_to_words(s, n, sb);
}

static int is_digit(char c)
{
    return c >= '0' && c <= '9';
}

/*
 * One match of Python's r'-?\d+\.?\d*' starting at i, or -1.
 *
 * The minus only counts when digits follow it: `-?` backtracks to empty
 * and `\d+` then fails on the '-' itself, so "-.5" yields a match on the
 * "5" alone and the "-." is left as literal text.
 */
static int match_number(const char *text, int len, int i)
{
    int j = i;

    if (j < len && text[j] == '-') {
        j++;
    }
    if (j >= len || !is_digit(text[j])) {
        return -1;
    }
    while (j < len && is_digit(text[j])) {
        j++;
    }
    if (j < len && text[j] == '.') {
        j++;
        while (j < len && is_digit(text[j])) {
            j++;
        }
    }
    return j;
}

static int expand_one(const char *num, int n, strbuf_t *sb)
{
    int dot = -1, k;

    for (k = 0; k < n; k++) {
        if (num[k] == '.') {
            dot = k;
            break;
        }
    }

    if (dot < 0) {
        return signed_to_words(num, n, sb);
    }

    if (signed_to_words(num, dot, sb) != 0) {
        return -1;
    }
    if (sb_puts(sb, " point") != 0) {
        return -1;
    }
    /* Digits after the point are read one at a time. */
    for (k = dot + 1; k < n; k++) {
        if (sb_putc(sb, ' ') != 0) {
            return -1;
        }
        if (digits_to_words(num + k, 1, sb) != 0) {
            return -1;
        }
    }
    return 0;
}

int sam_expand_numbers(const char *text, char *out, int out_capacity)
{
    strbuf_t sb;
    int len, i = 0, rc;

    if (text == NULL) {
        return -1;
    }
    len = (int)strlen(text);
    sb_init(&sb);

    while (i < len) {
        int end = match_number(text, len, i);

        if (end < 0) {
            if (sb_putc(&sb, text[i]) != 0) {
                sb_free(&sb);
                return -1;
            }
            i++;
            continue;
        }
        if (expand_one(text + i, end - i, &sb) != 0) {
            sb_free(&sb);
            return -1;
        }
        i = end;
    }

    rc = emit(&sb, out, out_capacity);
    sb_free(&sb);
    return rc;
}

/* --------------------------------------------------------------------- */
/* Text to phonemes                                                      */
/* --------------------------------------------------------------------- */

/* Python's str.strip() set. */
static int is_pyspace(char c)
{
    return c == ' ' || c == '\t' || c == '\n' || c == '\r'
           || c == '\v' || c == '\f';
}

/* The regex class [A-Za-z']. */
static int is_word_char(char c)
{
    return (c >= 'A' && c <= 'Z') || (c >= 'a' && c <= 'z') || c == '\'';
}

/* Run the rule engine over one token and append it stripped, if non-empty. */
static int append_rule_result(strbuf_t *sb, int *first,
                              const char *token, int token_len)
{
    char *buf;
    int cap, n, lo, hi;
    char *copy = (char *)malloc((size_t)token_len + 1);

    if (copy == NULL) {
        return -1;
    }
    memcpy(copy, token, (size_t)token_len);
    copy[token_len] = '\0';

    /* A rule can turn one character into fifteen; the slack covers the
     * longest target plus the terminator. */
    cap = token_len * 16 + 64;
    buf = (char *)malloc((size_t)cap);
    if (buf == NULL) {
        free(copy);
        return -1;
    }

    n = sam_reciter_rules(copy, buf, cap);
    free(copy);

    /*
     * Python:
     *
     *     rule_result = _rule_based_phonemes(token)
     *     if rule_result and rule_result is not False:
     *         result_parts.append(rule_result.strip())
     *
     * The truthiness test is on the UNSTRIPPED string and the value
     * appended is the stripped one, so a token of pure whitespace - the
     * space between two words, every time - contributes an empty part
     * that still takes a separator from the final ' '.join(). That is
     * why "RUN CORRESPONDINGLY" comes out with two spaces in it and not
     * one. Testing the stripped length here instead would drop the
     * second space and change every multi-word phoneme string.
     */
    if (n <= 0) {
        free(buf);          /* False, or '' - both are skipped */
        return 0;
    }

    lo = 0;
    hi = n;
    while (lo < hi && is_pyspace(buf[lo])) {
        lo++;
    }
    while (hi > lo && is_pyspace(buf[hi - 1])) {
        hi--;
    }

    if (!*first && sb_putc(sb, ' ') != 0) {
        free(buf);
        return -1;
    }
    *first = 0;
    if (sb_put(sb, buf + lo, hi - lo) != 0) {
        free(buf);
        return -1;
    }
    free(buf);
    return 0;
}

static int text_to_phonemes_buf(const char *text, const void *dict,
                                int dict_len, strbuf_t *sb)
{
    int len, i = 0, first = 1;
    dict_t probe;

    if (text == NULL) {
        return -1;
    }
    len = (int)strlen(text);
    if (len == 0) {
        return 0;   /* Python: `if not input_text: return ''` */
    }

    /*
     * Python takes the whole-string rule path when cmudict is not
     * importable, not a per-token one. A missing or unusable blob is the
     * same situation, so it takes the same path.
     */
    if (dict_open(dict, dict_len, &probe) != 0) {
        char *buf;
        int cap = len * 16 + 64;
        int n;

        buf = (char *)malloc((size_t)cap);
        if (buf == NULL) {
            return -1;
        }
        n = sam_reciter_rules(text, buf, cap);
        if (n < 0) {
            free(buf);
            return -1;   /* Python returns False */
        }
        if (sb_put(sb, buf, n) != 0) {
            free(buf);
            return -1;
        }
        free(buf);
        return 0;
    }

    while (i < len) {
        int start = i;
        int is_word = is_word_char(text[i]);

        while (i < len && is_word_char(text[i]) == is_word) {
            i++;
        }

        if (is_word) {
            char stack[128];
            char *upper;
            int tlen = i - start, k;
            const char *pron;
            int pron_len = 0;

            upper = (tlen < (int)sizeof(stack))
                    ? stack : (char *)malloc((size_t)tlen + 1);
            if (upper == NULL) {
                return -1;
            }
            for (k = 0; k < tlen; k++) {
                char c = text[start + k];
                upper[k] = (c >= 'a' && c <= 'z') ? (char)(c - 'a' + 'A') : c;
            }
            upper[tlen] = '\0';

            pron = sam_dict_lookup(dict, dict_len, upper, &pron_len);
            if (upper != stack) {
                free(upper);
            }

            if (pron != NULL && pron_len > 0) {
                /*
                 * Python appends the CONVERTED string and guards it with
                 * `if phonemes:`, so a pronunciation that converts to
                 * nothing falls through to the rules rather than
                 * contributing an empty part. Converting into a scratch
                 * buffer first is what keeps that test on the same value.
                 */
                strbuf_t conv;
                int ok;

                sb_init(&conv);
                ok = arpabet_to_sam_buf(pron, pron_len, &conv) == 0;
                if (ok && conv.len > 0) {
                    if (!first && sb_putc(sb, ' ') != 0) {
                        sb_free(&conv);
                        return -1;
                    }
                    first = 0;
                    if (sb_put(sb, sb_str(&conv), conv.len) != 0) {
                        sb_free(&conv);
                        return -1;
                    }
                    sb_free(&conv);
                    continue;
                }
                sb_free(&conv);
                if (!ok) {
                    return -1;
                }
            }
        }

        if (append_rule_result(sb, &first, text + start, i - start) != 0) {
            return -1;
        }
    }
    return 0;
}

int sam_text_to_phonemes(const char *text, const void *dict, int dict_len,
                         char *out, int out_capacity)
{
    strbuf_t sb;
    int rc;

    sb_init(&sb);
    if (text_to_phonemes_buf(text, dict, dict_len, &sb) != 0) {
        sb_free(&sb);
        return -1;
    }
    rc = emit(&sb, out, out_capacity);
    sb_free(&sb);
    return rc;
}

/* --------------------------------------------------------------------- */
/* Public pipeline                                                       */
/* --------------------------------------------------------------------- */

int sam_text_abi_version(void)
{
    return SAM_TEXT_ABI_VERSION;
}

int sam_parse(const char *phonemes, sam_phoneme_t *out, int out_capacity)
{
    sam_plist_t pl;
    int i, count;

    if (phonemes == NULL) {
        return SAM_E_BADARG;
    }
    if (sam_parse_phonemes(phonemes, &pl) != 0) {
        return SAM_E_BADARG;
    }
    count = pl.count;

    if (out == NULL) {
        sam_plist_free(&pl);
        return count;
    }
    if (out_capacity < count) {
        sam_plist_free(&pl);
        return SAM_E_SHORTBUF;
    }
    for (i = 0; i < count; i++) {
        /* The same narrowing the verified ctypes path does; see
         * native/tools/verify_parser.py. */
        out[i].phoneme = (unsigned char)pl.phoneme[i];
        out[i].length = (unsigned char)pl.length[i];
        out[i].stress = (unsigned char)pl.stress[i];
    }
    sam_plist_free(&pl);
    return count;
}

/* Shared tail of both speak entry points: parse, then render. */
static int speak_parsed(const char *phoneme_string, const sam_voice_t *voice,
                        unsigned char *out, int out_capacity)
{
    sam_plist_t pl;
    sam_phoneme_t *triples;
    int i, rc;

    if (sam_parse_phonemes(phoneme_string, &pl) != 0) {
        return SAM_E_BADARG;
    }
    if (pl.count == 0) {
        /* Python: `if phoneme_list is False or not phoneme_list`. */
        sam_plist_free(&pl);
        return SAM_E_BADARG;
    }

    triples = (sam_phoneme_t *)malloc((size_t)pl.count * sizeof(*triples));
    if (triples == NULL) {
        sam_plist_free(&pl);
        return SAM_E_NOMEM;
    }
    for (i = 0; i < pl.count; i++) {
        triples[i].phoneme = (unsigned char)pl.phoneme[i];
        triples[i].length = (unsigned char)pl.length[i];
        triples[i].stress = (unsigned char)pl.stress[i];
    }

    rc = sam_render(triples, pl.count, voice, out, out_capacity);

    free(triples);
    sam_plist_free(&pl);
    return rc;
}

int sam_speak_text(const char *text, const void *dict, int dict_len,
                   const sam_voice_t *voice,
                   unsigned char *out, int out_capacity)
{
    strbuf_t sb;
    int rc;

    if (text == NULL || voice == NULL) {
        return SAM_E_BADARG;
    }

    sb_init(&sb);
    if (text_to_phonemes_buf(text, dict, dict_len, &sb) != 0) {
        sb_free(&sb);
        return SAM_E_BADARG;
    }
    rc = speak_parsed(sb_str(&sb), voice, out, out_capacity);
    sb_free(&sb);
    return rc;
}

int sam_speak_phonemes(const char *phonemes, const sam_voice_t *voice,
                       unsigned char *out, int out_capacity)
{
    strbuf_t sb;
    int len, i, rc;

    if (phonemes == NULL || voice == NULL) {
        return SAM_E_BADARG;
    }

    /* text_to_audio(phonetic=True) uppercases the string first. */
    len = (int)strlen(phonemes);
    sb_init(&sb);
    if (sb_reserve(&sb, len + 1) != 0) {
        sb_free(&sb);
        return SAM_E_NOMEM;
    }
    for (i = 0; i < len; i++) {
        char c = phonemes[i];
        sb.p[i] = (c >= 'a' && c <= 'z') ? (char)(c - 'a' + 'A') : c;
    }
    sb.p[len] = '\0';
    sb.len = len;

    rc = speak_parsed(sb_str(&sb), voice, out, out_capacity);
    sb_free(&sb);
    return rc;
}
