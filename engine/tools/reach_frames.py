#!/usr/bin/env python3
"""Which of the frame stage's Python idioms does any input reach?

    python engine/tools/reach_frames.py            the corpus counts
    python engine/tools/reach_frames.py --grow N   hill-climb |pitch|

Stage R.3 of the C17 rewrite (docs/c17/03-r3-frames.md section 3.3).
Plan section 1.2 sorts every idiom into "the voice depends on it" or
"no input reaches it", and each sorting cites a measurement. This is
the measurement for create_transitions() and prepare_frames().

The default run takes verify_prepare.py's own corpus (the golden cases,
then 3,000 random ones from its fixed seed) and runs an instrumented
copy of the two functions over it. The copy computes exactly what
renderer.py computes; it only counts. For each event it prints how
often it happened and in how many cases, and the range of every row.
Cases on which the Python raises IndexError are counted and skipped, as
verify_prepare.py skips them.

--grow N searches for the largest |pitch| create_transitions() can
produce from N phonemes: six restarts of 4,000 steps of hill climbing
from seed 7, at inflection 100, mouth and throat 128. It is a search,
not a proof; the chapter says what it shows.
"""
import collections
import os
import random
import sys

ENGINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.dirname(ENGINE)
sys.path.insert(0, os.path.join(ROOT, 'native', 'tools'))
sys.path.insert(0, os.path.join(ROOT, 'nvda-addon', 'synthDrivers', 'sam'))

import renderer as R  # noqa: E402
from renderer_tables import (AMPLITUDE_RESCALE, BLEND_RANK,  # noqa: E402
                             IN_BLEND_LENGTH, OUT_BLEND_LENGTH)


class Tally:
    """Counts per case, merged only when the case completes, so a case
    the Python raises on leaves nothing behind."""

    def __init__(self):
        self.events = collections.Counter()
        self.cases = collections.Counter()
        self.ranges = {}
        self.drop_case()

    def hit(self, name):
        self.case_events[name] += 1

    def see(self, name, values):
        for v in values:
            lo, hi = self.case_ranges.get(name, (v, v))
            self.case_ranges[name] = (min(lo, v), max(hi, v))

    def drop_case(self):
        self.case_events = collections.Counter()
        self.case_ranges = {}

    def end_case(self):
        self.events.update(self.case_events)
        for name in self.case_events:
            self.cases[name] += 1
        for name, (lo, hi) in self.case_ranges.items():
            old = self.ranges.get(name, (lo, hi))
            self.ranges[name] = (min(old[0], lo), max(old[1], hi))
        self.drop_case()


