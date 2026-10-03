# 3. Stage R.3 — the frames

Stage R.3 of [the C17 rewrite plan](../c17-rewrite-plan.md), on branch
`c17-r3-frames`. The engine turns a phoneme list and a voice into
frames: one column of pitch, three formant frequencies, three
amplitudes and a consonant flag for each frame, with the transitions
between phonemes interpolated.

**Result:** `engine/src/frames.[ch]` reproduce `create_frames()`,
`create_transitions()` and `prepare_frames()`.

- `verify_prepare.py --impl engine 3000` finds all 3,015 comparable
  cases equal to the Python, in all eight rows and the frame count, on
  both Windows legs.
- `verify_frames.py` still passes.
- The four legs build with zero warnings, and their `dump_prepare`
  output is identical.

Of the idioms `native/` took from the Python, two stay. They are the
first entries of `engine/src/quirks.h`. Six are dropped, each with the
bound that makes dropping it exact. The formant and amplitude rows are
bytes again, by a proof. The mutation suite has 30 mutants
(§3.6).

---

## 3.1 What the functions do

All three are in `renderer.py`. `native/src/sam_frames.c:89–380` is the C
this was rewritten from.

- **`create_frames`** (`renderer.py:110`) gives each phoneme `length`
  identical frames. Each frame has:
  - the voice's formants (R.2);
  - the phoneme's amplitudes and sampled-consonant flag;
  - a pitch of `(pitch + stress_pitch * inflection / 50) & 0xFF`.

  A `.` or `?` bends the pitch of the last 30 frames before it
  (`add_inflection`).
- **`create_transitions`** (`renderer.py:198`) ramps every row across
  each boundary between two phonemes. The stronger phoneme (the lower
  blend rank) sets how many frames either side take part. Pitch is
  different: its change is measured from the middle of one phoneme to
  the middle of the next, but the ramp starts where the other rows'
  ramps start. The ramp itself (`interpolate`) is a Bresenham line: each
  frame gets the frame before it plus `change / width`, and an error
  term spreads the remainder.
- **`prepare_frames`** (`renderer.py:298`) runs the voice, both of the
  above, then:
  - outside sing mode, takes half of F1 (scaled by the inflection) off
    each pitch;
  - maps every amplitude below 16 through `AMPLITUDE_RESCALE`.

In `frames.c` only `sam_prepare_frames` and `sam_frames_free` are
external. The rest are `static`. The constants the Python writes inline
are named:

- `INFLECTION_REACH` (30);
- `PITCH_SKIP_FIRST` and `PITCH_SKIP_LATER` (127 and 255);
- `RISING_INFLECTION` and `FALLING_INFLECTION`;
- `FRAMES_MAX`.

## 3.2 The idioms sorted

Plan §1.2 asks for every idiom to be sorted, with how the sorting was
established. The measurements cited are §3.3's. Where a row says
"proof", the proof is given below the table.

| Idiom in `native/` | Where | Bin | How established |
|---|---|---|---|
| `int` formant and amplitude rows | `sam_internal.h` `sam_frames_t` | **dropped**: `uint8_t` | proof (a); measured F1 0–52, F2 0–170, F3 0–121, A 0–19 |
| negative amplitude indexes `AMPLITUDE_RESCALE` from the end | `sam_frames.c:362–373` | **dropped** | follows from (a): no amplitude is negative; measured 0 times |
| `>> 1` of a possibly negative F1 (Python floors) | `sam_frames.c:351` | **dropped** | follows from (a): F1 is never negative; measured 0 times |
| `int(change / width)` | `sam_frames.c:209–214` | **dropped**: it is C's `/` | proof (b) |
| two frame counts, `count` and `total` | `sam_internal.h` | **dropped**: one | algebra (c) |
| `n < capacity` in create_frames' loop, `end` and `n` passed apart to `add_inflection` | `sam_frames.c:98, 172` | **dropped** | algebra (c): `n` is the row's length and its capacity throughout |
| `int` pitch row | `sam_internal.h` | **kept**: Q1, `sam_pitch_t` (`int32_t`) | measured −480 to 658; search reached 3,470 (§3.3) |
| a negative frame writes `t[len + frame]` | `sam_frames.c:235–251` | **kept**: Q2, `sam_py_index()` | 123,238 writes in 236 of 3,000 cases |

