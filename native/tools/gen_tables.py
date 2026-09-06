#!/usr/bin/env python3
"""Generate the C renderer tables from renderer_tables.py.

Transliterating several thousand numbers by hand is how a voice quietly
changes, so the C tables are generated from the Python ones and never
edited directly. Run from the repository root after any table change:

    python native/tools/gen_tables.py

Writes native/src/sam_tables.h and native/src/sam_tables.c.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'nvda-addon', 'synthDrivers', 'sam'))

import renderer_tables as rt  # noqa: E402

OUT = os.path.join(ROOT, 'native', 'src')

BANNER = """/*
 * %s - GENERATED FILE, DO NOT EDIT.
 *
 * Produced by native/tools/gen_tables.py from
 * nvda-addon/synthDrivers/sam/renderer_tables.py. Edit the Python tables
 * and regenerate; hand-editing these numbers is how the voice changes by
 * accident.
 */
"""


def unpack(packed):
    """Split the packed 24-bit little-endian words into three byte columns."""
    return ([v & 0xFF for v in packed],
            [(v >> 8) & 0xFF for v in packed],
            [(v >> 16) & 0xFF for v in packed])


def check(name, values, ctype):
    lo, hi = (-128, 127) if ctype == 'int8_t' else (0, 255)
    for v in values:
        if not (lo <= v <= hi):
            raise SystemExit(f'{name}: {v} does not fit in {ctype}')
    return values


def emit_1d(name, values, ctype):
    """One flat array, eight values per line."""
    body = []
    for i in range(0, len(values), 8):
        body.append('    ' + ', '.join(f'{v:4}' for v in values[i:i + 8]) + ',')
    return (f'const {ctype} {name}[{len(values)}] = {{\n'
            + '\n'.join(body).rstrip(',') + '\n};\n')


def emit_2d(name, rows, ctype):
    body = ['    { ' + ', '.join(f'{v:4}' for v in row) + ' },' for row in rows]
    return (f'const {ctype} {name}[{len(rows)}][{len(rows[0])}] = {{\n'
            + '\n'.join(body) + '\n};\n')


def main():
    f1, f2, f3 = unpack(rt.FREQUENCY_DATA)
    a1, a2, a3 = unpack(rt.AMPLITUDE_DATA)

    tables_1d = [
        ('sam_freq1', f1, 'uint8_t'),
        ('sam_freq2', f2, 'uint8_t'),
        ('sam_freq3', f3, 'uint8_t'),
        ('sam_ampl1', a1, 'uint8_t'),
        ('sam_ampl2', a2, 'uint8_t'),
        ('sam_ampl3', a3, 'uint8_t'),
        ('sam_sampled_consonant_flags', list(rt.SAMPLED_CONSONANT_FLAGS), 'uint8_t'),
        ('sam_blend_rank', list(rt.BLEND_RANK), 'uint8_t'),
        ('sam_in_blend_length', list(rt.IN_BLEND_LENGTH), 'uint8_t'),
        ('sam_out_blend_length', list(rt.OUT_BLEND_LENGTH), 'uint8_t'),
        ('sam_sample_table', list(rt.SAMPLE_TABLE), 'uint8_t'),
        ('sam_sinus', list(rt.SINUS_TABLE), 'int8_t'),
        ('sam_stress_pitch', list(rt.STRESS_PITCH_TABLE), 'uint8_t'),
        ('sam_amplitude_rescale', list(rt.AMPLITUDE_RESCALE), 'uint8_t'),
        ('sam_sampled_consonant_values0', list(rt.SAMPLED_CONSONANT_VALUES0), 'uint8_t'),
    ]
    for name, values, ctype in tables_1d:
        check(name, values, ctype)

    time_rows = [list(r) for r in rt.TIME_TABLE]
    for row in time_rows:
        check('sam_time_table', row, 'uint8_t')

    # Header
    h = [BANNER % 'sam_tables.h',
         '\n#ifndef SAM_TABLES_H\n#define SAM_TABLES_H\n\n#include <stdint.h>\n',
         f'#define SAM_PHONEME_COUNT {len(rt.FREQUENCY_DATA)}\n',
         f'#define SAM_SAMPLE_TABLE_SIZE {len(rt.SAMPLE_TABLE)}\n']
    for name, values, ctype in tables_1d:
        h.append(f'extern const {ctype} {name}[{len(values)}];\n')
    h.append(f'extern const uint8_t sam_time_table[{len(time_rows)}]'
             f'[{len(time_rows[0])}];\n')
    h.append('\n#endif /* SAM_TABLES_H */\n')

    # Source
    c = [BANNER % 'sam_tables.c', '\n#include "sam_tables.h"\n\n']
    for name, values, ctype in tables_1d:
        c.append(emit_1d(name, values, ctype))
        c.append('\n')
    c.append(emit_2d('sam_time_table', time_rows, 'uint8_t'))

    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, 'sam_tables.h'), 'w', encoding='utf-8', newline='\n') as fh:
        fh.write(''.join(h))
    with open(os.path.join(OUT, 'sam_tables.c'), 'w', encoding='utf-8', newline='\n') as fh:
        fh.write(''.join(c))

    total = sum(len(v) for _, v, _ in tables_1d) + sum(len(r) for r in time_rows)
    for name, values, _ in tables_1d:
        print(f'  {name:32} {len(values):5}')
    print(f'  {"sam_time_table":32} {len(time_rows)}x{len(time_rows[0])}')
    print(f'\n{len(tables_1d) + 1} tables, {total} values -> native/src/sam_tables.[ch]')


if __name__ == '__main__':
    main()
