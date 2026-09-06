/*
 * dump_tables.c - print every generated table so verify_tables.py can
 * diff it against the Python source of truth. Build host tool, not
 * shipped in the DLL.
 */
#include <stdio.h>
#include "sam_tables.h"

static void dump_u8(const char *name, const uint8_t *v, int n)
{
    int i;
    printf("%s", name);
    for (i = 0; i < n; i++) printf(" %d", (int)v[i]);
    printf("\n");
}

static void dump_i8(const char *name, const int8_t *v, int n)
{
    int i;
    printf("%s", name);
    for (i = 0; i < n; i++) printf(" %d", (int)v[i]);
    printf("\n");
}

int main(void)
{
    int r, c;
    dump_u8("sam_freq1", sam_freq1, 80);
    dump_u8("sam_freq2", sam_freq2, 80);
    dump_u8("sam_freq3", sam_freq3, 80);
    dump_u8("sam_ampl1", sam_ampl1, 80);
    dump_u8("sam_ampl2", sam_ampl2, 80);
    dump_u8("sam_ampl3", sam_ampl3, 80);
    dump_u8("sam_sampled_consonant_flags", sam_sampled_consonant_flags, 80);
    dump_u8("sam_blend_rank", sam_blend_rank, 80);
    dump_u8("sam_in_blend_length", sam_in_blend_length, 80);
    dump_u8("sam_out_blend_length", sam_out_blend_length, 80);
    dump_u8("sam_sample_table", sam_sample_table, 1280);
    dump_i8("sam_sinus", sam_sinus, 256);
    dump_u8("sam_stress_pitch", sam_stress_pitch, 10);
    dump_u8("sam_amplitude_rescale", sam_amplitude_rescale, 16);
    dump_u8("sam_sampled_consonant_values0", sam_sampled_consonant_values0, 5);

    printf("sam_time_table");
    for (r = 0; r < 5; r++)
        for (c = 0; c < 5; c++) printf(" %d", (int)sam_time_table[r][c]);
    printf("\n");
    return 0;
}
