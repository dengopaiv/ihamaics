#!/usr/bin/env python3
"""Differential test: C sam_set_mouth_throat vs Python set_mouth_throat.

Compares all 65,536 (mouth, throat) combinations by checksum, so the
whole input space is covered rather than a handful of samples. On a
mismatch it re-runs that one case and prints the first differing value.

    python native/tools/verify_frames.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _build import ROOT, build_and_run, take_impl  # noqa: E402
take_impl()
sys.path.insert(0, os.path.join(ROOT, 'nvda-addon', 'synthDrivers', 'sam'))

from renderer import set_mouth_throat  # noqa: E402



def fnv1a(freqdata):
    """Must match checksum() in dump_frames.c exactly."""
    h = 2166136261
    for row in freqdata:
        for v in row:
            h = ((h ^ (v & 0xFF)) * 16777619) & 0xFFFFFFFF
            h = ((h ^ ((v >> 8) & 0xFF)) * 16777619) & 0xFFFFFFFF
    return h


def run_dumper():
    return build_and_run('dump_frames.c', ['sam_frames.c', 'sam_tables.c'],
                         text=True)


def main():
    out = run_dumper()
    if out is None:
        return 1

    lines = [l for l in out.splitlines() if l.strip()]
    if len(lines) != 65536:
        print(f'expected 65536 cases from C, got {len(lines)}')
        return 1

    mismatches = []
    for line in lines:
        m, t, c_sum = line.split()
        m, t, c_sum = int(m), int(t), int(c_sum)
        if fnv1a(set_mouth_throat(m, t)) != c_sum:
            mismatches.append((m, t))

    if not mismatches:
        print(f'sam_set_mouth_throat matches Python for all {len(lines)} '
              f'(mouth, throat) combinations')
        return 0

    print(f'{len(mismatches)} of {len(lines)} combinations MISMATCHED')
    m, t = mismatches[0]
    py = set_mouth_throat(m, t)
    print(f'  first at mouth={m} throat={t}; Python rows:')
    for i, row in enumerate(py):
        print(f'    f{i + 1}[0:12] = {row[:12]}')
    return 1


if __name__ == '__main__':
    sys.exit(main())
