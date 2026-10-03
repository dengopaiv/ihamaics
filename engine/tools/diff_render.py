#!/usr/bin/env python3
"""The rewrite's renderer against native/'s, past what the Python checks.

    python engine/tools/diff_render.py [N] [--seed S] [--native DLL]

Stage R.4 of the C17 rewrite (docs/c17/04-r4-renderer.md section 4.4).
verify_render.py compares the rewrite with the Python, which is slow and
raises on some inputs. This loads both DLLs side by side through ctypes
(native/build/sam_render-x64.dll and the engine build's sam_render.dll;
different file names, so Windows loads them as two libraries) and
compares their PCM, or their error code, on N random cases (default
20,000) from seed S (default 4):

  - every phoneme byte 0..255, not just the 80 the tables have;
  - lengths and stresses 0..255;
  - every speed 0..255;
  - inflection from -1,000 to 1,000, outside sam_render.h's 0..100;
  - singmode 0, 1, or another nonzero int.

That covers the inputs the Python raises on (a write below -len in
create_transitions, the output buffer overflowing), where the rewrite
promises to do what native/ did. Lengths and phoneme counts are kept
small enough that one case stays under 10 MB of buffer. Inflection
stops at +-1,000 because native/ has undefined behaviour far past that
(docs/c17/03-r3-frames.md section 3.4), and there the two may differ.

The output buffer is filled with 0xA5 before each call, so a byte the
renderer leaves unwritten shows up as a difference rather than as the
zero ctypes would have put there. --native names native/'s DLL when it
is not in native/build, as in the mutation suite's copy of the tree.
"""
import ctypes
import os
import random
import sys

ENGINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.dirname(ENGINE)
sys.path.insert(0, os.path.join(ROOT, 'native', 'tools'))
from verify_render import Phoneme, Voice, ERRORS  # noqa: E402

ENGINE_BUILD = os.environ.get('SAM_ENGINE_BUILD',
                              os.path.join(ENGINE, 'build-msvc'))
NATIVE_DLL = os.path.join(ROOT, 'native', 'build', 'sam_render-x64.dll')
ENGINE_DLL = os.path.join(ENGINE_BUILD, 'sam_render.dll')

BUFFER_LIMIT = 10_000_000


def load(path):
    lib = ctypes.CDLL(path)
    lib.sam_render.restype = ctypes.c_int
    lib.sam_render.argtypes = [ctypes.POINTER(Phoneme), ctypes.c_int,
                               ctypes.POINTER(Voice),
                               ctypes.POINTER(ctypes.c_ubyte), ctypes.c_int]
    return lib


def render(lib, arr, count, voice):
    need = lib.sam_render(arr, count, ctypes.byref(voice), None, 0)
    if need <= 0:
        return need, b''
    buf = (ctypes.c_ubyte * need).from_buffer(bytearray([0xA5]) * need)
    n = lib.sam_render(arr, count, ctypes.byref(voice), buf, need)
    return n, bytes(buf[:max(n, 0)])


def case(rnd):
    while True:
        k = rnd.randint(1, 25)
        pl = [(rnd.randrange(256), rnd.randrange(256) if rnd.random() < 0.1
               else rnd.randrange(60), rnd.randrange(256) if rnd.random() < 0.2
               else rnd.randrange(10)) for _ in range(k)]
        speed = rnd.choice([0, 1, 2, 20, 72, 150, 255, rnd.randrange(256)])
        v = (rnd.randrange(256), rnd.randrange(256), rnd.randrange(256), speed,
             rnd.choice([0, 0, 1, 1, 7]), rnd.randint(-1000, 1000))
        if 176.4 * sum(e[1] for e in pl) * speed <= BUFFER_LIMIT:
            return pl, v


def main(argv):
    seed = 4
    if '--seed' in argv:
        i = argv.index('--seed')
        seed = int(argv[i + 1])
        del argv[i:i + 2]
    native_dll = NATIVE_DLL
    if '--native' in argv:
        i = argv.index('--native')
        native_dll = argv[i + 1]
        del argv[i:i + 2]
    n = int(argv[1]) if len(argv) > 1 else 20000
    for path in (native_dll, ENGINE_DLL):
        if not os.path.exists(path):
            print(path + ' not built')
            return 1
    native, engine = load(native_dll), load(ENGINE_DLL)
    rnd = random.Random(seed)
    diff = 0
    codes = {}
    for _ in range(n):
        pl, v = case(rnd)
        arr = (Phoneme * len(pl))(*[Phoneme(*e) for e in pl])
        voice = Voice(*v)
        a = render(native, arr, len(pl), voice)
        b = render(engine, arr, len(pl), voice)
        key = ERRORS.get(a[0], 'samples' if a[0] > 0 else 'empty')
        codes[key] = codes.get(key, 0) + 1
        if a != b:
            diff += 1
            if diff <= 3:
                print('DIFF voice=%s phonemes=%s native=%d engine=%d'
                      % (v, pl[:6], a[0], b[0]))
    print('%d cases from seed %d: %s' % (n, seed, ', '.join(
        '%s %d' % kv for kv in sorted(codes.items()))))
    print('%d differ between native/ and engine/' % diff)
    return 1 if diff else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
