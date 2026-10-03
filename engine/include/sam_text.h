/*
 * sam_text.h - native SAM front end: text to phonemes, and the whole
 * pipeline from text to audio.
 *
 * sam_render.h covers the renderer, which is 99.7% of synthesis cost and
 * the only part the NVDA addon needs in C. This header covers the rest -
 * the reciter, the CMU dictionary, the number expander and the parser -
 * which cost almost nothing but drag a 3.6 MB dictionary and 2,300 lines
 * of Python behind them. Porting them is what makes an application with
 * no interpreter possible; see docs/native-gui.md.
 *
 * Versioned separately from sam_render.h on purpose. The renderer ABI is
 * unchanged and stays at SAM_ABI_VERSION 1, so an addon built against it
 * keeps working with a DLL that also exports these; a consumer of the
 * front end checks sam_text_abi_version() instead.
 *
 * Same conventions as sam_render.h throughout: C linkage, plain data,
 * caller-allocated buffers, out == NULL to query the size needed, and
 * negative returns for errors.
 */

#ifndef SAM_TEXT_H
#define SAM_TEXT_H

#include "sam_render.h"

#ifdef __cplusplus
extern "C" {
#endif

#define SAM_TEXT_ABI_VERSION 1

/* SAM_TEXT_ABI_VERSION of the built library, for a load-time check. */
SAM_API int sam_text_abi_version(void);

/*
 * The dictionary blob produced by native/tools/gen_dict.py.
 *
 * Every function taking (dict, dict_len) accepts dict == NULL, which
 * selects the rules-only path - the same thing Python does when cmudict
 * cannot be imported. The buffer is borrowed for the duration of the
 * call and never copied or freed, so a resource pointer is fine.
 */

/*
 * Text to a SAM phoneme string: dictionary first, rule engine for
 * anything the dictionary does not have. Port of text_to_phonemes().
 *
 * Writes a NUL-terminated string and returns its length, not counting
 * the NUL. With out == NULL, returns an upper bound on the length a real
 * call would need, so the caller can size a buffer.
 */
SAM_API int sam_text_to_phonemes(const char *text,
                                 const void *dict, int dict_len,
                                 char *out, int out_capacity);

/*
 * Numbers to words: "60" to "sixty", "3.14" to "three point one four".
 * Port of expand_numbers().
 *
 * The NVDA driver applies this before speaking; the GUI does not,
 * because sam_gui.py does not. It is exported so both can choose.
 */
SAM_API int sam_expand_numbers(const char *text, char *out, int out_capacity);

/*
 * Phoneme string to the renderer's triples. Port of parse().
 *
 * Returns the number of triples written, or the number a real call would
 * write when out == NULL. SAM_E_BADARG when the string contains a
 * character that is neither a phoneme nor a stress digit, which is where
 * Python's parse() returns False.
 */
SAM_API int sam_parse(const char *phonemes,
                      sam_phoneme_t *out, int out_capacity);

/*
 * Text straight to 8-bit unsigned PCM at SAM_SAMPLE_RATE: reciter,
 * parser and renderer in one call. Port of text_to_audio().
 *
 * Returns the sample count, or an upper bound when out == NULL. The
 * bound comes from sam_render() and is generous; a real call returns the
 * exact length.
 */
SAM_API int sam_speak_text(const char *text,
                           const void *dict, int dict_len,
                           const sam_voice_t *voice,
                           unsigned char *out, int out_capacity);

/*
 * As sam_speak_text, but the input is already a phoneme string. The
 * string is uppercased first, as text_to_audio(phonetic=True) does.
 */
SAM_API int sam_speak_phonemes(const char *phonemes,
                               const sam_voice_t *voice,
                               unsigned char *out, int out_capacity);

#ifdef __cplusplus
}
#endif

#endif /* SAM_TEXT_H */
