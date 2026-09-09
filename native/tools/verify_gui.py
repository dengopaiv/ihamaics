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
import re
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _build import ROOT  # noqa: E402

sys.path.insert(0, os.path.join(ROOT, 'nvda-addon', 'synthDrivers', 'sam'))

from sam import text_to_wav, VOICE_PRESETS  # noqa: E402

BUILD = os.path.join(ROOT, 'gui-native', 'build')

# The presets the GUI's combo offers, from VOICE_PRESETS in sam.py. They
# must stay in step with the PRESETS table in gui-native/sam_gui.cpp, so
# they are read from the Python rather than retyped: choosing a preset in
# the GUI only writes these four numbers, which means driving --selftest
# with them is driving the preset.
PRESETS = [
    ('SAM', 'sam'),
    ('Elf', 'elf'),
    ('Little Robot', 'little_robot'),
    ('Stuffy Guy', 'stuffy_guy'),
    ('Little Old Lady', 'little_old_lady'),
    ('Extra-Terrestrial', 'extra_terrestrial'),
]

# speed, pitch, mouth, throat, inflection, sing_mode, phoneme_mode, text
CASES = [
    # The defaults, which is what the window opens on.
    (72, 64, 128, 128, 50, 0, 0, 'Hello, my name is Sam.'),
    (72, 64, 128, 128, 50, 0, 0,
     'The quick brown fox jumps over the lazy dog.'),

    # Each control away from its default, one at a time.
    (1, 64, 128, 128, 50, 0, 0, 'Fastest possible speed.'),
    (255, 64, 128, 128, 50, 0, 0, 'Slowest possible speed.'),
    (72, 0, 128, 128, 50, 0, 0, 'Pitch at the floor.'),
    (72, 255, 128, 128, 50, 0, 0, 'Pitch at the ceiling.'),
    (72, 64, 0, 128, 50, 0, 0, 'Mouth closed.'),
    (72, 64, 255, 128, 50, 0, 0, 'Mouth wide open.'),
    (72, 64, 128, 0, 50, 0, 0, 'Throat at zero.'),
    (72, 64, 128, 255, 50, 0, 0, 'Throat at maximum.'),
    (72, 64, 128, 128, 0, 0, 0, 'Monotone, no inflection at all.'),
    (72, 64, 128, 128, 100, 0, 0, 'Wild inflection, very dramatic.'),

    # Sing mode, which the checkbox turns on.
    (72, 64, 128, 128, 50, 1, 0, 'Singing this one.'),
    (72, 64, 128, 128, 0, 1, 0, 'Singing flat.'),
    (72, 64, 128, 128, 100, 1, 0, 'Singing with wild inflection.'),
    (150, 32, 145, 145, 50, 1, 0, 'Slow singing, old lady voice.'),
    (72, 64, 128, 128, 50, 1, 1, 'AA5RAA5 IY4'),

    # Phoneme mode: the Convert button's own output, fed back in.
    (72, 64, 128, 128, 50, 0, 1, 'DHAX KAET IHZ AH5GLIY.'),
    (72, 64, 128, 128, 50, 0, 1, '/HEHLOW4'),
    (72, 64, 128, 128, 50, 0, 1, 'AY4 AEM SAE4M'),
    (150, 64, 128, 128, 50, 0, 1, 'AA5RAA5'),

    # Punctuation, digits and the awkward shapes.
    (72, 64, 128, 128, 50, 0, 0, 'What? Really! Yes, indeed.'),
    (72, 64, 128, 128, 50, 0, 0, 'Numbers 1 2 3 are not expanded here.'),
    (72, 64, 128, 128, 50, 0, 0, "It's a well-known e-mail address."),
    (72, 64, 128, 128, 50, 0, 0, 'Aalborg'),    # the commented dict entry
    (72, 64, 128, 128, 50, 0, 0, 'incomprehensibility'),
    (150, 64, 128, 128, 50, 0, 0, 'incomprehensibility'),
]


def check_presets_in_sync():
    """The C preset table must still say what sam.py says.

    gui-native/sam_gui.cpp carries its own copy of the numbers, because a
    Win32 combo cannot import a Python dict. A copy is a thing that drifts,
    and this project has already had these four values transposed once -
    commit 2116629, "Fix transposed throat and mouth in voice presets". So
    the copy is diffed against the original rather than trusted.
    """
    src = os.path.join(ROOT, 'gui-native', 'sam_gui.cpp')
    with open(src, encoding='utf-8') as f:
        text = f.read()

    block = re.search(r'static const PresetSpec PRESETS\[\]\s*=\s*\{(.*?)\};',
                      text, re.S)
    if block is None:
        print('could not find the PRESETS table in sam_gui.cpp')
        return 1

    found = re.findall(r'\{\s*L"([^"]+)"\s*,\s*(\d+)\s*,\s*(\d+)\s*,'
                       r'\s*(\d+)\s*,\s*(\d+)\s*\}', block.group(1))
    if len(found) != len(PRESETS):
        print('sam_gui.cpp has %d presets, verify_gui.py expects %d'
              % (len(found), len(PRESETS)))
        return 1

    failures = 0
    for i, ((label, key), entry) in enumerate(zip(PRESETS, found)):
        c_name, speed, pitch, mouth, throat = entry
        want = VOICE_PRESETS[key]
        got = {'speed': int(speed), 'pitch': int(pitch),
               'mouth': int(mouth), 'throat': int(throat)}
        if c_name != label:
            print('preset %d: sam_gui.cpp calls it %r, expected %r'
                  % (i, c_name, label))
            failures += 1
        if got != want:
            print('preset %r DIFFERS: sam_gui.cpp %s, sam.py %s'
                  % (label, got, want))
            failures += 1

    if not failures:
        print('preset table: all %d match VOICE_PRESETS in sam.py'
              % len(PRESETS))
    return failures


def preset_cases():
    """Every preset the combo offers, spoken and sung."""
    out = []
    for label, key in PRESETS:
        p = VOICE_PRESETS[key]
        for sing in (0, 1):
            out.append((p['speed'], p['pitch'], p['mouth'], p['throat'],
                        50, sing, 0, '%s preset.' % label))
    return out


def python_wav(speed, pitch, mouth, throat, inflection, sing_mode,
               phoneme_mode, text):
    """What sam_gui.py's synthesize() would produce for these controls."""
    return text_to_wav(text, pitch=pitch, speed=speed, mouth=mouth,
                       throat=throat, inflection=inflection,
                       singmode=bool(sing_mode),
                       phonetic=bool(phoneme_mode))


def check(exe, tmp):
    name = os.path.basename(exe)
    failures = 0

    cases = CASES + preset_cases()

    for i, case in enumerate(cases):
        speed, pitch, mouth, throat, infl, sing, mode, text = case
        out = os.path.join(tmp, 'case%02d.wav' % i)

        r = subprocess.run(
            [exe, '--selftest', str(speed), str(pitch), str(mouth),
             str(throat), str(infl), str(sing), str(mode), out, text],
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
              % (name, len(cases)))
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

    failures = check_presets_in_sync()
    with tempfile.TemporaryDirectory(prefix='samgui') as tmp:
        for exe in exes:
            failures += check(exe, tmp)

    if failures:
        print('\n%d comparison(s) failed' % failures)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
