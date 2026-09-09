/*
 * dump_reciter.c - run sam_reciter_rules() over text read from stdin,
 * one case per line, so verify_reciter.py can diff the output against
 * Python's _rule_based_phonemes().
 *
 * One output line per input line: the phoneme string, or "\x01FAIL" for
 * the cases where Python returns False. The sentinel is a control
 * character because an empty phoneme string is a legitimate result and
 * has to stay distinguishable from a failure.
 *
 * Host tool, not shipped in the DLL.
 */
#include <stdio.h>
#include <string.h>

#include "sam_frontend.h"

#define MAX_LINE 8192
#define MAX_OUT  (MAX_LINE * 16 + 1024)   /* a rule can expand 1 char to 15 */

int main(void)
{
    static char line[MAX_LINE];
    static char out[MAX_OUT];

    while (fgets(line, sizeof(line), stdin) != NULL) {
        size_t n = strlen(line);

        while (n > 0 && (line[n - 1] == '\n' || line[n - 1] == '\r')) {
            line[--n] = '\0';
        }

        if (sam_reciter_rules(line, out, (int)sizeof(out)) < 0) {
            printf("\x01" "FAIL\n");
        } else {
            printf("%s\n", out);
        }
    }
    return 0;
}
