/*
 * dump_parse.c - run sam_parse_phonemes() over phoneme strings read from
 * stdin, one per line, and print the resulting triples so
 * verify_parser.py can diff them against Python's parse().
 *
 * Output is one line per input line: either "FAIL" or the triples as
 * "phoneme,length,stress" separated by spaces. An empty result line is a
 * successful parse that produced nothing.
 *
 * Host tool, not shipped in the DLL.
 */
#include <stdio.h>
#include <string.h>

#include "sam_frontend.h"

/* Phoneme strings are short; the corpus is generated, not user input. */
#define MAX_LINE 8192

int main(void)
{
    static char line[MAX_LINE];

    while (fgets(line, sizeof(line), stdin) != NULL) {
        sam_plist_t pl;
        size_t n = strlen(line);
        int i;

        while (n > 0 && (line[n - 1] == '\n' || line[n - 1] == '\r')) {
            line[--n] = '\0';
        }

        if (sam_parse_phonemes(line, &pl) != 0) {
            printf("FAIL\n");
            continue;
        }
        for (i = 0; i < pl.count; i++) {
            printf("%s%d,%d,%d", i ? " " : "",
                   pl.phoneme[i], pl.length[i], pl.stress[i]);
        }
        printf("\n");
        sam_plist_free(&pl);
    }
    return 0;
}
