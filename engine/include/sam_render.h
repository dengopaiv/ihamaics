/*
 * sam_render.h - native SAM renderer ABI
 *
 * Replaces process_frames() and its callers in
 * nvda-addon/synthDrivers/sam/renderer.py, which measured at 99.7% of
 * total synthesis cost. The reciter and parser stay in Python; only the
 * per-sample DSP loop crosses into C. See docs/c-engine-port.md.
 *
 * Loaded from Python with ctypes, so everything here is C linkage, plain
 * data, and caller-allocated buffers. No callbacks, no ownership handoff.
 */

#ifndef SAM_RENDER_H
#define SAM_RENDER_H

#include <stddef.h>   /* NULL */

/*
 * Symbol visibility. MSVC exports nothing by default, so the build must
 * define SAM_BUILD_DLL; consumers using ctypes need no import decoration.
 */
#if defined(_WIN32)
#  if defined(SAM_BUILD_DLL)
#    define SAM_API __declspec(dllexport)
#  else
#    define SAM_API
#  endif
#else
#  define SAM_API __attribute__((visibility("default")))
#endif

#ifdef __cplusplus
extern "C" {
#endif

#define SAM_SAMPLE_RATE   22050   /* mono, 8-bit unsigned PCM */
#define SAM_ABI_VERSION   1

/* One entry of the parser's output list: [phoneme, length, stress]. */
typedef struct {
    unsigned char phoneme;
    unsigned char length;
    unsigned char stress;
} sam_phoneme_t;

typedef struct {
    unsigned char pitch;       /* 0-255,  default 64                     */
    unsigned char mouth;       /* 0-255,  default 128                    */
    unsigned char throat;      /* 0-255,  default 128                    */
    unsigned char speed;       /* 1-255,  default 72; 0 is invalid       */
    int           singmode;    /* 0 or 1                                 */
    int           inflection;  /* 0-100,  default 50 (0=flat, 100=wild)  */
} sam_voice_t;

/* Error codes. All negative; a non-negative return is a sample count. */
#define SAM_E_BADARG      (-1)   /* NULL phonemes, count <= 0, NULL voice */
#define SAM_E_BADSPEED    (-2)   /* voice->speed == 0 (would divide by zero) */
#define SAM_E_SHORTBUF    (-3)   /* out_capacity smaller than needed */
#define SAM_E_NOMEM       (-4)   /* internal working set could not be allocated */

/*
 * Render phonemes to 8-bit unsigned PCM.
 *
 * Pass out == NULL to query a capacity to allocate. That value is an
 * upper bound (176.4 * total_length * speed), not the exact length: how
 * many samples the timetable actually advances is only known once the
 * frames have been rendered. A real call returns the exact count.
 *
 * Otherwise writes the rendered samples and returns how many it wrote,
 * or a negative SAM_E_* code. SAM_E_SHORTBUF means out_capacity was
 * smaller than the rendered length and nothing was written.
 *
 * Deterministic in its inputs and free of globals and I/O, so it is safe
 * to call concurrently from several threads. It does allocate internally:
 * the per-frame working set is proportional to the total phoneme length
 * and is freed before returning.
 */
SAM_API int sam_render(const sam_phoneme_t *phonemes,
                       int                  count,
                       const sam_voice_t   *voice,
                       unsigned char       *out,
                       int                  out_capacity);

/* SAM_ABI_VERSION of the built library, for a load-time sanity check. */
SAM_API int sam_abi_version(void);

#ifdef __cplusplus
}
#endif

#endif /* SAM_RENDER_H */
