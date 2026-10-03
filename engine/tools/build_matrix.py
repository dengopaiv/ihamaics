#!/usr/bin/env python3
"""Configure, build and test engine/ on every leg of the toolchain matrix.

    python engine/tools/build_matrix.py [leg ...]

Legs (docs/c17-rewrite-plan.md section 3.4):

  msvc       MSVC, x64, Ninja, from a vcvarsall developer shell
  clang-cl   clang-cl from Visual Studio's bundled LLVM, same shell
  wsl-gcc    gcc under WSL
  wsl-clang  clang under WSL

Each leg builds in engine/build-<leg>, runs ctest, and counts compiler
warnings in the build log. A stage's exit test needs every leg built,
every test passing and zero warnings; the summary table says which.

MSVC alone does not prove the code is C17: klattsch found it accepts
binary literals and digit separators under /std:c17. That is why every
leg runs from the first stage, not just the one at hand.
"""
import os
import re
import subprocess
import sys

ENGINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.dirname(ENGINE)
sys.path.insert(0, os.path.join(ROOT, 'native', 'tools'))
from _build import find_vs  # noqa: E402

LEGS = ('msvc', 'clang-cl', 'wsl-gcc', 'wsl-clang')

WARNING = re.compile(r'warning[: ]', re.IGNORECASE)


def wsl_path(path):
    """C:\\a\\b to /mnt/c/a/b, for handing a Windows path to WSL."""
    drive, rest = os.path.splitdrive(os.path.abspath(path))
    return '/mnt/' + drive[0].lower() + rest.replace('\\', '/')


def windows_leg(leg):
    vs = find_vs()
    if vs is None:
        return None, 'no Visual Studio found'
    vcvars = os.path.join(vs, 'VC', 'Auxiliary', 'Build', 'vcvarsall.bat')
    build = os.path.join(ENGINE, 'build-' + leg)
    cc = 'cl' if leg == 'msvc' else 'clang-cl'
    script = (
        f'call "{vcvars}" x64 >nul 2>nul || exit /b 1\n'
        f'cmake -S "{ENGINE}" -B "{build}" -G Ninja -DCMAKE_C_COMPILER={cc} '
        f'--fresh || exit /b 1\n'
        f'cmake --build "{build}" || exit /b 1\n'
        f'ctest --test-dir "{build}" --output-on-failure || exit /b 1\n')
    bat = os.path.join(ENGINE, 'build-' + leg + '.cmd')
    os.makedirs(build, exist_ok=True)
    with open(bat, 'w') as f:
        f.write('@echo off\n' + script)
    try:
        r = subprocess.run(['cmd', '/c', bat], capture_output=True,
                           text=True, errors='replace')
    finally:
        os.remove(bat)
    return r, None


def wsl_leg(leg):
    cc = 'gcc' if leg == 'wsl-gcc' else 'clang'
    src = wsl_path(ENGINE)
    # Built on the Linux file system, not under /mnt/c: faster, and it
    # keeps Linux build trees out of the Windows checkout.
    build = '$HOME/sam-engine-build/' + leg
    script = (
        f'set -e; rm -rf "{build}"; '
        f'CC={cc} cmake -S "{src}" -B "{build}" -G Ninja; '
        f'cmake --build "{build}"; '
        f'ctest --test-dir "{build}" --output-on-failure')
    try:
        r = subprocess.run(['wsl', '-e', 'bash', '-lc', script],
                           capture_output=True, text=True, errors='replace')
    except FileNotFoundError:
        return None, 'WSL not installed'
    return r, None


def main(argv):
    legs = argv[1:] or LEGS
    rows = []
    for leg in legs:
        if leg not in LEGS:
            print(f'unknown leg {leg}; choose from {", ".join(LEGS)}')
            return 2
        r, why = (windows_leg if leg in ('msvc', 'clang-cl') else wsl_leg)(leg)
        if r is None:
            rows.append((leg, 'skipped', '-', why))
            continue
        log = r.stdout + r.stderr
        warnings = [ln for ln in log.splitlines() if WARNING.search(ln)]
        # ctest 3.x always prints the failure count; 4.x drops it when
        # nothing failed ("100% tests passed out of 1").
        tests = re.search(r'\d+% tests passed(?:, (\d+) tests failed)? out of (\d+)', log)
        # A skipped test counts as passed in ctest's own percentage, so
        # skips are counted from its "did not run" list and shown apart.
        skipped = len(re.findall(r'^\s*\d+ - \S+ \(Skipped\)', log, re.M))
        if tests:
            total, failed = int(tests.group(2)), int(tests.group(1) or 0)
            tested = f'{total - failed - skipped}/{total}'
            if skipped:
                tested += f' ({skipped} skipped)'
        else:
            tested = '-'
        rows.append((leg, 'ok' if r.returncode == 0 else 'FAILED',
                     tested, f'{len(warnings)} warnings'))
        if r.returncode != 0 or warnings:
            print(f'--- {leg} ---')
            print('\n'.join(warnings) if r.returncode == 0 else log[-4000:])

    print(f'{"leg":<10} {"build":<8} {"tests":<18} notes')
    for leg, state, tested, note in rows:
        print(f'{leg:<10} {state:<8} {tested:<18} {note}')
    bad = any(state != 'ok' or note != '0 warnings' for _, state, _, note in rows)
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
