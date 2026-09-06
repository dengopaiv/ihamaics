/*
 * sam_render.c - native SAM renderer.
 *
 * SCAFFOLD: sam_abi_version() is real; sam_render() is not implemented
 * yet and returns SAM_E_BADARG so the Python fallback stays in charge.
 * See docs/c-engine-port.md for the porting order.
 */

#include "sam_render.h"

SAM_API int sam_abi_version(void)
{
    return SAM_ABI_VERSION;
}

SAM_API int sam_render(const sam_phoneme_t *phonemes,
                       int                  count,
                       const sam_voice_t   *voice,
                       unsigned char       *out,
                       int                  out_capacity)
{
    (void)out;
    (void)out_capacity;

    if (phonemes == NULL || count <= 0 || voice == NULL) {
        return SAM_E_BADARG;
    }
    if (voice->speed == 0) {
        return SAM_E_BADSPEED;
    }

    /* TODO: port prepare_frames/create_frames/create_transitions/
     * process_frames from nvda-addon/synthDrivers/sam/renderer.py. */
    return SAM_E_BADARG;
}
