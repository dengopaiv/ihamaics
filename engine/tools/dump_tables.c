/*
 * dump_tables.c - print every renderer table, one line each, for
 * native/tools/verify_tables.py --impl engine to compare with the Python.
 *
 * The output format is native/tools/dump_tables.c's, line for line, so
 * one verifier checks both engines (docs/c17-rewrite-plan.md section 5).
 * Rewritten from that file for stage R.1. A host tool; not in the library.
 */

#include <stdio.h>

#include "tables.h"

static void dump_u8(const char *name, const uint8_t *v, size_t n)
{
    printf("%s", name);
    for (size_t i = 0; i < n; i++) {
        printf(" %d", (int)v[i]);
    }
    printf("\n");
}

static void dump_i8(const char *name, const int8_t *v, size_t n)
{
    printf("%s", name);
    for (size_t i = 0; i < n; i++) {
        printf(" %d", (int)v[i]);
    }
    printf("\n");
}

/* Every table is a declared array, so its length comes from the type. */
#define DUMP_U8(t) dump_u8(#t, t, sizeof t / sizeof t[0])
#define DUMP_I8(t) dump_i8(#t, t, sizeof t / sizeof t[0])

int main(void)
{
    DUMP_U8(sam_freq1);
    DUMP_U8(sam_freq2);
    DUMP_U8(sam_freq3);
    DUMP_U8(sam_ampl1);
    DUMP_U8(sam_ampl2);
    DUMP_U8(sam_ampl3);
    DUMP_U8(sam_sampled_consonant_flags);
    DUMP_U8(sam_blend_rank);
    DUMP_U8(sam_in_blend_length);
    DUMP_U8(sam_out_blend_length);
    DUMP_U8(sam_sample_table);
    DUMP_I8(sam_sinus);
    DUMP_U8(sam_stress_pitch);
    DUMP_U8(sam_amplitude_rescale);
    DUMP_U8(sam_sampled_consonant_values0);
    /*
     * Row by row, on one line: the verifier flattens the Python's rows.
     * Each row is read as its own array, not all 25 values through a
     * pointer to the first row, which strict C does not allow.
     */
    printf("sam_time_table");
    for (size_t r = 0; r < SAM_TIME_TABLE_ROWS; r++) {
        for (size_t c = 0; c < SAM_TIME_TABLE_COLS; c++) {
            printf(" %d", (int)sam_time_table[r][c]);
        }
    }
    printf("\n");
    return 0;
}