**(a) Formant and amplitude rows never leave `0 … max`.**

`create_frames` fills each of these six rows with bytes from the tables.
The claim is that no call of `interpolate` on one of them writes a value
below 0 or above the largest value already in that row. By induction
over the calls, the rows then stay bytes.

Take one call, with these values:

- `s = read(trans_start)` and `e = read(trans_end)`. Both are in
  `[0, M]`, where `M` is the row's maximum, because `read` returns
  either a row value or 0.
- `c = e − s`, the change.
- `w`, the width.

Step `k` (for `k` from 1 to `w − 1`) reads the frame step `k − 1` just
wrote. There are two exceptions:

- When that frame was negative, `read` returns 0 and the write went to
  the end of the row (Q2).
- When that frame was past the end, `read` returns 0 and the write was
  skipped.

A negative frame means `trans_start < 0`, and then `s = 0`. A frame past
the end means every later frame is too, so nothing more is written. In
every case that writes, then, the chain starts from `s` and builds on
its own writes. So step `k` writes

  `s + (k − k₀)·q + (corrections in steps k₀+1 … k)`,

where:

- `q` is the truncated step;
- `k₀` is the last step whose read came from outside the row (0 if
  none). After such a step the chain restarts from 0, but then `s` is 0
  too.

The corrections number at most `⌊k·r/w⌋ − ⌊k₀·r/w⌋`, with
`r = |c| mod w`. Since `k·q + ⌊k·r/w⌋ = ⌊k·c/w⌋` for `c ≥ 0`:

- **Rising (`c ≥ 0`):** the value is at least `s ≥ 0`, and at most
  `s + ⌊k·c/w⌋ ≤ s + c = e ≤ M`. The `elif val:` rule only ever drops
  a +1, which keeps the value above 0, since the value it leaves alone
  is 0.
- **Falling (`c < 0`):** this needs `s > e ≥ 0`, so `trans_start ≥ 0`.
  The value is at most `s ≤ M`, and at least `s − ⌊k·|c|/w⌋ ≥ s − |c|
  = e ≥ 0`.

∎. The amplitude rescale then maps a value below 16 to a byte from the
table, and leaves 16 and up as they are, so the rows are still bytes.

The pitch row is not covered: its change is measured between two other
frames (§3.1), so its ramp can leave the range it starts in. That is
Q1.

The proof is checked three ways:

- `row_write()` asserts it on every write.
- An assert-enabled Debug build ran the following, and no assert fired:
  - `verify_prepare.py --impl engine 20000`: 20,004 comparable cases,
    all equal;
  - 200,000 C-only cases with phonemes 0–255 and lengths 0–255,
    outside what the Python defines.
- A mutation that masks the Python's six rows to a byte lives (§3.6).

**(b) `int(change / width)` is C's `change / width`.** C17 6.5.5p6
truncates integer division toward zero, and so does `int()`. The question
is whether the float quotient can round onto an integer that the exact
quotient is not. If `c/w` is not an integer, it lies at least `1/w` from
one. Its rounding error is at most half an ulp, under `|c/w|·2⁻⁵³`.
That is smaller than `1/w` whenever `|c| < 2⁵³`. In the rewrite, `c` is
the difference of two `int32_t` values. A mutation that replaces the
Python's line with exact integer truncation lives (§3.6).

**(c) One frame count.** `create_transitions` returns
`boundary + length[last]`, where `boundary` is the sum of every length
but the last. That is the sum of all the lengths. `create_frames`
appends `length` frames per phoneme, so the row is that long too.
`native/` stored both as `total` and `count` and capped its fill loop at
`capacity`, which was that same sum. The rewrite keeps one `count` and
asserts the identity. `dump_prepare` prints `count` twice, because the
format has two columns.

