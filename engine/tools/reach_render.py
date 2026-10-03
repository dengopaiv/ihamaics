#!/usr/bin/env python3
"""Which of the renderer's Python idioms does any input reach?

    python engine/tools/reach_render.py [N]

Stage R.4 of the C17 rewrite (docs/c17/04-r4-renderer.md section 4.3).
Plan section 1.2 sorts every idiom into "the voice depends on it" or
"no input reaches it", and each sorting cites a measurement. This is
the measurement for process_frames(), render_sample() and OutputBuffer.

The corpus is verify_render.py's own: the 16 golden cases, then its
first N randomised cases (default 485) from its fixed seed. Frames come
from renderer.prepare_frames(), unchanged; process_frames() and
render_sample() are run as an instrumented copy that computes exactly
what renderer.py computes and only counts. For each event it prints how
often it happened and in how many cases, and the range of each value
of interest. A case on which the Python raises is counted by exception
and skipped, as verify_render.py skips it; it leaves no counts behind.
The final check compares the copy's PCM with renderer.render() on every
case, so the copy cannot drift from what it claims to measure.
"""
import collections
import glob
import json
import os
import sys

ENGINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.dirname(ENGINE)
sys.path.insert(0, os.path.join(ROOT, 'native', 'tools'))
sys.path.insert(0, os.path.join(ROOT, 'nvda-addon', 'synthDrivers', 'sam'))

import renderer as R  # noqa: E402
from renderer_tables import (SAMPLE_TABLE, SAMPLED_CONSONANT_VALUES0,  # noqa: E402
                             SINUS_TABLE)

R.native = None  # the Python path, never the DLL (section 4.1)


class Tally:
    """Counts per case, merged only when the case completes."""

    def __init__(self):
        self.events = collections.Counter()
        self.cases = collections.Counter()
        self.ranges = {}
        self.drop_case()

    def hit(self, name):
        self.case_events[name] += 1

    def see(self, name, v):
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


class Output(R.OutputBuffer):
    def __init__(self, size, tally):
        super().__init__(size)
        self.tally = tally

    def write_array(self, index, array):
        pos = (self.bufferpos + self.TIMETABLE[self.old_timetable_index][index]) // 50
        if pos > len(self.buffer):
            self.tally.hit('buffer overflow (Python raises)')
        elif pos + 4 >= len(self.buffer):
            self.tally.hit('write in advance cut at the buffer end')
        super().write_array(index, array)


def render_sample(output, last_sample_offset, consonant_flag, pitch, tally):
    kind = (consonant_flag & 7) - 1
    tally.see('kind', kind)
    if kind < 0:
        tally.hit('kind -1: values0[-1] (negative index)')
    sample_page = (kind * 256) & 0xFFFF
    off = consonant_flag & 248

    def inner(index1, value1, index0, value0):
        nonlocal off
        sample_idx = sample_page + off
        if sample_idx >= len(SAMPLE_TABLE):
            tally.hit('sample index past the table')
            return
        sample = SAMPLE_TABLE[sample_idx]
        for _ in range(8):
            if sample & 128:
                output.write(index1, value1)
            else:
                output.write(index0, value0)
            sample = (sample << 1) & 0xFF

    if off == 0:
        tally.hit('voiced sample')
        if pitch < 0:
            tally.hit('negative pitch into pitch >> 4 (floors)')
        elif pitch > 255:
            tally.hit('pitch over 255 into pitch >> 4')
        phase1 = ((pitch >> 4) ^ 255) & 0xFF
        off = last_sample_offset & 0xFF
        while True:
            inner(3, 26, 4, 6)
            off = (off + 1) & 0xFF
            phase1 = (phase1 + 1) & 0xFF
            if phase1 == 0:
                break
        return off

    tally.hit('unvoiced sample')
    off = (off ^ 255) & 0xFF
    value0 = (SAMPLED_CONSONANT_VALUES0[kind] & 0xFF
              if kind < len(SAMPLED_CONSONANT_VALUES0) else 0)
    while True:
        inner(2, 5, 1, value0)
        off = (off + 1) & 0xFF
        if off == 0:
            break
    return last_sample_offset


