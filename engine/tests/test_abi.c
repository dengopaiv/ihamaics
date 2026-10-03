/*
 * test_abi.c - the library links and reports the ABI versions its
 * headers declare.
 */

#include <stdio.h>

#include "sam_text.h"

int main(void)
{
    if (sam_abi_version() != SAM_ABI_VERSION) {
        printf("sam_abi_version() = %d, header says %d\n",
               sam_abi_version(), SAM_ABI_VERSION);
        return 1;
    }
    if (sam_text_abi_version() != SAM_TEXT_ABI_VERSION) {
        printf("sam_text_abi_version() = %d, header says %d\n",
               sam_text_abi_version(), SAM_TEXT_ABI_VERSION);
        return 1;
    }
    printf("abi %d, text abi %d\n", SAM_ABI_VERSION, SAM_TEXT_ABI_VERSION);
    return 0;
}
