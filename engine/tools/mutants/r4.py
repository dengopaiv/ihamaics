"""Stage R.4 mutants: the renderer (docs/c17/04-r4-renderer.md).

Run with: python engine/tools/mutate.py r4

Two checks:

  verify_render  sam_render over the 16 golden cases and 485 random
                 ones, through ctypes, against render() in renderer.py
                 (forced onto its Python path).
  diff_render    sam_render against native/'s DLL on 3,000 cases from
                 a wider generator, with the output buffer prefilled
                 with 0xA5. The mutation copy has no DLLs, so the real
                 tree's native/build/sam_render-x64.dll is passed in.

Each mutant is one edit, and killed_by names exactly what must fail.
The groups below follow the chapter's section 4.7:

  - SAM's own arithmetic, edited: every one must die, by both checks.
  - Q3 in quirks.h, "fixed" in the rewrite or in the oracle.
  - The idioms the rewrite dropped, removed from the oracle instead:
    each must live, which is "no input reaches it", run.
  - What only diff_render can see: bytes nobody wrote.
  - Equivalent edits, kept so the claim is rechecked every run.
"""
import os

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))

CHECKS = {
    'verify_render': ['native/tools/verify_render.py', '--impl', 'engine', '485'],
    'diff_render': ['engine/tools/diff_render.py', '3000', '--native',
                    os.path.join(_ROOT, 'native', 'build', 'sam_render-x64.dll')],
}

R = 'engine/src/render.c'
Q = 'engine/src/quirks.h'
PY = 'nvda-addon/synthDrivers/sam/renderer.py'

BOTH = ('verify_render', 'diff_render')
ORACLE = ('verify_render',)
DIFF = ('diff_render',)
LIVES = ()

