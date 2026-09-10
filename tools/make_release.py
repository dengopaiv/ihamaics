#!/usr/bin/env python3
r"""Build the one archive this project ships: sam-native.zip.

    python tools/make_release.py

It holds the two things a person installs and nothing else: the NVDA
addon and the desktop app. Both are native. The addon carries the C
renderer with no Python fallback, and sam_gui.exe has no Python behind
it at all, so neither one asks the user to install a runtime first.

The Python addon and sam_gui.py are not shipped. They stay in the
repository as source and as the reference the C engine is verified
against.

Inputs, and what to run when one of them is missing:

    native\build.cmd                    sam_render-x64.dll, -x86.dll
    python native\tools\gen_dict.py     native\data\sam.dict
    gui-native\build.cmd x64            sam_gui-x64.exe
    gui-native\build.cmd x86            sam_gui-x86.exe

The addon is rebuilt here from source, validated, and then zipped, so
the archive can never be staler than the tree it was cut from.
"""
import os
import subprocess
import sys
import time
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

ARCHIVE = os.path.join(ROOT, 'sam-native.zip')
PREFIX = 'sam-native'

ADDON = os.path.join(ROOT, 'nvda-addon', 'sam.nvda-addon')

# Prerequisites the archive is assembled from, with the command that
# produces each one. Checked before anything is built, so a missing
# toolchain is one error message rather than a half-written archive.
INPUTS = [
    (os.path.join(ROOT, 'native', 'build', 'sam_render-x64.dll'),
     r'native\build.cmd'),
    (os.path.join(ROOT, 'native', 'build', 'sam_render-x86.dll'),
     r'native\build.cmd'),
    (os.path.join(ROOT, 'gui-native', 'build', 'sam_gui-x64.exe'),
     r'gui-native\build.cmd x64'),
    (os.path.join(ROOT, 'gui-native', 'build', 'sam_gui-x86.exe'),
     r'gui-native\build.cmd x86'),
]

README = """SAM (Software Automatic Mouth) - I Have A Mouth And I Can Scream

The 1982 Commodore 64 speech synthesizer, as an NVDA voice and a
desktop app. Both are in this archive, and both are self-contained:
there is no Python or other runtime to install first.


THE NVDA ADDON  --  sam.nvda-addon

    1. Double-click sam.nvda-addon with NVDA running
    2. Accept the prompt, then restart NVDA
    3. NVDA menu -> Preferences -> Settings -> Speech
    4. Choose "SAM (Software Automatic Mouth)"

Rate, pitch, inflection and volume behave as usual. Mouth, Throat and
Sing mode are added to the settings ring. Needs NVDA 2023.1 or newer.


THE DESKTOP APP  --  sam_gui-x64.exe, sam_gui-x86.exe

Run the one that matches your Windows: x64 on a 64-bit system, x86 on
a 32-bit one. Nothing to install, and it writes no settings outside
its own window - copy it wherever you like.

Type text, set Speed, Pitch, Mouth, Throat and Inflection, pick a
voice preset, then Preview or save a WAV. Phoneme mode takes SAM's own
phoneme spelling instead of English, and Sing mode holds each vowel on
its pitch.


LICENCE

SAM is reverse-engineered software whose copyright is held by
SoftVoice, Inc.; it is not, and cannot be, under an open source
licence. The bundled CMU Pronouncing Dictionary is licensed separately
by Carnegie Mellon University. LICENSE and NOTICE.md in this archive
have the full position and the per-component attributions.


SOURCE

https://github.com/dengopaiv/ihamaics
"""


def run(argv, what):
    print(f'=== {what} ===')
    r = subprocess.run([sys.executable] + argv, cwd=ROOT)
    if r.returncode != 0:
        raise SystemExit(f'ERROR: {what} failed')
    print()


def main():
    missing = [(p, cmd) for p, cmd in INPUTS if not os.path.exists(p)]
    if missing:
        print('ERROR: the release needs binaries that are not built yet.\n')
        for path, cmd in missing:
            print(f'  {os.path.relpath(path, ROOT)}')
            print(f'      build it with:  {cmd}')
        return 1

    run([os.path.join('nvda-addon', 'package_addon.py')], 'building the addon')
    run([os.path.join('nvda-addon', 'validate_addon.py')], 'validating the addon')

    members = [(ADDON, 'sam.nvda-addon')]
    members += [(p, os.path.basename(p)) for p, _ in INPUTS
                if p.endswith('.exe')]
    members += [(os.path.join(ROOT, 'LICENSE'), 'LICENSE'),
                (os.path.join(ROOT, 'NOTICE.md'), 'NOTICE.md')]

    # One timestamp for every entry, taken from the newest input. The
    # archive is committed, so an unchanged tree has to produce an
    # unchanged file rather than a fresh diff on every build. The addon
    # was just rebuilt, so its mtime is always "now" - it stamps its own
    # entries deterministically, and that stamp is what counts here.
    with zipfile.ZipFile(ADDON) as addon_zf:
        stamps = [max(i.date_time for i in addon_zf.infolist())]
    stamps += [time.localtime(os.path.getmtime(p))[:6]
               for p, _ in members if p != ADDON]
    stamp = max(stamps)

    if os.path.exists(ARCHIVE):
        os.remove(ARCHIVE)

    print('=== writing the archive ===')
    with zipfile.ZipFile(ARCHIVE, 'w', zipfile.ZIP_DEFLATED,
                         compresslevel=9) as zf:
        info = zipfile.ZipInfo(f'{PREFIX}/README.txt', stamp)
        info.compress_type = zipfile.ZIP_DEFLATED
        info.external_attr = 0o644 << 16
        zf.writestr(info, README.encode('utf-8'))
        print(f'  {info.filename}')

        for path, name in members:
            with open(path, 'rb') as f:
                data = f.read()
            info = zipfile.ZipInfo(f'{PREFIX}/{name}', stamp)
            # The addon is a zip already; deflating it again buys
            # nothing and costs a second on every build.
            info.compress_type = (zipfile.ZIP_STORED
                                  if name.endswith('.nvda-addon')
                                  else zipfile.ZIP_DEFLATED)
            info.external_attr = 0o644 << 16
            zf.writestr(info, data)
            print(f'  {info.filename}: {len(data) / 1024:.0f} KB')

    # The loose .nvda-addon was only ever an intermediate. Removing it
    # keeps sam-native.zip the one archive in the tree, which is the
    # point of building it this way.
    os.remove(ADDON)

    size = os.path.getsize(ARCHIVE)
    print(f'\nCreated: {os.path.relpath(ARCHIVE, ROOT)} '
          f'({size / 1024 / 1024:.2f} MB)')
    print(f'Removed: {os.path.relpath(ADDON, ROOT)} '
          f'(it ships inside the archive)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
