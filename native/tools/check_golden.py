#!/usr/bin/env python3
"""Check the current renderer against the stored golden vectors.

Renders each case in native/tests/golden/ from its recorded inputs and
compares byte for byte with the recorded output. Any difference is a
regression: these fixtures define the voice.

    python native/tools/check_golden.py

Exit status is 0 when every case matches, 1 otherwise.
"""
import glob
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'nvda-addon', 'synthDrivers', 'sam'))

from renderer import render  # noqa: E402

GOLDEN = os.path.join(ROOT, 'native', 'tests', 'golden')


def main():
    specs = sorted(glob.glob(os.path.join(GOLDEN, '*.in.json')))
    if not specs:
        print('no golden vectors found; run gen_golden.py first')
        return 1

    failures = 0
    for spec_path in specs:
        name = os.path.basename(spec_path)[:-len('.in.json')]
        with open(spec_path, encoding='utf-8') as f:
            spec = json.load(f)
        with open(os.path.join(GOLDEN, name + '.pcm'), 'rb') as f:
            expected = f.read()

        p = spec['params']
        actual = bytes(render(spec['phoneme_list'], p['pitch'], p['mouth'],
                              p['throat'], p['speed'], p['singmode'],
                              p['inflection']))

        if actual == expected:
            print(f'  ok    {name:20} {len(expected)} samples')
            continue

        failures += 1
        if len(actual) != len(expected):
            print(f'  FAIL  {name:20} length {len(actual)} != {len(expected)}')
            continue
        diffs = [i for i, (a, b) in enumerate(zip(actual, expected)) if a != b]
        print(f'  FAIL  {name:20} {len(diffs)} of {len(expected)} bytes differ, '
              f'first at {diffs[0]} ({actual[diffs[0]]} != {expected[diffs[0]]})')

    print()
    if failures:
        print(f'{failures} of {len(specs)} cases REGRESSED')
        return 1
    print(f'all {len(specs)} cases byte-identical')
    return 0


if __name__ == '__main__':
    sys.exit(main())
