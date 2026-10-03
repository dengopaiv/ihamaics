#!/usr/bin/env python3
"""Generate engine/src/tables.[ch], the renderer's tables, from the Python.

    python engine/tools/gen_tables.py           write the two files
    python engine/tools/gen_tables.py --check   compare, write nothing

Stage R.1 of the C17 rewrite (docs/c17/01-r1-tables.md). The numbers
are SAM's own: the 6502 original's tables, by way of Stefan Macke's C,
Christian Schiffler's JavaScript (renderer/tables.es6) and our Python
(nvda-addon/synthDrivers/sam/renderer_tables.py), which is the oracle
and the one place a table value is ever edited. Rewritten from
native/tools/gen_tables.py, which produced the same values for native/.

What this generator adds to that one:

  - every table carries a comment saying what it holds and which
    index it takes, so tables.h can be read without the Python open;
  - every size is a named constant, and the two-dimensional tables are
    declared as what they are;
  - --check, which regenerates in memory and fails if either file on
    disk differs. ctest runs it under the label "quick", so a table
    edited by hand, or a Python table changed without regenerating,
    fails the build's own tests instead of changing the voice quietly.

Line endings are not compared: git checks these files out with CRLF on
Windows (core.autocrlf) and LF elsewhere, and both are the same file.
"""
import argparse
import os
import sys

ENGINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.dirname(ENGINE)
sys.path.insert(0, os.path.join(ROOT, 'nvda-addon', 'synthDrivers', 'sam'))

import renderer_tables as rt  # noqa: E402

OUT = os.path.join(ENGINE, 'src')

BANNER = """\
/*
 * %s - GENERATED FILE, DO NOT EDIT.
 *
 * Written by engine/tools/gen_tables.py from
 * nvda-addon/synthDrivers/sam/renderer_tables.py. Change a value there,
 * then regenerate; `gen_tables.py --check` (ctest label "quick") fails
 * while the two disagree.
 *
 * SAM's tables (1982, Don't Ask Software, Mark Barton), as published by
 * Stefan Macke's C and Christian Schiffler's JavaScript. See NOTICE.md.
 */
"""


def columns(packed):
    """The Python packs three bytes per phoneme as b0 | b1 << 8 | b2 << 16."""
    return ([v & 0xFF for v in packed],
            [(v >> 8) & 0xFF for v in packed],
            [(v >> 16) & 0xFF for v in packed])


def tables():
    """(name, ctype, dims, flat values, comment), in the order emitted.

    dims are the C array dimensions; each is a constant name or a number.
    The comment is the Python's own, plus what the index is.
    """
    f1, f2, f3 = columns(rt.FREQUENCY_DATA)
    a1, a2, a3 = columns(rt.AMPLITUDE_DATA)
    ph = ('SAM_PHONEME_COUNT',)
    rows = len(rt.TIME_TABLE)
    cols = len(rt.TIME_TABLE[0])
    return [
        ('sam_freq1', 'uint8_t', ph, f1,
         'Formant 1 frequency of each phoneme, before the voice\'s mouth\n'
         'setting scales it (R.2). Byte 0 of FREQUENCY_DATA.'),
        ('sam_freq2', 'uint8_t', ph, f2,
         'Formant 2 frequency, before the throat setting scales it.\n'
         'Byte 1 of FREQUENCY_DATA.'),
        ('sam_freq3', 'uint8_t', ph, f3,
         'Formant 3 frequency; no voice setting touches it. Byte 2 of\n'
         'FREQUENCY_DATA.'),
        ('sam_ampl1', 'uint8_t', ph, a1,
         'Formant 1 amplitude of each phoneme, as an index into\n'
         'sam_amplitude_rescale. Byte 0 of AMPLITUDE_DATA.'),
        ('sam_ampl2', 'uint8_t', ph, a2,
         'Formant 2 amplitude, the same way. Byte 1 of AMPLITUDE_DATA.'),
        ('sam_ampl3', 'uint8_t', ph, a3,
         'Formant 3 amplitude, the same way. Byte 2 of AMPLITUDE_DATA.'),
        ('sam_sampled_consonant_flags', 'uint8_t', ph,
         list(rt.SAMPLED_CONSONANT_FLAGS),
         'Per phoneme, for a sampled consonant: the low three bits pick\n'
         'the 256-byte section of sam_sample_table (1..5), the high five\n'
         'bits where in it an unvoiced one starts. High bits zero is a\n'
         'voiced one (Z, ZH, V, DH), which continues from where the last\n'
         'sample stopped. 0 for a phoneme with no sample.'),
        ('sam_blend_rank', 'uint8_t', ph, list(rt.BLEND_RANK),
         'Per phoneme: between two phonemes, the one with the lower rank\n'
         'decides the length of the transition.'),
        ('sam_in_blend_length', 'uint8_t', ph, list(rt.IN_BLEND_LENGTH),
         'Per phoneme: frames at its start used to interpolate from the\n'
         'phoneme before.'),
        ('sam_out_blend_length', 'uint8_t', ph, list(rt.OUT_BLEND_LENGTH),
         'Per phoneme: frames at its end used to interpolate to the next.'),
        ('sam_sample_table', 'uint8_t', ('SAM_SAMPLE_TABLE_SIZE',),
         list(rt.SAMPLE_TABLE),
         'The sampled consonants: five 256-byte sections of one-bit\n'
         'noise, eight samples per byte.'),
        ('sam_sinus', 'int8_t', ('SAM_SINUS_SIZE',), list(rt.SINUS_TABLE),
         'One cycle of sine, int(127 * sin(2 pi x / 256)), indexed by the\n'
         'high byte of the phase of formant 1 or 2 (formant 3 is a square\n'
         'wave). Computed by the Python, so the engine needs no libm and\n'
         'no agreement with it about rounding.'),
        ('sam_stress_pitch', 'uint8_t', ('SAM_STRESS_LEVELS',),
         list(rt.STRESS_PITCH_TABLE),
         'Pitch offset for each stress value 0..9. Scaled by inflection / 50,\n'
         'truncated, then added to the pitch modulo 256, so at the default\n'
         'inflection 0xE0 takes 32 off the pitch value.'),
        ('sam_amplitude_rescale', 'uint8_t', ('SAM_AMPLITUDE_LEVELS',),
         list(rt.AMPLITUDE_RESCALE),
         'Indexed by amplitude 0..15 from sam_ampl*: the level the mixer\n'
         'uses. The Python calls it "decibels to linear".'),
        ('sam_sampled_consonant_values0', 'uint8_t',
         ('SAM_SAMPLED_CONSONANT_KINDS',),
         list(rt.SAMPLED_CONSONANT_VALUES0),
         'For each kind of sampled consonant: the value output for a\n'
         'zero bit of its noise.'),
        ('sam_time_table', 'uint8_t',
         ('SAM_TIME_TABLE_ROWS', 'SAM_TIME_TABLE_COLS'),
         [v for row in rt.TIME_TABLE for v in row],
         'The output timetable: how far the write position moves, in\n'
         'fiftieths of a sample, indexed by the kind of the previous write\n'
         'and of this one.'),
    ], {
        'SAM_PHONEME_COUNT': len(rt.FREQUENCY_DATA),
        'SAM_SAMPLE_TABLE_SIZE': len(rt.SAMPLE_TABLE),
        'SAM_SINUS_SIZE': len(rt.SINUS_TABLE),
        'SAM_STRESS_LEVELS': len(rt.STRESS_PITCH_TABLE),
        'SAM_AMPLITUDE_LEVELS': len(rt.AMPLITUDE_RESCALE),
        'SAM_SAMPLED_CONSONANT_KINDS': len(rt.SAMPLED_CONSONANT_VALUES0),
        'SAM_TIME_TABLE_ROWS': rows,
        'SAM_TIME_TABLE_COLS': cols,
    }


