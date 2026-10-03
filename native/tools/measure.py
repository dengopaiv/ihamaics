#!/usr/bin/env python3
"""Measure the renderer: the baseline and after-table of the C17 rewrite.

    python native/tools/measure.py [--impl native|engine] [--reps N]

docs/c17-rewrite-plan.md section 7: any speed or size claim about the
rewrite cites a table made by this script, on one named machine, for
both implementations. Stage R.0 ran it on native/; stage R.9 runs it on
engine/ on the same machine.

What it prints, all for the renderer alone (the front end was 0.3 % of
synthesis cost when docs/c-engine-port.md profiled it, and is not timed):

  - SENTENCE below, rendered at the default voice: median and minimum
    wall time per render, direct (bench_render.c) and through ctypes as
    the NVDA driver calls it, and the real-time factor of the median;
  - the latency grid of docs/c-engine-port.md: "a", "the" and
    "comfortable" at speeds 15, 72 and 150, and the worst case,
    "incomprehensibility" at 150, through ctypes;
  - the size of the renderer DLL and of the GUI executable.

Phonemes come from the Python front end, so both implementations render
exactly the same input. Every timing is the median of --reps renders
after one untimed warm-up render.
"""
import ctypes
import os
import platform
import statistics
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _build import ROOT, build_and_run, engine_dll, take_impl  # noqa: E402
take_impl()
import _build  # noqa: E402
import verify_render  # noqa: E402  (its ctypes loader and structs)

sys.path.insert(0, os.path.join(ROOT, 'nvda-addon', 'synthDrivers', 'sam'))
from reciter import text_to_phonemes  # noqa: E402
from parser import parse  # noqa: E402

# Twenty words, fixed so the R.9 run renders exactly what R.0 did.
# docs/c-engine-port.md timed "a 20-word sentence" but did not record
# which one, so its 17.2 ms is not directly comparable with these.
SENTENCE = ('The quick brown fox jumps over the lazy dog while seven '
            'wizards quietly judge every boxing match in the town')

DEFAULT = dict(pitch=64, mouth=128, throat=128, speed=72,
               singmode=False, inflection=50)

RATE = 22050


def phonemes_for(text):
    ph = text_to_phonemes(text)
    lst = parse(ph) if ph else None
    if not lst:
        raise SystemExit('front end rejected %r' % text)
    return lst


def time_ctypes(lib, lst, p, reps):
    arr = (verify_render.Phoneme * len(lst))(
        *[verify_render.Phoneme(e[0], e[1], e[2]) for e in lst])
    voice = verify_render.Voice(p['pitch'], p['mouth'], p['throat'], p['speed'],
                                1 if p['singmode'] else 0, p['inflection'])
    need = lib.sam_render(arr, len(lst), ctypes.byref(voice), None, 0)
    buf = (ctypes.c_ubyte * max(need, 1))()
    n = lib.sam_render(arr, len(lst), ctypes.byref(voice), buf, len(buf))
    times = []
    for _ in range(reps):
        t0 = time.perf_counter_ns()
        lib.sam_render(arr, len(lst), ctypes.byref(voice), buf, len(buf))
        times.append(time.perf_counter_ns() - t0)
    return n, min(times), statistics.median(times)


def time_direct(lst, p, reps):
    head = '%d %d %d %d %d %d %d\n%d\n' % (
        p['pitch'], p['mouth'], p['throat'], p['speed'],
        1 if p['singmode'] else 0, p['inflection'], reps, len(lst))
    body = ''.join('%d %d %d\n' % tuple(e) for e in lst)
    out = build_and_run('bench_render.c',
                        ['sam_render.c', 'sam_frames.c', 'sam_tables.c'],
                        stdin_data=(head + body).encode(), text=True,
                        defines=('_CRT_SECURE_NO_WARNINGS',),
                        # The flags native\build.cmd gives the DLL, so the
                        # direct and ctypes figures time the same code.
                        flags=('/O2', '/MT'))
    if out is None:
        return None
    n, mn, med = (int(x) for x in out.split())
    return n, mn, med


def ms(ns):
    return '%.3f ms' % (ns / 1e6)


def machine():
    cpu = platform.processor()
    try:
        r = subprocess.run(['powershell', '-NoProfile', '-Command',
                            '(Get-CimInstance Win32_Processor).Name'],
                           capture_output=True, text=True, timeout=30)
        cpu = r.stdout.strip() or cpu
    except (OSError, subprocess.SubprocessError):
        pass
    return '%s; %s %s; Python %s' % (cpu, platform.system(), platform.version(),
                                     platform.python_version())


def main():
    reps = 200
    if '--reps' in sys.argv:
        reps = int(sys.argv[sys.argv.index('--reps') + 1])

    lib = verify_render.load()
    if lib is None:
        return 1

    print('implementation: %s' % _build.IMPL)
    print('machine:        %s' % machine())
    print('renders:        median of %d, after one warm-up\n' % reps)

    lst = phonemes_for(SENTENCE)
    n, mn, med = time_ctypes(lib, lst, DEFAULT, reps)
    audio_ns = n / RATE * 1e9
    print('sentence (%d words, %d samples, %.0f ms of audio):'
          % (len(SENTENCE.split()), n, audio_ns / 1e6))
    print('  ctypes   median %s  min %s  real-time factor %.4f'
          % (ms(med), ms(mn), med / audio_ns))
    d = time_direct(lst, DEFAULT, reps)
    if d is None:
        print('  direct   not measured (bench_render did not build or run)')
    else:
        dn, dmn, dmed = d
        if dn != n:
            print('  direct   sample count %d differs from ctypes %d' % (dn, n))
            return 1
        print('  direct   median %s  min %s  real-time factor %.4f'
              % (ms(dmed), ms(dmn), dmed / audio_ns))

    print('\nlatency through ctypes, median per render:')
    words = ('a', 'the', 'comfortable')
    print('  %-6s' % 'speed' + ''.join('%16s' % w for w in words))
    for speed in (15, 72, 150):
        p = dict(DEFAULT, speed=speed)
        cells = [time_ctypes(lib, phonemes_for(w), p, reps)[2] for w in words]
        print('  %-6d' % speed + ''.join('%16s' % ms(c) for c in cells))
    worst = time_ctypes(lib, phonemes_for('incomprehensibility'),
                        dict(DEFAULT, speed=150), reps)
    print('  worst case, "incomprehensibility" at speed 150: %s' % ms(worst[2]))

    print('\nsizes:')
    dll = engine_dll()
    print('  %-24s %8d bytes' % (os.path.relpath(dll, ROOT), os.path.getsize(dll)))
    gui = os.path.join(ROOT, 'gui-native', 'build', 'sam_gui-x64.exe')
    if _build.IMPL == 'native' and os.path.exists(gui):
        print('  %-24s %8d bytes' % (os.path.relpath(gui, ROOT), os.path.getsize(gui)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
