#!/usr/bin/env python3
"""Differential test: the C front end vs the Python one.

Three comparisons, each over a domain rather than a sample:

  text_to_phonemes, with the dictionary   every word in the dictionary,
                                          plus sentences, punctuation and
                                          coined words
  text_to_phonemes, dictionary absent     the same corpus down the
                                          rules-only path Python takes
                                          when cmudict will not import
  expand_numbers                          every integer shape up to and
                                          past the range a C integer
                                          could hold, plus decimals and
                                          signs

    python native/tools/verify_text.py [extra-random-cases]

Needs native/data/sam.dict; run native/tools/gen_dict.py first.
"""
import os
import random
import string
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _build import ROOT, build_and_run  # noqa: E402

sys.path.insert(0, os.path.join(ROOT, 'nvda-addon', 'synthDrivers', 'sam'))

import cmudict                                     # noqa: E402
import reciter                                     # noqa: E402
from reciter import text_to_phonemes, expand_numbers  # noqa: E402

DICT = os.path.join(ROOT, 'native', 'data', 'sam.dict')

TEXT_SOURCES = ['sam_text.c', 'sam_reciter.c', 'sam_parser.c',
                'sam_parser_tables.c', 'sam_reciter_tables.c',
                'sam_cmudict_tables.c', 'sam_render.c', 'sam_frames.c',
                'sam_tables.c']

FAIL = '\x01FAIL'


def coined_words(count, rng):
    vowels = 'AEIOUY'
    cons = 'BCDFGHJKLMNPQRSTVWXZ'
    out = []
    for _ in range(count):
        w = []
        for _ in range(rng.randint(1, 5)):
            w.append(rng.choice(cons))
            w.append(rng.choice(vowels))
            if rng.random() < 0.45:
                w.append(rng.choice(cons))
        out.append(''.join(w))
    return out


def sentences(words, count, rng):
    punct = ['.', ',', '?', '!', '', '', '']
    out = []
    for _ in range(count):
        n = rng.randint(1, 12)
        s = ' '.join(rng.choice(words) for _ in range(n))
        out.append(s + rng.choice(punct))
    return out


def text_corpus(extra):
    rng = random.Random(20260909)
    table = cmudict.load_cmudict()
    words = list(table)

    cases = list(words)
    n_dict = len(cases)

    cases += coined_words(6000 + extra, rng)
    cases += sentences(words, 6000, rng)
    cases += [w.lower() for w in words[:3000]]
    cases += [w.title() for w in words[:3000]]

    printable = [c for c in string.printable if c not in '\r\n\x0b\x0c']
    cases += [c for c in printable]
    cases += ['A' + c + 'B' for c in printable]

    cases += [
        '', ' ', '  ', 'Hello, my name is Sam.', "don't", "DON'T", "Don't",
        "'", "''", "it's", "o'clock", 'e-mail', 'well-known',
        'The quick brown fox jumps over the lazy dog.',
        'AALBORG', 'Aalborg', 'aalen', 'AALSMEER',   # the commented entries
        'a b c', 'A.B.C.', 'U.S.A.', 'Mr. Smith', '3 apples', '1,000',
        'x' * 300, 'Hello' * 60, '?!.,;:', '   spaced   out   ',
    ]
    return cases, n_dict


def number_corpus(extra):
    rng = random.Random(4242)
    cases = []

    for n in range(0, 1101):
        cases.append(str(n))
    for e in range(0, 25):
        cases.append(str(10 ** e))
        cases.append(str(10 ** e - 1))
        cases.append(str(10 ** e + 1))

    # Past every C integer width, which is the reason the C port works on
    # digits instead of on an int.
    cases += ['9' * 19, '9' * 20, '9' * 40, '1' + '0' * 30,
              '18446744073709551615', '18446744073709551616',
              '123456789012345678901234567890']

    for _ in range(3000 + extra):
        d = rng.randint(1, 30)
        cases.append(''.join(rng.choice('0123456789') for _ in range(d)))

    cases += ['-1', '-0', '-000', '0', '00', '007', '-42', '3.14', '0.5',
              '.5', '-.5', '1.', '1.0', '-3.14159', '1.2.3', '00.00',
              '1000000.000001', '-0.0',
              'I have 3 apples and 42 oranges.',
              'Call 555-1234 now.', 'Version 2.0.1', '$1,000,000',
              'The year 2026.', 'no digits here', '', ' ', '-', '--',
              '1st', '2nd', '10th', '1e5', '0x10']
    return cases


def compare(label, mode, cases, py_fn, args=()):
    cases = [c for c in cases if '\n' not in c and '\r' not in c]
    print('%s: %d cases' % (label, len(cases)))

    stdin = ('\n'.join(cases) + '\n').encode('ascii', 'replace')
    out = build_and_run('dump_text.c', TEXT_SOURCES, stdin_data=stdin,
                        args=(mode,) + tuple(args))
    if out is None:
        return 1

    got = out.decode('ascii', 'replace').replace('\r\n', '\n').split('\n')
    if got and got[-1] == '':
        got.pop()
    if len(got) != len(cases):
        print('  expected %d result lines from C, got %d'
              % (len(cases), len(got)))
        return 1

    mismatches = []
    for case, c_line in zip(cases, got):
        try:
            want = py_fn(case)
        except Exception as e:                     # noqa: BLE001
            want = 'EXC:%s' % type(e).__name__
        if want is False:
            want = FAIL
        if want != c_line:
            mismatches.append((case, want, c_line))

    if mismatches:
        print('  %d of %d MISMATCHED' % (len(mismatches), len(cases)))
        for case, want, c_line in mismatches[:15]:
            print('    input : %r' % case)
            print('      py  : %r' % want)
            print('      C   : %r' % c_line)
        return 1

    print('  matches Python on all %d cases' % len(cases))
    return 0


def rules_only(text):
    """text_to_phonemes with cmudict unavailable, as Python does it."""
    saved = reciter.cmudict
    reciter.cmudict = None
    try:
        return reciter.text_to_phonemes(text)
    finally:
        reciter.cmudict = saved


def main():
    extra = int(sys.argv[1]) if len(sys.argv) > 1 else 0

    if not os.path.exists(DICT):
        print('native/data/sam.dict is missing.')
        print('Run:  python native/tools/gen_dict.py')
        return 1

    cases, n_dict = text_corpus(extra)
    print('text corpus includes all %d dictionary words' % n_dict)

    rc = compare('text_to_phonemes (with dictionary)', 'phonemes', cases,
                 text_to_phonemes, args=(DICT,))
    rc |= compare('text_to_phonemes (rules only)', 'rules', cases, rules_only)
    rc |= compare('expand_numbers', 'numbers', number_corpus(extra),
                  expand_numbers)
    return rc


if __name__ == '__main__':
    sys.exit(main())
