#!/usr/bin/env python3
"""Differential test: C sam_prepare_frames vs Python prepare_frames.

Covers the golden cases plus a large randomised corpus of phoneme
sequences and voice parameters, comparing the frame count and all eight
output rows by checksum. Rows are compared individually so a failure
says which stage went wrong rather than just "the audio is different".

    python native/tools/verify_prepare.py [n_random]
"""
import glob
import json
import os
import random
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _build import ROOT, build_and_run, take_impl  # noqa: E402
take_impl()
sys.path.insert(0, os.path.join(ROOT, 'nvda-addon', 'synthDrivers', 'sam'))

from renderer import prepare_frames  # noqa: E402

GOLDEN = os.path.join(ROOT, 'native', 'tests', 'golden')

ROWS = ['pitches', 'freq1', 'freq2', 'freq3', 'ampl1', 'ampl2', 'ampl3', 'flags']


def fnv_row(values):
    """Must match hash_int_row/hash_u8_row in dump_prepare.c."""
    h = 2166136261
    for v in values:
        u = v & 0xFFFFFFFF          # 32-bit two's complement
        for b in range(4):
            h = ((h ^ ((u >> (8 * b)) & 0xFF)) * 16777619) & 0xFFFFFFFF
    return h


def build_cases(n_random):
    cases = []
    for p in sorted(glob.glob(os.path.join(GOLDEN, '*.in.json'))):
        spec = json.load(open(p, encoding='utf-8'))
        cases.append((spec['phoneme_list'], spec['params']))

    rnd = random.Random(20260906)
    for _ in range(n_random):
        n = rnd.randint(1, 60)
        pl = [[rnd.randrange(0, 80), rnd.randrange(0, 80), rnd.randrange(0, 10)]
              for _ in range(n)]
        # Bias toward the edges: 0, 255 and the period/question phonemes
        if rnd.random() < 0.3 and pl:
            pl[rnd.randrange(len(pl))][0] = rnd.choice([1, 2])
        cases.append((pl, dict(
            pitch=rnd.choice([0, 1, 32, 64, 128, 254, 255, rnd.randrange(256)]),
            mouth=rnd.choice([0, 128, 255, rnd.randrange(256)]),
            throat=rnd.choice([0, 128, 255, rnd.randrange(256)]),
            speed=rnd.choice([1, 72, 255]),
            singmode=rnd.random() < 0.3,
            inflection=rnd.choice([0, 1, 50, 99, 100, rnd.randrange(101)]),
        )))
    return cases


def write_case_file(cases, path):
    with open(path, 'w') as f:
        for pl, p in cases:
            f.write(f"{p['pitch']} {p['mouth']} {p['throat']} {p.get('speed', 72)} "
                    f"{1 if p['singmode'] else 0} {p['inflection']} {len(pl)}")
            for ent in pl:
                f.write(f" {ent[0]} {ent[1]} {ent[2]}")
            f.write('\n')


def run_dumper(case_path):
    # _CRT_SECURE_NO_WARNINGS is for the host tool's fopen/fscanf; the
    # shipped DLL uses neither. Dumper exit codes: 2=bad args/open,
    # 3=case parse, 4=prepare_frames failed.
    return build_and_run('dump_prepare.c', ['sam_frames.c', 'sam_tables.c'],
                         args=(case_path,), text=True,
                         defines=('_CRT_SECURE_NO_WARNINGS',))


def main():
    n_random = int(sys.argv[1]) if len(sys.argv) > 1 else 400
    cases = build_cases(n_random)

    tmpdir = tempfile.mkdtemp(prefix='samcases')
    try:
        case_path = os.path.join(tmpdir, 'cases.txt')
        write_case_file(cases, case_path)
        out = run_dumper(case_path)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
    if out is None:
        return 1

    lines = [l for l in out.splitlines() if l.strip()]
    if len(lines) != len(cases):
        print(f'expected {len(cases)} results from C, got {len(lines)}')
        return 1

    row_failures = {name: 0 for name in ROWS}
    count_failures = 0
    python_raised = []
    first_bad = None

    for idx, (line, (pl, p)) in enumerate(zip(lines, cases)):
        parts = [int(x) for x in line.split()]
        c_total, c_count, c_hashes = parts[0], parts[1], parts[2:]

        try:
            t, freq, pitches, ampl, flags = prepare_frames(
                pl, p['pitch'], p['mouth'], p['throat'], p['singmode'], p['inflection'])
        except IndexError:
            # The Python renderer raises on some phoneme sequences: see
            # interpolate(), where a write with frame < -len(row) is out of
            # range even for negative indexing. Nothing to compare against;
            # the C skips the write instead of crashing.
            python_raised.append(idx)
            continue
        py_rows = [pitches, freq[0], freq[1], freq[2],
                   ampl[0], ampl[1], ampl[2], flags]

        if (t, len(pitches)) != (c_total, c_count):
            count_failures += 1
            if first_bad is None:
                first_bad = (idx, 'frame count',
                             f'python total={t} count={len(pitches)}, '
                             f'C total={c_total} count={c_count}')
            continue

        for name, py_row, c_hash in zip(ROWS, py_rows, c_hashes):
            if fnv_row(py_row) != c_hash:
                row_failures[name] += 1
                if first_bad is None:
                    first_bad = (idx, name, f'{len(py_row)} frames')

    total_fail = count_failures + sum(row_failures.values())
    compared = len(cases) - len(python_raised)
    if total_fail == 0:
        print(f'sam_prepare_frames matches Python on all {compared} comparable '
              f'cases ({len(cases) - n_random} golden + {n_random} randomised), '
              f'all 8 rows and the frame count')
        if python_raised:
            print(f'  note: Python raised IndexError on {len(python_raised)} '
                  f'randomised case(s); the C survives those. See '
                  f'interpolate() in renderer.py.')
        return 0

    print(f'{total_fail} failure(s) across {len(cases)} cases')
    if count_failures:
        print(f'  frame count mismatched in {count_failures} cases')
    for name, n in row_failures.items():
        if n:
            print(f'  row {name}: {n} cases differ')
    if first_bad:
        idx, what, detail = first_bad
        pl, p = cases[idx]
        print(f'\n  first failure: case {idx}, {what} ({detail})')
        print(f'    params   {p}')
        print(f'    phonemes {pl[:8]}{"..." if len(pl) > 8 else ""}')
    return 1


if __name__ == '__main__':
    sys.exit(main())