def process_frames(output, frame_count, speed, frequency, pitches, amplitude,
                   flags_row, tally):
    speedcounter = speed
    phase1 = phase2 = phase3 = 0
    last_sample_offset = 0
    pos = 0
    if not pitches:
        tally.hit('no frames')
        return
    n = len(flags_row)
    for row in (pitches, *frequency, *amplitude):
        if len(row) != n:
            tally.hit('rows of different lengths')
    if frame_count != n:
        tally.hit('frame count differs from row length')

    def pitch_at_wrapped():
        if pos > 255:
            tally.hit('pitch read at pos & 0xFF (pos over 255)')
        if (pos & 0xFF) >= n:
            tally.hit('pitch read at pos & 0xFF past the row: 0')
        return pitches[pos & 0xFF] if (pos & 0xFF) < n else 0

    glottal_pulse = pitches[0]
    if glottal_pulse <= 0:
        tally.hit('first glottal pulse <= 0: never resets')
    mem38 = int(glottal_pulse * 0.75)
    stuck = glottal_pulse <= 0

    while frame_count > 0:
        if pos >= n:
            tally.hit('pos past the rows: loop ends')
            break
        flags = flags_row[pos]
        if flags & 248:
            last_sample_offset = render_sample(output, last_sample_offset, flags,
                                               pitch_at_wrapped(), tally)
            pos += 2
            frame_count -= 2
            if frame_count < 0:
                tally.hit('frame count -1 after an unvoiced sample')
            speedcounter = speed
            continue

        a = [amplitude[r][pos] if pos < n else 0 for r in range(3)]
        for v in a:
            if v > 15:
                tally.hit('amplitude over 15, & 0x0F')
        a = [v & 0x0F for v in a]
        f = [frequency[r][pos] if pos < n else 0 for r in range(3)]
        d = [int(v * 256 / 4) for v in f]
        p = [phase1 * 256, phase2 * 256, phase3 * 256]
        tally.see('phase', max(phase1, phase2, phase3))
        ary = []
        for _ in range(5):
            sp1 = SINUS_TABLE[(p[0] >> 8) & 0xFF]
            sp2 = SINUS_TABLE[(p[1] >> 8) & 0xFF]
            rp3 = -0x70 if ((p[2] >> 8) & 0xFF) < 129 else 0x70
            s = sp1 * a[0] + sp2 * a[1] + rp3 * a[2]
            tally.see('mux sum', s)
            mux = int(s / 32) + 128
            if s < 0 and s % 32:
                tally.hit('negative mux sum, truncated not floored')
            if mux < 0:
                tally.hit('mux clamped at 0')
            if mux > 255:
                tally.hit('mux clamped at 255')
            ary.append(0 if mux < 0 else (255 if mux > 255 else mux))
            p = [p[i] + d[i] for i in range(3)]
        output.write_array(0, ary)

        speedcounter -= 1
        if speedcounter == 0:
            pos += 1
            frame_count -= 1
            if frame_count == 0:
                return
            speedcounter = speed

        glottal_pulse -= 1
        if glottal_pulse != 0:
            mem38 -= 1
            if mem38 != 0 or flags == 0:
                if stuck:
                    tally.hit('formant step with the pulse stuck')
                f = [frequency[r][pos] if pos < n else 0 for r in range(3)]
                if pos >= n:
                    tally.hit('phase step past the rows: + 0')
                phase1 += f[0]
                phase2 += f[1]
                phase3 += f[2]
                continue
            tally.hit('voiced sample at mem38 0')
            last_sample_offset = render_sample(output, last_sample_offset, flags,
                                               pitch_at_wrapped(), tally)
        if pos >= n:
            tally.hit('pulse reset past the rows: 0')
        glottal_pulse = pitches[pos] if pos < n else 0
        if glottal_pulse <= 0:
            tally.hit('pulse reset to <= 0: never resets again')
            stuck = True
        else:
            stuck = False
        tally.see('glottal pulse at reset', glottal_pulse)
        mem38 = int(glottal_pulse * 0.75)
        phase1 = phase2 = phase3 = 0


def render(pl, p, tally):
    t, frequency, pitches, amplitude, flags = R.prepare_frames(
        pl, p['pitch'], p['mouth'], p['throat'], p['singmode'], p['inflection'])
    for v in pitches:
        tally.see('pitch row', v)
    total = sum(e[1] for e in pl)
    size = int(176.4 * total * p['speed'])
    if size == 0:
        tally.hit('empty buffer')
        return b''
    out = Output(size, tally)
    process_frames(out, t, p['speed'], frequency, pitches, amplitude, flags, tally)
    tally.see('samples / buffer size %', 100 * (out.bufferpos // 50) // size)
    return out.get()


def corpus(n):
    sys.argv[1:] = []
    import verify_render  # noqa: E402  (its corpus, its seed)
    golden = []
    for spec in sorted(glob.glob(os.path.join(ROOT, 'native', 'tests', 'golden',
                                              '*.in.json'))):
        s = json.load(open(spec, encoding='utf-8'))
        golden.append((s['phoneme_list'], s['params']))
    return [('golden', golden), ('random', verify_render.fuzz_cases(n))]


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 485
    drift = 0
    for label, cases in corpus(n):
        tally = Tally()
        raised = collections.Counter()
        for pl, p in cases:
            p = dict(p, speed=p.get('speed', 72))
            try:
                got = render([list(e) for e in pl], p, tally)
            except Exception as e:  # noqa: BLE001  (counted, then skipped)
                raised[type(e).__name__ + ': ' + str(e)[:40]] += 1
                tally.drop_case()
                continue
            tally.end_case()
            want = bytes(R.render(pl, p['pitch'], p['mouth'], p['throat'],
                                  p['speed'], p['singmode'], p['inflection']))
            if got != want:
                drift += 1
        print('== %s: %d cases, %d raised (skipped)' % (label, len(cases),
                                                         sum(raised.values())))
        for why, k in sorted(raised.items()):
            print('   raised %4d  %s' % (k, why))
        for name in sorted(tally.events):
            print('   %-48s %9d times in %4d cases'
                  % (name, tally.events[name], tally.cases[name]))
        for name in sorted(tally.ranges):
            lo, hi = tally.ranges[name]
            print('   range %-42s %d .. %d' % (name, lo, hi))
    print('copy drifted from renderer.render() on %d cases' % drift)
    return 1 if drift else 0


if __name__ == '__main__':
    sys.exit(main())
