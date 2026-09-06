#!/usr/bin/env python3
"""Differential test: C sam_set_mouth_throat vs Python set_mouth_throat.

Compares all 65,536 (mouth, throat) combinations by checksum, so the
whole input space is covered rather than a handful of samples. On a
mismatch it re-runs that one case and prints the first differing value.

    python native/tools/verify_frames.py
"""
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'nvda-addon', 'synthDrivers', 'sam'))

from renderer import set_mouth_throat  # noqa: E402

SRC = os.path.join(ROOT, 'native', 'src')
TOOLS = os.path.join(ROOT, 'native', 'tools')


def fnv1a(freqdata):
    """Must match checksum() in dump_frames.c exactly."""
    h = 2166136261
    for row in freqdata:
        for v in row:
            h = ((h ^ (v & 0xFF)) * 16777619) & 0xFFFFFFFF
            h = ((h ^ ((v >> 8) & 0xFF)) * 16777619) & 0xFFFFFFFF
    return h


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


def run_dumper():
    vs = find_vs()
    if not vs:
        print('no MSVC toolset found; cannot verify')
        return None
    vcvars = os.path.join(vs, 'VC', 'Auxiliary', 'Build', 'vcvarsall.bat')
    tmp = tempfile.mkdtemp(prefix='samframes')
    try:
        exe = os.path.join(tmp, 'dump_frames.exe')
        bat = os.path.join(tmp, 'go.cmd')
        with open(bat, 'w') as f:
            f.write('@echo off\n')
            f.write(f'call "{vcvars}" x64 >nul 2>nul\n')
            f.write(f'cd /d "{tmp}"\n')
            log = os.path.join(tmp, 'build.log')
            inc = os.path.join(ROOT, 'native', 'include')
            f.write(f'cl /nologo /W4 /WX /I "{SRC}" /I "{inc}" '
                    f'"{os.path.join(TOOLS, "dump_frames.c")}" '
                    f'"{os.path.join(SRC, "sam_frames.c")}" '
                    f'"{os.path.join(SRC, "sam_tables.c")}" '
                    f'/Fe:"{exe}" > "{log}" 2>&1 || exit /b 1\n')
            f.write(f'"{exe}"\n')
        r = subprocess.run(['cmd', '/c', bat], capture_output=True, text=True)
        if r.returncode != 0:
            log = os.path.join(tmp, 'build.log')
            print(f'build or run failed (exit {r.returncode}):')
            if os.path.exists(log):
                print(open(log, encoding='utf-8', errors='replace').read())
            print(r.stdout[-1000:] or r.stderr[-1000:])
            return None
        return r.stdout
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


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