MUTANTS = [
    # The output: time table and write position.
    dict(name='time table row never moves on (always formants)',
         edits=[(R, '    o->last_write = kind;\n', '')],
         killed_by=BOTH),
    dict(name='50 time units per sample -> 49',
         edits=[(R, '#define TIME_UNITS_PER_SAMPLE  50', '#define TIME_UNITS_PER_SAMPLE  49')],
         killed_by=BOTH),
    dict(name='voiced rows 3 and 4 swapped (as the table comments say)',
         edits=[(R, 'WRITE_VOICED_1    = 3,', 'WRITE_VOICED_1    = 4,'),
                (R, 'WRITE_VOICED_0    = 4 ', 'WRITE_VOICED_0    = 3 ')],
         killed_by=BOTH),

    # Sampled consonants.
    dict(name='voiced 1-bit level 26 -> 27',
         edits=[(R, '#define VOICED_VALUE_1     26', '#define VOICED_VALUE_1     27')],
         killed_by=BOTH),
    dict(name='unvoiced 1-bit level 5 -> 4',
         edits=[(R, '#define UNVOICED_VALUE_1    5', '#define UNVOICED_VALUE_1    4')],
         killed_by=BOTH),
    dict(name='noise read from bit 6, not bit 7',
         edits=[(R, '        if (noise & 0x80u) {', '        if (noise & 0x40u) {')],
         killed_by=BOTH),
    dict(name='voiced length not complemented',
         edits=[(R, 'uint8_t left = (uint8_t)~(uint8_t)((uint32_t)pitch >> 4);',
                 'uint8_t left = (uint8_t)((uint32_t)pitch >> 4);')],
         killed_by=BOTH),
    # Only the Python's corpus puts a pitch outside a byte into a voiced
    # sample (3 of its 485 cases); diff_render's 3,000 happen not to.
    dict(name='Q1: voiced length from a byte pitch',
         edits=[(R, 'uint8_t left = (uint8_t)~(uint8_t)((uint32_t)pitch >> 4);',
                 'uint8_t left = (uint8_t)~(uint8_t)((uint8_t)pitch >> 4);')],
         killed_by=ORACLE),
    dict(name='voiced sample does not carry its offset on',
         edits=[(R, '        return off;\n', '        return last_offset;\n')],
         killed_by=BOTH),
    dict(name='unvoiced 0-bit level from kind 0 always',
         edits=[(R, 'sam_sampled_consonant_values0[kind];', 'sam_sampled_consonant_values0[0];')],
         killed_by=BOTH),

    # Formants.
    dict(name='phase step freq * 63, not * 64',
         edits=[(R, '(uint32_t)fr->freq[f][pos] * 64u;', '(uint32_t)fr->freq[f][pos] * 63u;')],
         killed_by=BOTH),
    dict(name='square wave flips at 128, not 129',
         edits=[(R, '& 0xFFu) < 129u)', '& 0xFFu) < 128u)')],
         killed_by=BOTH),
    dict(name='square wave height 0x70 -> 0x6F',
         edits=[(R, '#define SQUARE_HEIGHT    0x70', '#define SQUARE_HEIGHT    0x6F')],
         killed_by=BOTH),
    dict(name='mux sum floored (>> 5), not truncated (/ 32)',
         edits=[(R, ' / 32 + 128;', ' >> 5) + 128;'),
                (R, 'const int mux = (s1 * amp[0]', 'const int mux = ((s1 * amp[0]')],
         killed_by=BOTH),
    dict(name='amplitude not masked to 4 bits',
         edits=[(R, '        amp[f] = fr->ampl[f][pos] & 0x0F;', '        amp[f] = fr->ampl[f][pos];')],
         killed_by=BOTH),
    dict(name='phases not reset at the glottal pulse',
         edits=[(R, '        phase[0] = phase[1] = phase[2] = 0;\n', '')],
         killed_by=BOTH),

    # The frame loop.
    dict(name='pitch read at pos, not pos & 0xFF (both reads)',
         edits=[(R, 'fr->pitch[pos & 0xFF]);\n            pos += 2;', 'fr->pitch[pos]);\n            pos += 2;'),
                (R, 'fr->pitch[pos & 0xFF]);\n        }', 'fr->pitch[pos]);\n        }')],
         killed_by=BOTH),
    dict(name='unvoiced sample takes one frame, not two',
         edits=[(R, '            pos += 2;\n', '            pos += 1;\n')],
         killed_by=BOTH),
    dict(name='mem38 = g - g / 4 (rounds up), not int(g * 0.75)',
         edits=[(R, '    return g * 3 / 4;', '    return g - g / 4;')],
         killed_by=BOTH),

    # Q3: the pulse counters do not wrap.
    dict(name='Q3: pulse counters a byte',
         edits=[(Q, 'typedef int64_t sam_pulse_t;', 'typedef uint8_t sam_pulse_t;')],
         killed_by=BOTH),
    dict(name='Q3: oracle pulse wraps at a byte',
         edits=[(PY, '            glottal_pulse -= 1\n', '            glottal_pulse = (glottal_pulse - 1) & 0xFF\n')],
         killed_by=ORACLE),

    # The dropped idioms, removed from the oracle: no input reaches them.
    dict(name='oracle: no sample table guard (unreached)',
         edits=[(PY, '        if sample_idx >= len(SAMPLE_TABLE):\n            return\n', '')],
         killed_by=LIVES),
    dict(name='oracle: no values0 guard (unreached)',
         edits=[(PY, 'SAMPLED_CONSONANT_VALUES0[kind] & 0xFF if kind < len(SAMPLED_CONSONANT_VALUES0) else 0',
                 'SAMPLED_CONSONANT_VALUES0[kind] & 0xFF')],
         killed_by=LIVES),
    dict(name='oracle: phases kept modulo 256 (equivalent)',
         edits=[(PY, 'phase1 = phase1 + freq0', 'phase1 = (phase1 + freq0) & 0xFF'),
                (PY, 'phase2 = phase2 + freq1', 'phase2 = (phase2 + freq1) & 0xFF'),
                (PY, 'phase3 = phase3 + freq2', 'phase3 = (phase3 + freq2) & 0xFF')],
         killed_by=LIVES),
    dict(name='oracle: no pos < n guards in the loop (unreached)',
         edits=[(PY, '        if pos >= n_flags:\n            break\n', ''),
                (PY, '                    freq0 = frq0_arr[pos] if pos < n_frq0 else 0\n'
                     '                    freq1 = frq1_arr[pos] if pos < n_frq1 else 0\n'
                     '                    freq2 = frq2_arr[pos] if pos < n_frq2 else 0\n',
                 '                    freq0 = frq0_arr[pos]\n'
                 '                    freq1 = frq1_arr[pos]\n'
                 '                    freq2 = frq2_arr[pos]\n'),
                (PY, '            if pos < n_pitches:\n                glottal_pulse = pitches[pos]\n'
                     '            else:\n                glottal_pulse = 0\n',
                 '            glottal_pulse = pitches[pos]\n')],
         killed_by=LIVES),

    # Bytes nobody wrote: ctypes zeroes verify_render's buffer, so only
    # diff_render's 0xA5 fill shows them.
    dict(name='no zeroing ahead of a write (the first 3 samples)',
         edits=[(R, '    zero_to(o, pos);\n', '')],
         killed_by=DIFF),

    # Equivalent edits.
    dict(name='mux not clamped (unreached: 3..252 measured)',
         edits=[(R, 'out[k] = (uint8_t)(mux < 0 ? 0 : (mux > UINT8_MAX ? UINT8_MAX : mux));',
                 'out[k] = (uint8_t)mux;')],
         killed_by=LIVES),
    dict(name='level not masked to 4 bits ((x * 16) mod 256 is the same)',
         edits=[(R, '(uint8_t)((level & 0x0Fu) * 16u);', '(uint8_t)(level * 16u);')],
         killed_by=LIVES),
    # Once a write lands at pos >= size nothing is written again (the
    # time only grows), and the result is cut at size either way.
    dict(name='overflow test pos >= size (equivalent)',
         edits=[(R, '    if (pos > o->size) {', '    if (pos >= o->size) {')],
         killed_by=LIVES),
    # The counter is already `speed` whenever pos is new, and pos is
    # constant within a frame, so an unvoiced sample always comes at the
    # first step of its frame: SAM's reset is a no-op.
    dict(name='speed counter not restarted after unvoiced (equivalent)',
         edits=[(R, '            pos += 2;\n            speedcounter = speed;\n', '            pos += 2;\n')],
         killed_by=LIVES),
]
