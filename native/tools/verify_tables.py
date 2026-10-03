#!/usr/bin/env python3
"""Prove the generated C tables equal the Python ones.

Compiles native/tools/dump_tables.c against the generated tables, runs it,
and compares every value with renderer_tables.py. A generator is only
trustworthy if something checks its output.

    python native/tools/verify_tables.py

Exit status is 0 when every table matches, 1 otherwise.
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _build import ROOT, build_and_run, take_impl  # noqa: E402
take_impl()
sys.path.insert(0, os.path.join(ROOT, 'nvda-addon', 'synthDrivers', 'sam'))

import renderer_tables as rt  # noqa: E402



def unpack(packed, shift):
    return [(v >> shift) & 0xFF for v in packed]


def expected():
    return {
        'sam_freq1': unpack(rt.FREQUENCY_DATA, 0),
        'sam_freq2': unpack(rt.FREQUENCY_DATA, 8),
        'sam_freq3': unpack(rt.FREQUENCY_DATA, 16),
        'sam_ampl1': unpack(rt.AMPLITUDE_DATA, 0),
        'sam_ampl2': unpack(rt.AMPLITUDE_DATA, 8),
        'sam_ampl3': unpack(rt.AMPLITUDE_DATA, 16),
        'sam_sampled_consonant_flags': list(rt.SAMPLED_CONSONANT_FLAGS),
        'sam_blend_rank': list(rt.BLEND_RANK),
        'sam_in_blend_length': list(rt.IN_BLEND_LENGTH),
        'sam_out_blend_length': list(rt.OUT_BLEND_LENGTH),
        'sam_sample_table': list(rt.SAMPLE_TABLE),
        'sam_sinus': list(rt.SINUS_TABLE),
        'sam_stress_pitch': list(rt.STRESS_PITCH_TABLE),
        'sam_amplitude_rescale': list(rt.AMPLITUDE_RESCALE),
        'sam_sampled_consonant_values0': list(rt.SAMPLED_CONSONANT_VALUES0),
        'sam_time_table': [v for row in rt.TIME_TABLE for v in row],
    }


def run_dumper():
    """Compile and run dump_tables.c, returning its stdout."""
    return build_and_run('dump_tables.c', ['sam_tables.c'], text=True)


def main():
    out = run_dumper()
    if out is None:
        return 1

    actual = {}
    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = re.split(r'\s+', line)
        actual[parts[0]] = [int(x) for x in parts[1:]]

    want = expected()
    failures = 0
    for name, values in want.items():
        got = actual.get(name)
        if got is None:
            print(f'  MISSING {name}')
            failures += 1
        elif got != values:
            bad = [i for i, (a, b) in enumerate(zip(got, values)) if a != b]
            if len(got) != len(values):
                print(f'  FAIL    {name}: length {len(got)} != {len(values)}')
            else:
                print(f'  FAIL    {name}: {len(bad)} values differ, '
                      f'first at index {bad[0]} ({got[bad[0]]} != {values[bad[0]]})')
            failures += 1
        else:
            print(f'  ok      {name:32} {len(values):5} values')

    extra = set(actual) - set(want)
    for name in sorted(extra):
        print(f'  EXTRA   {name} present in C but not checked')

    print()
    if failures:
        print(f'{failures} table(s) MISMATCHED')
        return 1
    total = sum(len(v) for v in want.values())
    print(f'all {len(want)} tables match, {total} values verified')
    return 0


if __name__ == '__main__':
    sys.exit(main())
