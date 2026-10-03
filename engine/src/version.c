/*
 * version.c - the ABI version entry points, and the layout promises the
 * two public headers make.
 *
 * Stage R.0 of the C17 rewrite (docs/c17-rewrite-plan.md): the library
 * exists, builds on every leg and answers a version query. Nothing else
 * is implemented yet, so nothing else is exported.
 *
 * The public headers in include/ are copies of native/include, byte for
 * byte; they are the API both engines share. Derived, as everything in
 * this engine is, from SAM (1982, Don't Ask Software, Mark Barton) by way
 * of Stefan Macke's C and Christian Schiffler's JavaScript. See NOTICE.md.
 */

#include "sam_text.h"

/*
 * The NVDA addon passes these structs through ctypes with its own field
 * list. A layout change here would be read silently wrong on the other
 * side, so it is a compile error instead. docs/c-engine-port.md measured
 * both sizes from Python when the ABI was first defined.
 */
_Static_assert(sizeof(sam_phoneme_t) == 3, "sam_phoneme_t is three bytes, no padding");
_Static_assert(sizeof(sam_voice_t) == 12, "sam_voice_t is four bytes and two ints");

SAM_API int sam_abi_version(void)
{
    return SAM_ABI_VERSION;
}

SAM_API int sam_text_abi_version(void)
{
    return SAM_TEXT_ABI_VERSION;
}
