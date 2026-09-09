#!/usr/bin/env python3
"""Differential test: C sam_parse_phonemes vs Python parser.parse.

The renderer could be checked with golden vectors because the voice is a
fixed target. The parser is a function over every pronunciation in the
language, so it is checked against the whole domain instead: every
phoneme string the CMU dictionary can produce, every rule-based
pronunciation of a large coined-word corpus, the punctuation cases that
reach parser.py's negative-index write, and a pile of randomised phoneme
strings for the paths a real word never takes.

    python native/tools/verify_parser.py [extra-random-cases]
"""
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _build import ROOT, build_and_run  # noqa: E402

sys.path.insert(0, os.path.join(ROOT, 'nvda-addon', 'synthDrivers', 'sam'))

import cmudict                          # noqa: E402
import parser as sam_parser             # noqa: E402
import parser_tables as pt              # noqa: E402
from reciter import _rule_based_phonemes  # noqa: E402

SOURCES = ['sam_parser.c', 'sam_parser_tables.c', 'sam_reciter_tables.c']


def coined_words(count, rng):
    """Words the dictionary will not have, to force the rule engine."""
    vowels = 'AEIOUY'
    cons = 'BCDFGHJKLMNPQRSTVWXZ'
    out = []
    for _ in range(count):
        w = []
        for _ in range(rng.randint(1, 4)):
            w.append(rng.choice(cons))
            w.append(rng.choice(vowels))
            if rng.random() < 0.4:
                w.append(rng.choice(cons))
        out.append(''.join(w))
    return out


def random_phoneme_strings(count, rng):
    """Arbitrary phoneme strings, including ones a reciter never emits."""
    names = [n for n in pt.PHONEME_NAME_TABLE]
    pieces = names + list('*12345678') + [' ', '.', ',', '?', '-']
    out = []
    for _ in range(count):
        out.append(''.join(rng.choice(pieces)
                           for _ in range(rng.randint(1, 40))))
    return out


def build_corpus(extra_random):
    rng = random.Random(20260909)
    cases = []

    # Every dictionary pronunciation.
    table = cmudict.load_cmudict()
    for word in table:
        p = cmudict.lookup(word)
        if p:
            cases.append(p)
    dict_cases = len(cases)

    # Rule-engine output for coined words and for real ones.
    rule_words = coined_words(4000, rng) + list(table)[:4000]
    for w in rule_words:
        p = _rule_based_phonemes(w)
        if p:
            cases.append(p.strip())
    rule_cases = len(cases) - dict_cases

    # The edges: punctuation first, punctuation only, empty.
    edge = ['', '.', ',', '?', '-', '..', ' .', '. ', ' ', '.AH', 'AH.',
            'AH5', '5', '*', '**', 'AH5 AH5', 'DHAX KAET IHZ AH5GLIY.',
            'AH5.AH5', 'UL', 'UM', 'UN', 'ULUMUN', 'K', 'G', 'KK', 'GG',
            'SP', 'ST', 'SK', 'CH', 'J', 'UW', 'TUW', 'DUW', 'TR', 'DR',
            'QQ', 'AH5 . AH5', 'AA5RAA5', 'NB', 'NG', 'PL', 'PR', 'BL']
    cases.extend(edge)

    rand = random_phoneme_strings(2000 + extra_random, rng)
    cases.extend(rand)

    return cases, dict_cases, rule_cases, len(edge), len(rand)


def py_parse(s):
    """parse() as a comparable string, matching dump_parse.c's format."""
    try:
        r = sam_parser.parse(s)
    except Exception as e:                      # noqa: BLE001
        return 'EXC:%s' % type(e).__name__
    if r is False:
        return 'FAIL'
    return ' '.join('%d,%d,%d' % (p, l, st) for p, l, st in r)


def main():
    extra = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    cases, n_dict, n_rule, n_edge, n_rand = build_corpus(extra)

    # A newline is the record separator, so nothing may contain one.
    bad = [c for c in cases if '\n' in c or '\r' in c]
    if bad:
        print('corpus contains newlines; cannot use line framing')
        return 1

    print('corpus: %d cases (%d dictionary, %d rule-based, %d edge, '
          '%d random)' % (len(cases), n_dict, n_rule, n_edge, n_rand))

    stdin = ('\n'.join(cases) + '\n').encode('ascii', 'replace')
    out = build_and_run('dump_parse.c', SOURCES, stdin_data=stdin)
    if out is None:
        return 1

    got = out.decode('ascii').replace('\r\n', '\n').split('\n')
    if got and got[-1] == '':
        got.pop()
    if len(got) != len(cases):
        print('expected %d result lines from C, got %d'
              % (len(cases), len(got)))
        return 1

    mismatches = []
    widest = 0
    for case, c_line in zip(cases, got):
        want = py_parse(case)
        if want != c_line:
            mismatches.append((case, want, c_line))
        elif want not in ('FAIL',) and not want.startswith('EXC:'):
            for triple in want.split():
                widest = max(widest, max(int(v) for v in triple.split(',')))

    if mismatches:
        print('%d of %d cases MISMATCHED' % (len(mismatches), len(cases)))
        for case, want, c_line in mismatches[:10]:
            print('  input  : %r' % case)
            print('    python: %s' % want)
            print('    C     : %s' % c_line)
        return 1

    print('sam_parse_phonemes matches Python on all %d cases '
          '(largest value seen: %d)' % (len(cases), widest))

    # The comparison above is on the unnarrowed integers, which is the
    # strong form. The triples then become bytes on the way to the
    # renderer, and the two paths narrow the same way: C casts to
    # uint8_t, and ctypes' c_ubyte truncates mod 256 rather than raising
    # (c_ubyte(274).value == 18). So agreement here survives the cast.
    #
    # It only comes up at all for synthetic input: no dictionary
    # pronunciation and no rule-engine output in this corpus exceeds a
    # byte. One randomised phoneme string does, which is why the check
    # reports the width instead of assuming it.
    if widest > 255:
        print('  note: %d > 255, from a randomised phoneme string; both '
              'the C cast and ctypes narrow it to %d'
              % (widest, widest & 0xFF))
    return 0


if __name__ == '__main__':
    sys.exit(main())