### Not Python idioms, but sorted all the same

- **`elif val:`** in the ramp: a rising ramp never lifts a 0. It is in
  the Python as explicit logic, not as a language semantic. It is
  reached in 2,000 of 3,000 cases. It stays, in `frames.c`, with a
  comment. Its origin is not verified: the JavaScript and Macke's C are
  not in this tree.
- **`& 0xFF` and `& 128` on values that can be negative.** Python's `&`
  works on two's complement whatever the sign. C17 does not promise two's
  complement for signed types (C23 does). The rewrite converts to an
  unsigned type first (`low_byte()`, and `(unsigned)(trans_length − 2)
  & 0x80u`). Conversion to unsigned is modular, so the bits are Python's
  on any C17 compiler. This is SAM's own byte arithmetic, written so it
  is portable, not an idiom.
- **The inflection's float arithmetic** (`inflection / 50.0`, then
  `int()`). This is this project's extension, not SAM's, and not on the
  plan's §1.1 list.
  - The rewrite keeps it in `double`, which is the same IEEE binary64 as
    Python's `float`. An `#error` stops a build whose
    `FLT_EVAL_METHOD` would evaluate it wider.
  - `native/` cast the product to `int` unguarded. That is undefined
    behaviour once the product leaves `int`, which needs an inflection
    beyond about ±431 million. The rewrite saturates there instead.
    `sam_render.h` documents 0–100.
- **A phoneme past the tables (80 to 255).** The Python raises reading
  the frequency row. `native/` gave the phoneme zeros in every row, and
  the rewrite does too, so the public API behaves as before. The parser
  never emits one.
- **A write below `−len`.** The Python raises `IndexError`.
  `verify_prepare.py` skips those cases (1 in 3,000). As in `native/`,
  the write is skipped, and Q2 returns −1 for it.

## 3.3 The measurements

`engine/tools/reach_frames.py` (new, kept) runs an instrumented copy of
`create_transitions` and `prepare_frames` over `verify_prepare.py`'s own
corpus, from its own seed. It counts each event, and it takes the range
of each row. The copy computes what `renderer.py` computes, and it only
counts. A case on which the Python raises is dropped whole, as the
verifier drops it. Run on 2026-10-03:

```
== golden: 16 cases, 0 raised IndexError (skipped)
  no transition (bit 7 of trans_length - 2)                  28 events in     8 cases
  write past the end, skipped                                 6 events in     1 cases
  range A1 before rescale        (0, 15)     range F1    (0, 36)
  range A2 before rescale        (0, 14)     range F2    (0, 132)
  range A3 before rescale        (0, 8)      range F3    (38, 121)
  range pitch after transitions  (0, 249)    range trans_length (0, 8)
== random: 3000 cases, 1 raised IndexError (skipped)
  amplitude 16 or more, kept                              22504 events in   494 cases
  elif val: leaves a 0 alone                              81827 events in  2000 cases
  negative index write (Q2)                              123238 events in   236 cases
  no transition (bit 7 of trans_length - 2)               17002 events in  2603 cases
  trans_start negative                                      339 events in   265 cases
  width 0                                                    54 events in    51 cases
  write past the end, skipped                            130579 events in  1297 cases
  range A1 before rescale        (0, 15)     range F1    (0, 52)
  range A2 before rescale        (0, 14)     range F2    (0, 170)
  range A3 before rescale        (0, 19)     range F3    (0, 121)
  range pitch after transitions  (-480, 658)
  range pitch out, sing mode     (-480, 569)
  range trans_length             (0, 336)
```

(The two range columns are folded together here for width. The tool
prints one per line.)

Events that never happened print nothing:

- a negative amplitude;
- a negative F1 at the `>> 1`;
- `int(change / width)` disagreeing with integer division;
- the frame count differing from the row length.

