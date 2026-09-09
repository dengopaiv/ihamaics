#!/usr/bin/env python3
"""Differential test: the built GUI executable vs sam_gui.py.

The point of driving the real binary through its --selftest mode, rather
than a harness that merely shares its sources, is that this checks what
ships: the resource-linked dictionary, the static CRT build, the voice
struct as the GUI fills it in, and the WAV header the GUI writes. A test
that shared the sources would pass while the shipped exe was missing its
dictionary.

Both architectures are checked, because both are shipped.

    python native/tools/verify_gui.py

Build them first with gui-native\\build.cmd x64 and x86.
"""
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _build import ROOT  # noqa: E402

sys.path.insert(0, os.path.join(ROOT, 'nvda-addon', 'synthDrivers', 'sam'))

from sam import text_to_wav  # noqa: E402

BUILD = os.path.join(ROOT, 'gui-native', 'build')

# speed, pitch, mouth, throat, inflection, phoneme_mode, text
CASES = [
    # The defaults, which is what the window opens on.
    (72, 64, 128, 128, 50, 0, 'Hello, my name is Sam.'),
    (72, 64, 128, 128, 50, 0, 'The quick brown fox jumps over the lazy dog.'),

    # Each control away from its default, one at a time.
    (1, 64, 128, 128, 50, 0, 'Fastest possible speed.'),
    (255, 64, 128, 128, 50, 0, 'Slowest possible speed.'),
    (72, 0, 128, 128, 50, 0, 'Pitch at the floor.'),
    (72, 255, 128, 128, 50, 0, 'Pitch at the ceiling.'),
    (72, 64, 0, 128, 50, 0, 'Mouth closed.'),
    (72, 64, 255, 128, 50, 0, 'Mouth wide open.'),
    (72, 64, 128, 0, 50, 0, 'Throat at zero.'),
    (72, 64, 128, 255, 50, 0, 'Throat at maximum.'),
    (72, 64, 128, 128, 0, 0, 'Monotone, no inflection at all.'),
    (72, 64, 128, 128, 100, 0, 'Wild inflection, very dramatic.'),

    # The voice presets in sam.py, which no GUI exposes but which are the
    # combinations most likely to be typed in by hand.
    (72, 64, 160, 110, 50, 0, 'Elf preset.'),
    (92, 60, 190, 190, 50, 0, 'Little robot preset.'),
    (82, 72, 105, 110, 50, 0, 'Stuffy guy preset.'),
    (82, 32, 145, 145, 50, 0, 'Little old lady preset.'),
    (100, 64, 200, 150, 50, 0, 'Extra terrestrial preset.'),

    # Phoneme mode: the Convert button's own output, fed back in.
    (72, 64, 128, 128, 50, 1, 'DHAX KAET IHZ AH5GLIY.'),
    (72, 64, 128, 128, 50, 1, '/HEHLOW4'),
    (72, 64, 128, 128, 50, 1, 'AY4 AEM SAE4M'),
    (150, 64, 128, 128, 50, 1, 'AA5RAA5'),

    # Punctuation, digits and the awkward shapes.
    (72, 64, 128, 128, 50, 0, 'What? Really! Yes, indeed.'),
    (72, 64, 128, 128, 50, 0, 'Numbers 1 2 3 are not expanded here.'),
    (72, 64, 128, 128, 50, 0, "It's a well-known e-mail address."),
    (72, 64, 128, 128, 50, 0, 'Aalborg'),       # the commented dict entry
    (72, 64, 128, 128, 50, 0, 'incomprehensibility'),
    (150, 64, 128, 128, 50, 0, 'incomprehensibility'),
]


def python_wav(speed, pitch, mouth, throat, inflection, phoneme_mode, text):
    """What sam_gui.py's synthesize() would produce for these controls."""
    return text_to_wav(text, pitch=pitch, speed=speed, mouth=mouth,
                       throat=throat, inflection=inflection,
                       phonetic=bool(phoneme_mode))


def check(exe, tmp):
    name = os.path.basename(exe)
    failures = 0

    for i, case in enumerate(CASES):
        speed, pitch, mouth, throat, infl, mode, text = case
        out = os.path.join(tmp, 'case%02d.wav' % i)

        r = subprocess.run(
            [exe, '--selftest', str(speed), str(pitch), str(mouth),
             str(throat), str(infl), str(mode), out, text],
            capture_output=True)
        want = python_wav(*case)

        # Python returns None when the phoneme string will not parse, and
        # text_to_wav's callers treat that as "no audio". The exe reports
        # the same thing as a non-zero exit, so refusing together is a
        # match. "Aalborg" is the case that exercises it: sixteen
        # dictionary entries carry a trailing comment that cmudict.py
        # stores as pronunciation, and the result does not parse.
        if want is None:
            if r.returncode == 0:
                print('  %-18s case %d: Python produced nothing but the '
                      'exe succeeded: %r' % (name, i, text))
                failures += 1
            continue

        if r.returncode != 0:
            print('  %-18s case %d exited %d: %r'
                  % (name, i, r.returncode, text))
            failures += 1
            continue

        with open(out, 'rb') as f:
            got = f.read()

        if got != want:
            where = next((k for k in range(min(len(got), len(want)))
                          if got[k] != want[k]), min(len(got), len(want)))
            print('  %-18s case %d DIFFERS: %r' % (name, i, text))
            print('      python %d bytes, exe %d bytes, first difference at %d'
                  % (len(want), len(got), where))
            failures += 1

    if failures == 0:
        print('  %-18s byte-identical to the Python GUI on all %d cases'
              % (name, len(CASES)))
    return failures


def main():
    exes = [os.path.join(BUILD, n)
            for n in ('sam_gui-x64.exe', 'sam_gui-x86.exe')]
    missing = [e for e in exes if not os.path.exists(e)]
    if missing:
        for e in missing:
            print('missing: %s' % os.path.relpath(e, ROOT))
        print('Build with:  gui-native\\build.cmd x64   (and x86)')
        return 1

    failures = 0
    with tempfile.TemporaryDirectory(prefix='samgui') as tmp:
        for exe in exes:
            failures += check(exe, tmp)

    if failures:
        print('\n%d comparison(s) failed' % failures)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