def fits(name, ctype, values):
    lo, hi = (-128, 127) if ctype == 'int8_t' else (0, 255)
    bad = [v for v in values if not lo <= v <= hi]
    if bad:
        raise SystemExit(f'{name}: {bad[0]} does not fit in {ctype}')


def comment(text, indent=''):
    lines = text.split('\n')
    return (indent + '/*\n'
            + ''.join(f'{indent} * {ln}\n' for ln in lines)
            + indent + ' */\n')


def body(values, dims, consts):
    """The initialiser: rows of the last dimension, eight values a line."""
    width = consts.get(dims[-1], dims[-1])
    out = []
    if len(dims) == 2:
        for i in range(0, len(values), width):
            out.append('    { ' + ', '.join(f'{v:4}' for v in values[i:i + width])
                       + ' },')
    else:
        for i in range(0, len(values), 8):
            out.append('    ' + ', '.join(f'{v:4}' for v in values[i:i + 8]) + ',')
    out[-1] = out[-1].rstrip(',')
    return '\n'.join(out)


def generate():
    tabs, consts = tables()
    for name, ctype, dims, values, _ in tabs:
        fits(name, ctype, values)
        size = 1
        for d in dims:
            size *= consts[d]
        if size != len(values):
            raise SystemExit(f'{name}: {len(values)} values for {dims}')

    h = [BANNER % 'tables.h', '\n#ifndef SAM_TABLES_H\n#define SAM_TABLES_H\n\n',
         '#include <stdint.h>\n\n']
    for k, v in consts.items():
        h.append(f'#define {k:<28} {v}\n')
    for name, ctype, dims, values, text in tabs:
        decl = ''.join(f'[{d}]' for d in dims)
        h.append('\n' + comment(text) + f'extern const {ctype} {name}{decl};\n')
    h.append('\n#endif /* SAM_TABLES_H */\n')

    c = [BANNER % 'tables.c', '\n#include "tables.h"\n']
    for name, ctype, dims, values, _ in tabs:
        decl = ''.join(f'[{d}]' for d in dims)
        c.append(f'\nconst {ctype} {name}{decl} = {{\n'
                 + body(values, dims, consts) + '\n};\n')

    total = sum(len(t[3]) for t in tabs)
    return {'tables.h': ''.join(h), 'tables.c': ''.join(c)}, len(tabs), total


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--check', action='store_true',
                    help='fail if the files on disk differ; write nothing')
    args = ap.parse_args()

    files, ntab, total = generate()
    if args.check:
        stale = []
        for name, text in files.items():
            path = os.path.join(OUT, name)
            try:
                with open(path, encoding='utf-8', newline='') as fh:
                    disk = fh.read().replace('\r\n', '\n')
            except FileNotFoundError:
                disk = None
            if disk != text:
                stale.append(name)
        if stale:
            print('out of date with renderer_tables.py: '
                  + ', '.join('engine/src/' + s for s in stale))
            print('regenerate with:  python engine/tools/gen_tables.py')
            return 1
        print(f'engine/src/tables.[ch] current: {ntab} tables, {total} values')
        return 0

    for name, text in files.items():
        with open(os.path.join(OUT, name), 'w', encoding='utf-8',
                  newline='\n') as fh:
            fh.write(text)
    print(f'{ntab} tables, {total} values -> engine/src/tables.[ch]')
    return 0


if __name__ == '__main__':
    sys.exit(main())
