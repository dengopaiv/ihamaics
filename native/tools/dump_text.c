/*
 * dump_text.c - run the native front end over cases read from stdin so
 * verify_text.py can diff it against the Python one.
 *
 *   dump_text phonemes <sam.dict>   sam_text_to_phonemes, with dictionary
 *   dump_text rules                 sam_text_to_phonemes, dictionary absent
 *   dump_text numbers               sam_expand_numbers
 *
 * One output line per input line, "\x01FAIL" where Python returns False.
 * The sentinel is a control character because an empty result is a
 * legitimate answer and must stay distinct from a failure.
 *
 * Host tool, not shipped in the DLL.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "sam_text.h"

#define MAX_LINE 8192
#define MAX_OUT  (MAX_LINE * 24 + 4096)

static void *read_file(const char *path, int *out_len)
{
    FILE *f = fopen(path, "rb");
    long n;
    void *buf;

    if (f == NULL) {
        return NULL;
    }
    if (fseek(f, 0, SEEK_END) != 0) {
        fclose(f);
        return NULL;
    }
    n = ftell(f);
    if (n <= 0 || fseek(f, 0, SEEK_SET) != 0) {
        fclose(f);
        return NULL;
    }
    buf = malloc((size_t)n);
    if (buf == NULL) {
        fclose(f);
        return NULL;
    }
    if (fread(buf, 1, (size_t)n, f) != (size_t)n) {
        free(buf);
        fclose(f);
        return NULL;
    }
    fclose(f);
    *out_len = (int)n;
    return buf;
}

int main(int argc, char **argv)
{
    static char line[MAX_LINE];
    static char out[MAX_OUT];
    void *dict = NULL;
    int dict_len = 0;
    int numbers = 0;

    if (argc < 2) {
        fprintf(stderr, "usage: dump_text phonemes <dict> | rules | numbers\n");
        return 2;
    }
    if (strcmp(argv[1], "numbers") == 0) {
        numbers = 1;
    } else if (strcmp(argv[1], "phonemes") == 0) {
        if (argc < 3) {
            fprintf(stderr, "phonemes mode needs a dictionary path\n");
            return 2;
        }
        dict = read_file(argv[2], &dict_len);
        if (dict == NULL) {
            fprintf(stderr, "could not read %s\n", argv[2]);
            return 2;
        }
    } else if (strcmp(argv[1], "rules") != 0) {
        fprintf(stderr, "unknown mode %s\n", argv[1]);
        return 2;
    }

    while (fgets(line, sizeof(line), stdin) != NULL) {
        size_t n = strlen(line);
        int rc;

        while (n > 0 && (line[n - 1] == '\n' || line[n - 1] == '\r')) {
            line[--n] = '\0';
        }

        if (numbers) {
            rc = sam_expand_numbers(line, out, (int)sizeof(out));
        } else {
            rc = sam_text_to_phonemes(line, dict, dict_len, out,
                                      (int)sizeof(out));
        }

        if (rc < 0) {
            printf("\x01" "FAIL\n");
        } else {
            printf("%s\n", out);
        }
    }

    free(dict);
    return 0;
}
