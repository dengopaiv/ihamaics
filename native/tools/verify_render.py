#!/usr/bin/env python3
"""Check the native renderer against the golden vectors, byte for byte.

Loads the built DLL through ctypes exactly as the driver will, renders
each golden case, and compares with the recorded PCM. Optionally also
fuzzes against the Python renderer on randomised phoneme sequences.

    python native/tools/verify_render.py [n_random]
"""
import ctypes
import glob
import json
import os
import random
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'nvda-addon', 'synthDrivers', 'sam'))

GOLDEN = os.path.join(ROOT, 'native', 'tests', 'golden')
BUILD = os.path.join(ROOT, 'native', 'build')


class Phoneme(ctypes.Structure):
    _fields_ = [("phoneme", ctypes.c_ubyte),
                ("length", ctypes.c_ubyte),
                ("stress", ctypes.c_ubyte)]


class Voice(ctypes.Structure):
    _fields_ = [("pitch", ctypes.c_ubyte), ("mouth", ctypes.c_ubyte),
                ("throat", ctypes.c_ubyte), ("speed", ctypes.c_ubyte),
                ("singmode", ctypes.c_int), ("inflection", ctypes.c_int)]


ERRORS = {-1: 'SAM_E_BADARG', -2: 'SAM_E_BADSPEED',
          -3: 'SAM_E_SHORTBUF', -4: 'SAM_E_NOMEM'}


def load():
    name = ("sam_render-x64.dll" if ctypes.sizeof(ctypes.c_void_p) == 8
            else "sam_render-x86.dll")
    path = os.path.join(BUILD, name)
    if not os.path.exists(path):
        print(f'{name} not built; run native\\build.cmd first')
        return None
    lib = ctypes.cdll.LoadLibrary(path)
    lib.sam_abi_version.restype = ctypes.c_int
    lib.sam_abi_version.argtypes = []
    lib.sam_render.restype = ctypes.c_int
    lib.sam_render.argtypes = [ctypes.POINTER(Phoneme), ctypes.c_int,
                               ctypes.POINTER(Voice),
                               ctypes.POINTER(ctypes.c_ubyte), ctypes.c_int]
    return lib


def native_render(lib, phoneme_list, p):
    arr = (Phoneme * len(phoneme_list))(
        *[Phoneme(e[0], e[1], e[2]) for e in phoneme_list])
    voice = Voice(p['pitch'], p['mouth'], p['throat'], p.get('speed', 72),
                  1 if p['singmode'] else 0, p['inflection'])

    need = lib.sam_render(arr, len(phoneme_list), ctypes.byref(voice), None, 0)
    if need < 0:
        return need, None
    buf = (ctypes.c_ubyte * max(need, 1))()
    n = lib.sam_render(arr, len(phoneme_list), ctypes.byref(voice), buf, len(buf))
    if n < 0:
        return n, None
    return n, bytes(bytearray(buf[:n]))


def main():
    lib = load()
    if lib is None:
        return 1
    if lib.sam_abi_version() != 1:
        print(f'unexpected ABI version {lib.sam_abi_version()}')
        return 1

    failures = 0
    specs = sorted(glob.glob(os.path.join(GOLDEN, '*.in.json')))
    for spec_path in specs:
        name = os.path.basename(spec_path)[:-len('.in.json')]
        spec = json.load(open(spec_path, encoding='utf-8'))
        expected = open(os.path.join(GOLDEN, name + '.pcm'), 'rb').read()

        n, actual = native_render(lib, spec['phoneme_list'], spec['params'])
        if actual is None:
            print(f'  FAIL  {name:20} returned {ERRORS.get(n, n)}')
            failures += 1
            continue
        if actual == expected:
            print(f'  ok    {name:20} {len(expected)} samples')
            continue

        failures += 1
        if len(actual) != len(expected):
            print(f'  FAIL  {name:20} length {len(actual)} != {len(expected)}')
        else:
            diffs = [i for i, (a, b) in enumerate(zip(actual, expected)) if a != b]
            print(f'  FAIL  {name:20} {len(diffs)}/{len(expected)} bytes differ, '
                  f'first at {diffs[0]} ({actual[diffs[0]]} != {expected[diffs[0]]})')

    n_random = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    if n_random:
        from renderer import render as py_render
        rnd = random.Random(31337)
        fuzz_fail = 0
        skipped = 0
        for _ in range(n_random):
            k = rnd.randint(1, 25)
            pl = [[rnd.randrange(0, 80), rnd.randrange(1, 40), rnd.randrange(0, 10)]
                  for _ in range(k)]
            p = dict(pitch=rnd.randrange(256), mouth=rnd.randrange(256),
                     throat=rnd.randrange(256), speed=rnd.choice([1, 20, 72, 150, 255]),
                     singmode=rnd.random() < 0.3, inflection=rnd.randrange(101))
            try:
                want = bytes(py_render(pl, p['pitch'], p['mouth'], p['throat'],
                                       p['speed'], p['singmode'], p['inflection']))
            except Exception:
                skipped += 1
                continue
            _, got = native_render(lib, pl, p)
            if got != want:
                fuzz_fail += 1
                if fuzz_fail == 1:
                    print(f'\n  fuzz FAIL: params={p} phonemes={pl[:6]}')
                    if got is not None:
                        print(f'    lengths C={len(got)} python={len(want)}')
        print(f'\n  fuzz: {n_random - skipped - fuzz_fail}/{n_random - skipped} '
              f'randomised cases byte-identical'
              + (f' ({skipped} skipped: Python raised)' if skipped else ''))
        failures += fuzz_fail

    print()
    if failures:
        print(f'{failures} FAILURE(S)')
        return 1
    print(f'native renderer byte-identical to Python on all {len(specs)} golden cases')
    return 0


if __name__ == '__main__':
    sys.exit(main())