**The pitch row's reach.** `native/`'s comment gave −194 to 366,
measured on the 400 cases the verifier ran by default then. The 3,000
reach −480 to 658.

`reach_frames.py --grow N` hill-climbs on `N` random phonemes for the
largest `|pitch|`. It runs six restarts of 4,000 steps each, from
seed 7. A scratch copy of the same search gave:

| N | largest \|pitch\| |
|---|---|
| 10 | 2,429 |
| 30 | 3,470 |
| 60 | 2,352 |
| 120 | 1,264 |

The kept tool, run again for N = 30, printed `N 30: largest |pitch| found 3470`, the same number.

There is no proof of a bound. One transition writes values between
`p[trans_start]` and `p[trans_start] + (p[pitch_end] − p[pitch_start])`,
so the row's range can grow to three times its width per transition.
What stops it in practice is not known.

So Q1 is `int32_t`, which holds everything measured with a factor of
over 600,000 to spare. The ramp computes in `int64_t`, and `to_pitch()`
saturates into the row, so an input past `int32_t` is defined behaviour.
There the rewrite and the Python would disagree, as `native/` would
have, and with undefined behaviour too.

`int16_t` would hold the corpus and the search. The mutation suite
shows it passing (§3.6). It is not used, because the margin is a
measurement, not a proof.

## 3.4 The dump tool

`engine/tools/dump_prepare.c` reads `verify_prepare.py`'s case file and
prints `native/tools/dump_prepare.c`'s line for each case. The line is:

- the frame count twice (§3.2 (c));
- then FNV-1a over each of the eight rows, each value as four
  little-endian bytes of a 32-bit two's-complement integer.

The byte rows are hashed through the same `int` path. The values reach
the hash through a conversion to `uint32_t`, which is modular, so a
negative pitch hashes as Python's `v & 0xFFFFFFFF` does.
`verify_prepare.py` is unchanged. `dump_prepare` is added to the
dump-tool `foreach`, which turns the `verify_prepare;3000` ctest from
skipped to run.

## 3.5 The four legs

`python engine/tools/build_matrix.py`, 2026-10-03:

```
leg        build    tests              notes
msvc       ok       5/9 (4 skipped)    0 warnings
clang-cl   ok       5/9 (4 skipped)    0 warnings
wsl-gcc    ok       2/2                0 warnings
wsl-clang  ok       2/2                0 warnings
```

On Windows the five that pass are:

- `abi`;
- `tables_current`;
- `verify_tables`;
- `verify_frames`;
- `verify_prepare` (3,000).

The four skips are R.4 to R.7.

On Linux, as in R.2, the verifiers do not run yet (R.10). Instead,
`verify_prepare.py`'s case file (16 golden and 3,000 random cases, 3,016
lines) was written once. All four legs' `dump_prepare` ran on it, and
each output gave MD5 `90df7000687fe89adb49ccf50acb0da0`, with CR removed
on Windows. So gcc and clang on Linux produce the rows that the Python
accepts on Windows.

The exports are still exactly `sam_abi_version` and
`sam_text_abi_version`. That was checked with `dumpbin /exports` on the
MSVC DLL and `nm -D --defined-only` on the gcc `.so`.

## 3.6 The mutation suite

`engine/tools/mutants/r3.py`. There is one check:
`verify_prepare.py --impl engine 3000`. It runs on a Release build, so
the asserts are off and the verifier alone has to see each mutant.

