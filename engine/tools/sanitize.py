#!/usr/bin/env python3
"""The renderer under AddressSanitizer and UBSan, on the Linux legs.

    python engine/tools/sanitize.py [N]

Stage R.4 of the C17 rewrite (docs/c17/04-r4-renderer.md section 4.6;
plan section 5, "Sanitizers"). For each of wsl-gcc and wsl-clang, this
builds engine/ under WSL in $HOME/sam-engine-build/<leg>-sanitize, as a
Debug build (asserts on) at -O1 with

    -fsanitize=address,undefined,float-cast-overflow
    -fno-sanitize-recover=all

and runs its dump_render over one case file. The same file goes through
the MSVC leg's dump_render.exe on Windows, and the two outputs must be
identical line for line. Any sanitizer report ends the run with a
nonzero exit, which counts as a failure here.

The case file holds the 16 golden cases, verify_render.py's first 485
randomised ones (the Python's domain), one long utterance with the
glottal pulse stuck (where native/ overflows an int), and N cases (default 5,000) from
diff_render.py's wider generator, which reaches what the Python raises
on. It is written next to the MSVC build, where WSL can read it.
"""
import glob
import json
import os
import random
import subprocess
import sys

ENGINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.dirname(ENGINE)
sys.path.insert(0, os.path.join(ROOT, 'native', 'tools'))
sys.path.insert(0, os.path.join(ENGINE, 'tools'))
import diff_render  # noqa: E402
from build_matrix import wsl_path  # noqa: E402
from verify_render import fuzz_cases  # noqa: E402

MSVC = os.environ.get('SAM_ENGINE_BUILD', os.path.join(ENGINE, 'build-msvc'))
FLAGS = ('-fsanitize=address,undefined,float-cast-overflow '
         '-fno-sanitize-recover=all -fno-omit-frame-pointer -O1 -g')


def line(pl, v):
    pitch, mouth, throat, speed, sing, infl = v
    return ' '.join(str(x) for x in (pitch, mouth, throat, speed, sing, infl,
                                     len(pl), *[y for e in pl for y in e]))


def write_cases(path, n):
    rows = []
    for spec in sorted(glob.glob(os.path.join(ROOT, 'native', 'tests', 'golden',
                                              '*.in.json'))):
        s = json.load(open(spec, encoding='utf-8'))
        p = s['params']
        rows.append(line(s['phoneme_list'], (p['pitch'], p['mouth'], p['throat'],
                                             p.get('speed', 72), int(p['singmode']),
                                             p['inflection'])))
    for pl, p in fuzz_cases(485):
        rows.append(line(pl, (p['pitch'], p['mouth'], p['throat'], p['speed'],
                              int(p['singmode']), p['inflection'])))
    # The stuck pulse at length: sing mode, pitch 0 and inflection 0 make
    # every pitch 0, so the formants' phases never reset. The Python's
    # phase passes 8,388,608, where native/'s int phase * 256 overflows
    # (section 4.6). The Python gives 2,528,172 samples, FNV 4004425672.
    rows.append(line([(9, 255, 0)] * 12, (0, 128, 128, 255, 1, 0)))
    rnd = random.Random(5)
    for _ in range(n):
        rows.append(line(*diff_render.case(rnd)))
    with open(path, 'w', newline='\n') as f:
        f.write('\n'.join(rows) + '\n')
    return len(rows)


def main(argv):
    n = int(argv[1]) if len(argv) > 1 else 5000
    exe = os.path.join(MSVC, 'dump_render.exe')
    if not os.path.exists(exe):
        print(exe + ' not built; run engine/tools/build_matrix.py msvc')
        return 1
    cases = os.path.join(MSVC, 'sanitize_cases.txt')
    total = write_cases(cases, n)
    want = subprocess.run([exe, cases], capture_output=True, text=True,
                          check=True).stdout.splitlines()
    print('%d cases; msvc dump_render: %d lines' % (total, len(want)))

    failed = 0
    for leg, cc in (('wsl-gcc', 'gcc'), ('wsl-clang', 'clang')):
        build = '$HOME/sam-engine-build/%s-sanitize' % leg
        script = (
            'set -e; rm -rf "{b}"; '
            'CC={cc} cmake -S "{src}" -B "{b}" -G Ninja -DCMAKE_BUILD_TYPE=Debug '
            '-DCMAKE_C_FLAGS="{fl}" -DCMAKE_EXE_LINKER_FLAGS="{fl}" '
            '-DCMAKE_SHARED_LINKER_FLAGS="{fl}" >/dev/null; '
            'cmake --build "{b}" --target dump_render >/dev/null; '
            '"{b}/dump_render" "{cases}"'
        ).format(b=build, cc=cc, src=wsl_path(ENGINE), fl=FLAGS,
                 cases=wsl_path(cases))
        r = subprocess.run(['wsl', '-e', 'bash', '-lc', script],
                           capture_output=True, text=True, errors='replace')
        got = r.stdout.splitlines()
        reports = [s for s in r.stderr.splitlines()
                   if 'runtime error' in s or 'Sanitizer' in s]
        same = got == want
        ok = r.returncode == 0 and same and not reports
        failed += not ok
        print('%-10s exit %d, %d lines, %s msvc, %d sanitizer reports: %s'
              % (leg, r.returncode, len(got), 'same as' if same else 'DIFFERENT from',
                 len(reports), 'ok' if ok else 'FAILED'))
        if not ok:
            print('\n'.join((reports or r.stderr.splitlines())[:20]))
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