def create_transitions(pitches, frequency, amplitude, tuples, tally):
    """renderer.create_transitions(), counting what it does."""
    tables = [pitches, frequency[0], frequency[1], frequency[2],
              amplitude[0], amplitude[1], amplitude[2]]

    def read(table, pos):
        if pos < 0 or pos >= len(tables[table]):
            return 0
        return tables[table][pos]

    def interpolate(width, table, frame, change):
        if width == 0:
            tally.hit('width 0')
            return
        sign = change < 0
        remainder = abs(change) % width
        div = int(change / width)
        if div != (-(-change // width) if sign else change // width):
            tally.hit('int(change / width) differs from integer division')
        error = 0
        pos = width
        while pos > 1:
            pos -= 1
            val = read(table, frame) + div
            error += remainder
            if error >= width:
                error -= width
                if sign:
                    val -= 1
                elif val:
                    val += 1
                else:
                    tally.hit('elif val: leaves a 0 alone')
            frame += 1
            if frame < len(tables[table]):
                if frame < -len(tables[table]):
                    tally.hit('write below -len (Python raises)')
                elif frame < 0:
                    tally.hit('negative index write (Q2)')
                tables[table][frame] = val
            else:
                tally.hit('write past the end, skipped')

    boundary = 0
    for pos in range(len(tuples) - 1):
        phoneme = tuples[pos][0]
        next_phoneme = tuples[pos + 1][0]
        next_rank = BLEND_RANK[next_phoneme] if next_phoneme < len(BLEND_RANK) else 0
        rank = BLEND_RANK[phoneme] if phoneme < len(BLEND_RANK) else 0
        if rank == next_rank:
            out_b = OUT_BLEND_LENGTH[phoneme] if phoneme < len(OUT_BLEND_LENGTH) else 0
            in_b = OUT_BLEND_LENGTH[next_phoneme] if next_phoneme < len(OUT_BLEND_LENGTH) else 0
        elif rank < next_rank:
            out_b = IN_BLEND_LENGTH[next_phoneme] if next_phoneme < len(IN_BLEND_LENGTH) else 0
            in_b = OUT_BLEND_LENGTH[next_phoneme] if next_phoneme < len(OUT_BLEND_LENGTH) else 0
        else:
            out_b = OUT_BLEND_LENGTH[phoneme] if phoneme < len(OUT_BLEND_LENGTH) else 0
            in_b = IN_BLEND_LENGTH[phoneme] if phoneme < len(IN_BLEND_LENGTH) else 0
        boundary += tuples[pos][1]
        trans_end = boundary + in_b
        trans_start = boundary - out_b
        trans_length = out_b + in_b
        tally.see('trans_length', [trans_length])
        if trans_start < 0:
            tally.hit('trans_start negative')
        if ((trans_length - 2) & 128) == 0:
            cur_width = tuples[pos][1] >> 1
            next_width = tuples[pos + 1][1] >> 1
            pitch_end = boundary + next_width
            pitch_start = boundary - cur_width
            if pitch_end < len(pitches) and pitch_start >= 0:
                interpolate(cur_width + next_width, 0, trans_start,
                            pitches[pitch_end] - pitches[pitch_start])
            for table in range(1, 7):
                interpolate(trans_length, table, trans_start,
                            read(table, trans_end) - read(table, trans_start))
        else:
            tally.hit('no transition (bit 7 of trans_length - 2)')
    return boundary + tuples[-1][1] if tuples else boundary


def prepare_frames(pl, p, tally):
    """renderer.prepare_frames(), counting what it does."""
    fd = R.set_mouth_throat(p['mouth'], p['throat'])
    pitches, frequency, amplitude, _ = R.create_frames(
        p['pitch'], pl, fd, p['inflection'])
    rows = len(pitches)
    t = create_transitions(pitches, frequency, amplitude, pl, tally)
    if t != rows:
        tally.hit('frame count differs from row length')
    tally.see('pitch after transitions', pitches)
    for r in range(3):
        tally.see('F%d' % (r + 1), frequency[r])
        tally.see('A%d before rescale' % (r + 1), amplitude[r])
    if p['singmode']:
        tally.see('pitch out, sing mode', pitches)
    else:
        for f in frequency[0]:
            if f < 0:
                tally.hit('negative F1 halved (>> 1 floors)')
    for r in range(3):
        for v in amplitude[r]:
            if v < 0:
                tally.hit('negative amplitude indexes from the end')
            elif v >= len(AMPLITUDE_RESCALE):
                tally.hit('amplitude 16 or more, kept')


def corpus():
    sys.argv[1:] = []
    import verify_prepare  # noqa: E402  (its corpus, its seed)
    cases = verify_prepare.build_cases(3000)
    golden = len(cases) - 3000
    return [('golden', cases[:golden]), ('random', cases[golden:])]


def measure():
    for label, cases in corpus():
        tally = Tally()
        raised = 0
        for pl, p in cases:
            try:
                prepare_frames([list(e) for e in pl], p, tally)
            except IndexError:
                raised += 1
                tally.drop_case()
                continue
            tally.end_case()
        print('== %s: %d cases, %d raised IndexError (skipped)'
              % (label, len(cases), raised))
        for name in sorted(tally.events):
            print('  %-52s %8d events in %5d cases'
                  % (name, tally.events[name], tally.cases[name]))
        for name in sorted(tally.ranges):
            print('  range %-46s %s' % (name, tally.ranges[name]))


def grow(n, seed=7, restarts=6, steps=4000):
    fd = R.set_mouth_throat(128, 128)
    rnd = random.Random(seed)

    def score(pl, pitch):
        try:
            p, f, a, _ = R.create_frames(pitch, pl, fd, 100)
            R.create_transitions(p, f, a, pl)
        except IndexError:
            return -1
        return max(abs(v) for v in p) if p else 0

    best_all = 0
    for _ in range(restarts):
        pl = [[rnd.randrange(80), rnd.randrange(256), rnd.randrange(10)]
              for _ in range(n)]
        pitch = rnd.randrange(256)
        best = score(pl, pitch)
        for _ in range(steps):
            q = [e[:] for e in pl]
            for _ in range(rnd.randint(1, 3)):
                i, j = rnd.randrange(n), rnd.randrange(3)
                q[i][j] = rnd.randrange((80, 256, 10)[j])
            s = score(q, pitch)
            if s >= best:
                best, pl = s, q
        best_all = max(best_all, best)
    print('N %d: largest |pitch| found %d' % (n, best_all))


if __name__ == '__main__':
    if len(sys.argv) > 2 and sys.argv[1] == '--grow':
        grow(int(sys.argv[2]))
    else:
        measure()
