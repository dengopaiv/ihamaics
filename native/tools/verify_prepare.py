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
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'nvda-addon', 'synthDrivers', 'sam'))

from renderer import prepare_frames  # noqa: E402

SRC = os.path.join(ROOT, 'native', 'src')
TOOLS = os.path.join(ROOT, 'native', 'tools')
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


def find_vs():
    vswhere = os.path.join(os.environ.get('ProgramFiles(x86)', r'C:\Program Files (x86)'),
                           'Microsoft Visual Studio', 'Installer', 'vswhere.exe')
    if not os.path.exists(vswhere):
        return None
    out = subprocess.run(
        [vswhere, '-latest', '-products', '*', '-requires',
         'Microsoft.VisualStudio.Component.VC.Tools.x86.x64',
         '-property', 'installationPath'],
        capture_output=True, text=True).stdout.strip()
    return out or None


def run_dumper(case_path):
    vs = find_vs()
    if not vs:
        print('no MSVC toolset found; cannot verify')
        return None
    vcvars = os.path.join(vs, 'VC', 'Auxiliary', 'Build', 'vcvarsall.bat')
    tmp = tempfile.mkdtemp(prefix='samprep')
    try:
        exe = os.path.join(tmp, 'dump_prepare.exe')
        bat = os.path.join(tmp, 'go.cmd')
        log = os.path.join(tmp, 'build.log')
        inc = os.path.join(ROOT, 'native', 'include')
        with open(bat, 'w') as f:
            f.write('@echo off\n')
            f.write(f'call "{vcvars}" x64 >nul 2>nul\n')
            f.write(f'cd /d "{tmp}"\n')
            # cl writes diagnostics to stdout, so log them rather than
            # discarding them: a swallowed /WX error looks like a silent
            # failure. _CRT_SECURE_NO_WARNINGS is for the host tool's
            # fopen/fscanf; the shipped DLL uses neither.
            f.write(f'cl /nologo /W4 /WX /D_CRT_SECURE_NO_WARNINGS '
                    f'/I "{SRC}" /I "{inc}" '
                    f'"{os.path.join(TOOLS, "dump_prepare.c")}" '
                    f'"{os.path.join(SRC, "sam_frames.c")}" '
                    f'"{os.path.join(SRC, "sam_tables.c")}" '
                    f'/Fe:"{exe}" > "{log}" 2>&1 || exit /b 1\n')
            f.write(f'"{exe}" "{case_path}"\n')
        r = subprocess.run(['cmd', '/c', bat], capture_output=True, text=True)
        if r.returncode != 0:
            print(f'build or run failed (exit {r.returncode}); dumper exit codes: '
                  f'2=bad args/open, 3=case parse, 4=prepare_frames failed')
            if os.path.exists(log):
                print(open(log, encoding='utf-8', errors='replace').read())
            print(r.stdout[-2000:] or r.stderr[-2000:])
            return None
        return r.stdout
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


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
