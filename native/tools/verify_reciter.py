#!/usr/bin/env python3
"""Differential test: C sam_reciter_rules vs Python _rule_based_phonemes.

The rule engine is a function over every string a user might type, so it
is checked against a domain rather than a sample: every word in the CMU
dictionary, tens of thousands of coined words that force the rules the
dictionary would otherwise hide, every punctuation and digit case that
reaches rules2, and the awkward shapes - empty input, a lone quote, runs
of symbols - that decide whether the driving loop terminates.

Scope: ASCII. Non-ASCII bytes have a character flag of zero in both
implementations and become a space either way, with the exception noted
in sam_reciter.c; the GUI narrows to bytes before calling in.

    python native/tools/verify_reciter.py [extra-coined-words]
"""
import os
import random
import string
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _build import ROOT, build_and_run  # noqa: E402

sys.path.insert(0, os.path.join(ROOT, 'nvda-addon', 'synthDrivers', 'sam'))

import cmudict                            # noqa: E402
from reciter import _rule_based_phonemes  # noqa: E402

SOURCES = ['sam_reciter.c', 'sam_reciter_tables.c']
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
        if rng.random() < 0.15:
            w.append("'S")
        out.append(''.join(w))
    return out


def build_corpus(extra):
    rng = random.Random(20260909)
    table = cmudict.load_cmudict()

    cases = list(table)                       # every dictionary word
    n_dict = len(cases)

    cases += coined_words(20000 + extra, rng)
    n_coined = len(cases) - n_dict

    # Every character the tables know about, alone and in context.
    printable = [c for c in string.printable if c not in '\r\n\x0b\x0c']
    chars = []
    for c in printable:
        chars += [c, c * 2, 'A' + c, c + 'A', 'A' + c + 'A', ' ' + c + ' ']
    cases += chars
    n_chars = len(chars)

    edge = [
        '', ' ', '  ', "'", "''", "'S", 'A', 'I', '.', '..', '. ', ' .',
        '1', '10', '100', '1ST', '2ND', '3RD', '5TH', '8TH', '10TH', '64',
        '.5', '1.5', '3.14', '-1', '$', '%', '&', '#', '@', '^', '*', '+',
        '<', '=', '>', '?', '!', '"', '/', ':', ';', ',', '-',
        'HELLO, MY NAME IS SAM.', 'THE QUICK BROWN FOX JUMPS OVER',
        'hello world', 'MiXeD CaSe', 'A' * 200, 'Z' * 200, 'X' * 500,
        'THING', 'THINGS', 'MAKING', 'LOVELY', 'HOPEFUL', 'BAKED',
        'BAKER', 'BAKES', 'CHURCH', 'SHOP', 'SCHOOL', 'GHOST',
    ]
    cases += edge

    return cases, n_dict, n_coined, n_chars, len(edge)


def py_reciter(s):
    try:
        r = _rule_based_phonemes(s)
    except Exception as e:                     # noqa: BLE001
        return 'EXC:%s' % type(e).__name__
    return FAIL if r is False else r


def main():
    extra = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    cases, n_dict, n_coined, n_chars, n_edge = build_corpus(extra)

    cases = [c for c in cases if '\n' not in c and '\r' not in c]
    print('corpus: %d cases (%d dictionary words, %d coined, %d character '
          'contexts, %d edge)' % (len(cases), n_dict, n_coined, n_chars,
                                  n_edge))

    stdin = ('\n'.join(cases) + '\n').encode('ascii', 'replace')
    out = build_and_run('dump_reciter.c', SOURCES, stdin_data=stdin)
    if out is None:
        return 1

    got = out.decode('ascii', 'replace').replace('\r\n', '\n').split('\n')
    if got and got[-1] == '':
        got.pop()
    if len(got) != len(cases):
        print('expected %d result lines from C, got %d'
              % (len(cases), len(got)))
        return 1

    mismatches = []
    for case, c_line in zip(cases, got):
        want = py_reciter(case)
        if want != c_line:
            mismatches.append((case, want, c_line))

    if mismatches:
        print('%d of %d cases MISMATCHED' % (len(mismatches), len(cases)))
        for case, want, c_line in mismatches[:15]:
            print('  input  : %r' % case)
            print('    python: %r' % want)
            print('    C     : %r' % c_line)
        return 1

    print('sam_reciter_rules matches Python on all %d cases' % len(cases))
    return 0


if __name__ == '__main__':
    sys.exit(main())