```
mutant                                                            verify_prepare
inflection reaches 29 frames back, not 30                         killed          ok
first skipped pitch 127 -> 126                                    killed          ok
later skipped pitch 255 -> 254                                    killed          ok
rising inflection 255 -> 254                                      killed          ok
falling inflection 1 -> 2                                         killed          ok
'.' and '?' swapped                                               killed          ok
rising inflection not clamped to 255                              killed          ok
stress pitch not scaled by inflection                             killed          ok
scaled() rounds instead of truncating                             killed          ok
ramp lifts a 0 too (no `elif val:`)                               killed          ok
ramp never corrects the error term                                killed          ok
read() wraps negative positions too                               killed          ok
bit 7 test on 0x40                                                killed          ok
equal ranks: in_blend from the in table                           killed          ok
pitch ramp starts at pitch_start ("fixed")                        killed          ok
pitch ramp skipped at pitch_start 0                               killed          ok
F1 adjustment uses a quarter, not a half                          killed          ok
F1 adjustment in sing mode too                                    killed          ok
amplitude 16 and up rescaled too (& 15)                           killed          ok
Q1: pitch row a byte                                              killed          ok
Q1: pitch row int16_t (holds the corpus)                          lived           ok
Q2: rewrite skips negative writes                                 killed          ok
Q2: oracle skips negative writes                                  killed          ok
oracle: int(change / width) as integer division (equivalent)      lived           ok
oracle: no negative amplitude index (equivalent)                  lived           ok
oracle: F1 halved by truncation, not floor (equivalent)           lived           ok
oracle: formant and amplitude rows masked to a byte (equivalent)  lived           ok
dump: frame count off by one                                      killed          ok
dump: pitch hashed as a byte                                      killed          ok
dump: amplitude rows in the wrong order                           killed          ok

30 mutants, 30 as expected, 0 not
```

What the groups show:

- **SAM's arithmetic.** Every constant, comparison and table choice in
  the three functions is visible in the 3,000 cases.
- **Q1 and Q2 kept.**
  - Making the pitch row a byte dies, and so does skipping negative
    writes, in the rewrite or in the oracle. That is "the voice depends
    on it", run.
  - `int16_t` lives: it holds the corpus. §3.3 says why it is still not
    used.
- **The dropped idioms.** Each one, taken out of the oracle, changes
  nothing, so each such mutant lives:
  - integer division for `int(change / width)`;
  - no negative amplitude index;
  - a truncating halving of F1;
  - masking the six byte rows.

  Those are the claims of §3.2, run.
- **The dump tool lying.** A wrong count, a pitch hashed as a byte, and
  the amplitude rows swapped are each caught.

## 3.7 What R.3 did not do

- **No coverage build.** Plan §5 sorts quirks by a gcc `--coverage` run
  over the whole R.5–R.7 corpus. That corpus does not exist before R.7.
  This stage sorted by the instrumented oracle over `verify_prepare.py`'s
  corpus, which is random phoneme lists, and so is wider than anything
  the parser emits.
  - The golden cases (real speech) reach neither Q1 nor Q2: pitch
    stays 0–249, and no write is negative.
  - Whether real text ever does is R.9's question. Until then both
    stay: they are reached in the verified domain.
- **No sanitizers.** They come at R.4 and R.7, per the plan. The
  Debug build's asserts stood in for the bounds this stage relies on.
- **`native/` untouched.** Its `verify_prepare.py --impl native` still
  passes.

## 3.8 Files

New:
- `engine/src/frames.c`, `engine/src/frames.h`;
- `engine/src/quirks.h` (Q1, Q2);
- `engine/tools/dump_prepare.c`;
- `engine/tools/reach_frames.py`;
- `engine/tools/mutants/r3.py`;
- this chapter.

Changed:
- `engine/CMakeLists.txt`: `frames.c` added to the library, and
  `dump_prepare` added to the tools.

Not touched:
- `native/`;
- the Python;
- the golden vectors;
- `sam-native.zip`;
- the author's uncommitted driver work.

**Known, inferred, guessed.**
- *Known:*
  - every count and range above was printed by the command named with
    it, on 2026-10-03;
  - (a), (b) and (c) are proofs, and the asserts and the mutation suite
    agree with them.
- *Inferred:* that a crafted input could push the pitch row far beyond
  what was found. The tripling argument allows it, but the search did
  not find it, so this is not shown.
- *Guessed:* that `elif val:` is SAM's rather than the JavaScript's. It
  reads like the 6502's "leave 0 alone" test. It is kept either way,
  because it is reached.
