# 4. Stage R.4 — the renderer

Stage R.4 of [the C17 rewrite plan](../c17-rewrite-plan.md), on branch
`c17-r4-renderer`. The engine turns frames into sound: two sine
formants and a square one, reset at every glottal pulse, plus the
sampled consonants, written as 8-bit unsigned PCM at 22,050 Hz.

**Result:** `engine/src/render.c` reproduces `process_frames()`,
`render_sample()`, `OutputBuffer` and `render()`, and the rewrite's
DLL now exports `sam_render`.

- `verify_render.py --impl engine` matches the Python byte for byte on
  all 16 golden cases. Of 3,000 random cases, the Python can render
  2,898, and all 2,898 match. The other 102 are cases where the
  Python raises.
- `diff_render.py` compares the rewrite with `native/`'s DLL on 20,000
  wider cases, including the ones the Python raises on. None differ.
- The corpus, run under AddressSanitizer and UBSan with gcc and with
  clang, produces no report, and its output equals the MSVC build's.
  Planted bugs show the sanitizers do fire.
- `native/` has undefined behaviour on valid input: a signed `int`
  overflows in its phase arithmetic. UBSan reports it on a constructed
  long utterance. The rewrite gives the Python's 2,528,172 samples
  there, with no report (§4.6).
- The mutation suite has 30 mutants (§4.9).

Before any of that: **the fuzz this stage's exit test names had been
comparing `native/`'s DLL with itself since 2026-09-06** (§4.1). It now
compares with the Python, and the exit count is restated in those terms.

`quirks.h` gains Q3. The glottal pulse counters do not wrap, because the
Python's unbounded `int` never does. Four further idioms are dropped,
each with its proof.

---

## 4.1 The fuzz was not comparing with the Python

`verify_render.py N` renders N random cases through the DLL, and
through `renderer.render()` as the reference. But `renderer.render()`
hands off to `native.py` whenever that module can load a DLL, and
`native.py` looks in two places: next to itself (the installed addon),
then in `native/build/sam_render-x64.dll` (a development tree). So on
any machine where `native/` had been built, the reference was the DLL
itself.

How it was established, 2026-10-03:

- In `nvda-addon/synthDrivers/sam`, `import renderer` gives
  `renderer.native` as the module, and `native._load()` returns
  `CDLL('…\native\build\sam_render-x64.dll')`.
- The committed `verify_render.py` was copied out and run with 60
  cases. It reported `60/60 randomised cases byte-identical`. The fixed
  one reports `57/57 … (3 skipped: Python raised)`. The DLL never
  raises, so 60 of 60 with no skips is the DLL agreeing with itself.
- History: the fuzz came with `d15d3d3` (2026-09-06 21:10, "Complete
  the native renderer"). The hand-off came with `2cfc2b2` four minutes
  later ("Use the native renderer in the addon"). The port's own run,
  in the first commit, did compare with the Python (inferred from that
  order; the run itself is not in the log). Every later run with
  `native/build` present compared the DLL with itself. That includes
  R.0's baseline ("485 random sequences byte-identical",
  [docs/c17/00](00-r0-scaffold.md)).

`check_golden.py` had the same trap and already avoided it, by setting
`renderer.native = None` before rendering. `verify_render.py` now does
the same. That is its only behavioural change. The case generation
moved into a function, `fuzz_cases(n)`, which yields the same sequence
from the same seed, so that `engine/tools/reach_render.py` measures
exactly the verifier's corpus.

With the fix, `native/` itself still passes:
`verify_render.py --impl native 485` gives 16 golden cases and
`470/470 randomised cases byte-identical (15 skipped: Python raised)`.
So the port was right; only the check had gone hollow.

The plan's exit test for R.4 asked for "a count at least the 485 the
port passed". In the terms it meant, that is 470 cases compared with
the Python. R.4 ran 3,000, of which 2,898 compared.

## 4.2 The idioms sorted

`native/src/sam_render.c` is the C this was rewritten from.

| Idiom in `native/` | Where | Bin | How established |
|---|---|---|---|
| unbounded `int` phases, `phase * 256` | `sam_render.c:144, 173–175, 227–229` | **dropped**: `uint8_t`, modulo 256 | proof (a); measured up to 7,443,690, and `native/` overflows (§4.6) |
| `pos < n` before every row read; `pos >= n` ends the loop | `sam_render.c:159–161, 179–184, 224–226, 242` | **dropped** | invariant (b); none fails over the corpus |
| `(pos & 0xFF) < n ? pitches[pos & 0xFF] : 0` | `sam_render.c:166, 235` | **dropped**: the `0` | invariant (b) |
| kind −1 reads `values0[-1]` (Python's negative index) | `sam_render.c:109–121` | **dropped** | enumeration (c); 0 times |
| `sample_idx` checked against the table, both ends | `sam_render.c:68–70` | **dropped** | enumeration (c); 0 times |
| `int(mux / 32)`, a float division then truncation | `sam_render.c:198` (native already used `/`) | **dropped**: C's `/` | proof (d) |
| `int(glottal_pulse * 0.75)` in a double | `sam_render.c:155, 243` | **dropped**: `g * 3 / 4` in `int64_t` | proof (e) |
| `pitch >> 4` of a pitch that may be negative or past a byte | `sam_render.c:93` | **dropped**: shift of the `uint32_t` conversion | proof (f) |
| the glottal pulse and `mem38` in Python's unbounded `int` | `sam_render.c:153–155, 218–243` | **kept**: Q3, `sam_pulse_t` (`int64_t`) | measured: 10 + 68 cases enter it, 1,734,241 stuck steps in 78 (§4.3) |
| the Python's `RuntimeError("Buffer overflow")` | `sam_render.c:36–39` | **outside the oracle**: as `native/` | 10 of 485 random cases; §4.4 |

### (a) Only the phase modulo 256 reaches the output

Each formant step computes `p = phase * 256`, adds `d = freq * 64`
five times, and reads `(p >> 8) & 0xFF` before each addition. At the
k-th read, `p = phase * 256 + k * d`, with `k * d >= 0`. For integers
`a` and `x >= 0`, `(a * 256 + x) >> 8 = a + (x >> 8)`, because a floor
division by 256 lets `a * 256` through whole. So the read is
`(phase + ((k * d) >> 8)) mod 256`, which depends on `phase` only
modulo 256. Every phase starts at 0 and only adds frequencies, which
are bytes ≥ 0. `uint8_t` arithmetic is exactly modulo 256, so the
rewrite keeps the phases as `uint8_t`. It keeps `p` as `uint32_t`,
where a wrap modulo 2^32 leaves bits 8–15, the only ones read,
unchanged.

The measurement (§4.3) shows why this matters: the Python's phase
reached 7,443,690 in 485 random cases. `native/` keeps `phase * 256` in
an `int`, which overflows past 8,388,607. 7,443,690 is 11% below that,
and §4.6 crosses it.

### (b) pos and frame_count always add up to the row length

The Python's loop starts with `frame_count = t`, the frame count. R.3
showed that `t` equals the length of every row
([docs/c17/03](03-r3-frames.md) §3.2 (c)). `pos` starts at 0. The loop
moves the two only together: `pos += 2; frame_count -= 2` for an
unvoiced sample, and `pos += 1; frame_count -= 1` at the end of a
frame. So `pos + frame_count = n` throughout, and `frame_count > 0`
holds exactly when `pos < n`. From that:

- `if pos >= n_flags: break` can only fire when the loop condition
  already ends the loop.
- After `pos += 1`, `frame_count == 0 → return` fires exactly when
  `pos == n`. Every read after that point (the phase step and the pulse
  reset) therefore has `pos < n`.
- `pos & 0xFF <= pos < n`, so the pitch read at `pos & 0xFF` is
  always in the row, and its `else 0` never applies.

The rewrite has a loop condition `pos < n` and a `return` at
`pos == n`, and no other check. That `pos` is read at `pos & 0xFF` is
SAM's 6502 index register, not a Python idiom. It is kept, and is
reached in 149 of 485 cases.

### (c) The sampled consonant's kind is always 0 to 4

The kind is `(flags & 7) - 1`, and the flags row holds only values from
`sam_sampled_consonant_flags`, or 0 for a phoneme ≥ 80 (R.3,
`phoneme_values()`). `create_transitions()` does not touch that row.
The table has twelve nonzero values:

| flag | phonemes | kind | |
|---|---|---|---|
| 0x01 | 38 | 0 | voiced |
| 0x02 | 39, 45 | 1 | voiced |
| 0x03 | 40, 41 | 2 | voiced |
| 0x19 | 70 | 0 | unvoiced, offset 24 |
| 0x1B | 67 | 2 | unvoiced, offset 24 |
| 0x72 | 43 | 1 | unvoiced, offset 112 |
| 0x7C | 36 | 3 | unvoiced, offset 120 |
| 0x95 | 37 | 4 | unvoiced, offset 144 |
| 0xBB | 35 | 2 | unvoiced, offset 184 |
| 0xD3 | 34 | 2 | unvoiced, offset 208 |
| 0xE2 | 33 | 1 | unvoiced, offset 224 |
| 0xF1 | 32 | 0 | unvoiced, offset 240 |

`render_sample()` is called only with a nonzero flag:

- unvoiced when `flags & 0xF8 != 0`;
- voiced when `flags != 0`, after `flags & 0xF8 == 0`.

So the kind is 0–4. The largest index into `sam_sample_table` is then
4 · 256 + 255 = 1,279, inside its 1,280 bytes. Both of the Python's
guards are unreachable: `sample_idx >= len(SAMPLE_TABLE)`, and
`kind < len(VALUES0)`, whose negative-index branch at kind −1 never
runs. The table was enumerated from `renderer_tables.py`, and R.1
verified `engine/src/tables.c` equal to it value for value. The
rewrite asserts the range in `render_sample()`.

### (d) int(sum / 32) is C's division

`|sum| <= 15 · (127 + 127 + 112) = 5,490`, since the sine table spans
−127..127 (measured), the square wave is ±0x70, and the amplitudes are
masked to 0–15. A division by 32 is exact in binary floating point for
any integer this small, so `int()` truncates the exact quotient toward
zero, and so does C's `/` (C17 6.5.5). The two agree. A floor (`>> 5`)
would not: the corpus has 15 million negative sums that are not
multiples of 32, and the mutant that floors dies.

### (e) int(g * 0.75) is g * 3 / 4

`g` is an `int32_t` pitch (Q1). `g * 0.75` is exact in a double for
`|g| < 2^51`, and `int()` truncates it. `3 * g` is exact in `int64_t`,
and C's `/ 4` truncates the same real number. A mutant that rounds the
other way, `g - g / 4`, dies.

### (f) pitch >> 4, and the pitch wider than a byte

A voiced consonant lasts `(((pitch >> 4) ^ 255) & 0xFF)` bytes of
noise, short of 256. Python's `>>` floors, and `& 0xFF` keeps bits
4–11 of the pitch in two's complement. The pitch here is Q1's: 1
random case has a negative one at this point and 2 have one over 255.
The rewrite converts it to `uint32_t`, which is modular in C, so the
bits are the same, then shifts. No negative number is shifted. Masking
the pitch to a byte first is a mutant, and it dies.

### What stays, not proved unreachable

- **The clamp of the mixed sample to 0..255.** The tables allow
  −43..299 (−5,490 / 32 + 128 to 5,490 / 32 + 128). The corpus reached
  only 3..252 (sums −4,004..3,991). It is not proved unreachable, and
  it costs nothing, so it stays. Removing it is an equivalent mutant
  over the corpus, and it is listed so.
- **`amplitude & 0x0F`.** This is SAM's, and it is reached: amplitude
  values of 16 or more come out of the ramps (R.3), in 22 of 485 cases.
- **`(level & 15) * 16` for a sample level.** This is SAM's 4-bit
  volume register. Into a byte, `(x * 16) mod 256` equals
  `(x & 15) * 16` for every `x`, so the mask changes nothing. It is
  kept for what it says, and listed as an equivalent mutant.

## 4.3 The measurements

`python engine/tools/reach_render.py 485`, 2026-10-03:

- It takes `verify_render.py`'s own corpus: the 16 golden cases, then
  `fuzz_cases(485)`.
- It builds frames with the unchanged `renderer.prepare_frames()`.
- It runs an instrumented copy of `process_frames()` and
  `render_sample()`. A case the Python raises on is counted by its
  exception and leaves no counts behind.
- Its last line compares the copy's PCM with `renderer.render()` on
  every case: "drifted on 0 cases".

```
== golden: 16 cases, 0 raised (skipped)
   negative mux sum, truncated not floored             101298 times in   16 cases
   unvoiced sample                                         15 times in    8 cases
   voiced sample                                           20 times in    4 cases
   voiced sample at mem38 0                                20 times in    4 cases
   range glottal pulse at reset                     9 .. 250
   range kind                                       0 .. 3
   range mux sum                                    -3976 .. 3976
   range phase                                      0 .. 22599
   range pitch row                                  9 .. 250
   range samples / buffer size %                    1 .. 2
== random: 485 cases, 15 raised (skipped)
   raised    5  IndexError: list assignment index out of range
   raised   10  RuntimeError: Buffer overflow
   amplitude over 15, & 0x0F                            29559 times in   22 cases
   first glottal pulse <= 0: never resets                  10 times in   10 cases
   formant step with the pulse stuck                  1734241 times in   78 cases
   frame count -1 after an unvoiced sample                 17 times in   17 cases
   negative mux sum, truncated not floored           15183937 times in  424 cases
   negative pitch into pitch >> 4 (floors)                  1 times in    1 cases
   pitch over 255 into pitch >> 4                           6 times in    2 cases
   pitch read at pos & 0xFF (pos over 255)               4743 times in  149 cases
   pulse reset to <= 0: never resets again                 68 times in   68 cases
   unvoiced sample                                       7213 times in  330 cases
   voiced sample                                        14698 times in  197 cases
   voiced sample at mem38 0                             14698 times in  197 cases
   range glottal pulse at reset                     -9 .. 428
   range kind                                       0 .. 4
   range mux sum                                    -4004 .. 3991
   range phase                                      0 .. 7443690
   range pitch row                                  -243 .. 488
   range samples / buffer size %                    1 .. 98
copy drifted from renderer.render() on 0 cases
```

What the tool counts and never saw:

- kind −1;
- a sample index past the table;
- `pos` past the rows, at the loop head, at a phase step or at a pulse
  reset;
- a pitch read at `pos & 0xFF` past the row;
- a mixed sample clamped at either end;
- rows of different lengths;
- a frame count different from the row length;
- a write in advance cut at the buffer's end, in a case that did not
  overflow.

Q3, "the voice depends on it":

- **10 random cases start with a glottal pulse ≤ 0.** Pitch 0 comes
  from the non-sing-mode `& 0xFF`; a negative pitch from sing mode
  (Q1).
- **68 cases reset into one.**
- **78 cases render 1,734,241 formant steps while stuck.** In all of
  them the Python's pulse only falls, never reaches 0 again, and
  neither resets the phases nor samples a voiced consonant.

None of the 16 golden cases (real speech) reaches Q3, the wider pitch
into `>> 4`, or the overflow. They also show the buffer the size query
reserves: real speech uses 1–2 % of it (§4.7).

## 4.4 Beyond the oracle: native/ and the rewrite agree

The Python defines nothing where it raises. There, the rewrite does
what `native/` did:

- **`IndexError` from `create_transitions`** (Q2 below −len, R.3): the
  write is skipped.
- **`RuntimeError("Buffer overflow")`**, when the write position passes
  the reserved buffer: this write is skipped. The time keeps moving,
  and `last_write` is not updated. All ten such cases in the corpus are
  at speed 1 (measured: the other five raises, `IndexError`, are at
  speeds 72, 150 and 255). At speed 1 the buffer reserves 176 samples
  per frame. A sampled consonant writes 8 samples for every byte of
  noise, of which it reads up to 256, so one consonant can outrun that
  reservation.

So `native/` is the reference past the oracle.
`engine/tools/diff_render.py` loads both DLLs side by side. Their file
names differ, so Windows loads them as two libraries. It renders
random cases through both, with the output buffer prefilled with 0xA5,
so that an unwritten byte shows up. The generator is wider than the
verifier's:

- every phoneme byte;
- lengths and stresses 0–255;
- every speed, 0 included;
- inflection −1,000..1,000;
- `singmode` 0, 1 or 7.

Each case stays under 10 MB of buffer.

```
python engine/tools/diff_render.py        (seed 4)
20000 cases from seed 4: SAM_E_BADSPEED 3329, empty 17, samples 16654
0 differ between native/ and engine/
```

Inflection stops at ±1,000 because `native/` casts the inflection
product to `int` with undefined behaviour far past that (R.3 §3.4).
Under that limit, the two agree on every case: rendered, empty and
refused.

## 4.5 A bug of the rewrite's, and a misleading comment

The first build failed four golden cases: `mouth_throat_max` and
`mouth_throat_zero` by 7 bytes, and `pitch_floor` and `sentence` by
hundreds. The cause was the time-table rows of the voiced samples.
`renderer.py`'s table is commented `# voiced sample 0` for row 3 and
`# voiced sample 1` for row 4. But `render_sample()` calls
`render_sample_inner(3, 26, 4, 6)`, which writes row 3 for a **1** bit
and row 4 for a **0** bit. The rewrite's enum had followed the
comments. It now follows the calls, `WRITE_VOICED_1 = 3` and
`WRITE_VOICED_0 = 4`, with a note in `render.c`. The comment in
`renderer.py` is left alone, because the oracle is not edited. The
swap is a mutant, and the golden cases kill it.

## 4.6 The sanitizers

`python engine/tools/sanitize.py`, 2026-10-03. For each of wsl-gcc
(gcc 14.2.0) and wsl-clang (clang 19.1.7), it makes a Debug build
(asserts on) at `-O1` with
`-fsanitize=address,undefined,float-cast-overflow -fno-sanitize-recover=all`.
Its `dump_render` runs over one case file, which holds:

- the 16 golden cases;
- `fuzz_cases(485)`;
- one long stuck-pulse utterance (below);
- 5,000 cases from `diff_render.py`'s generator.

The output must equal the MSVC Release build's line for line, and
nothing may be reported:

```
5502 cases; msvc dump_render: 5502 lines
wsl-gcc    exit 0, 5502 lines, same as msvc, 0 sanitizer reports: ok
wsl-clang  exit 0, 5502 lines, same as msvc, 0 sanitizer reports: ok
```

A clean report proves nothing unless the sanitizers can fire. Each kind
was shown to fire with a planted bug, on both compilers:

- **ASan.** At the pulse reset, `fr->pitch[pos]` became
  `fr->pitch[pos] + fr->flags[n]`, one byte past the frame block. Both
  compilers reported `heap-buffer-overflow … in process_frames`, and
  both exited 1.
- **UBSan.** The voiced length became `(uint32_t)(pitch << 28) >> 4`.
  Both reported `left shift of 60 by 28 places cannot be represented in
  type 'int'`.

The first plant tried, `fr->pitch[n]`, was not caught. It still reads
inside the one allocation of R.3's frame block (the byte rows follow the
pitch row). The output changed, so `sanitize.py` failed on the
difference, but ASan had nothing to report. A read inside one block
is invisible to ASan; the verifiers are what catch it.

### native/ overflows an int on valid input

The same build of `native/`'s three renderer files, with
`-fsanitize=undefined,float-cast-overflow`, reported nothing on the
5,501 random and golden cases. Long utterances are what the phase
arithmetic needs, so one was built:

- twelve phonemes 9, each of length 255;
- speed 255, sing mode, pitch 0, inflection 0.

Every pitch is then 0, the pulse is stuck from the first frame, and the
phases run for about 780,000 steps.

```
native/src/sam_render.c:203:20: runtime error: signed integer overflow: 2147483136 + 5696 cannot be represented in type 'int'
native/src/sam_render.c:175:17: runtime error: signed integer overflow: 8388695 * 256 cannot be represented in type 'int'
```

All of these inputs are within `sam_render.h`'s documented ranges.
MSVC happens to wrap, and wrapping happens to give the right answer,
by (a). The rewrite renders the case without a report and equals the
Python:

| | samples | FNV-1a |
|---|---|---|
| Python, `renderer.render()` (8 s) | 2,528,172 | 4004425672 |
| rewrite, MSVC Release | 2,528,172 | 4004425672 |
| rewrite, gcc ASan + UBSan | 2,528,172 | 4004425672 |

The case is now part of `sanitize.py`'s file.

## 4.7 The output buffer

`render()` reserves `int(176.4 * frames * speed)` bytes, zeroed, and
the size query returns the same number. `native/` callocs that,
renders, and copies out what was produced. Real speech uses 1–2 % of
it (`hello_default`: a query of 495,331 bytes for 9,789 samples). The
rewrite changes how this is done, not what comes out:

- **When `out_capacity` covers the whole reservation**, which it does
  after a query, the rewrite renders straight into `out` and allocates
  nothing but the frames.
- **Otherwise** it renders into a buffer of its own and copies, so
  that `SAM_E_SHORTBUF` still writes nothing to `out`, as
  `sam_render.h` promises.
- **Zeroing is lazy.** The Python's buffer is all zeros, and the first
  write lands at sample 3, so samples 0–2 of every utterance are zeros
  nobody wrote. The rewrite zeroes bytes only as the write position
  passes them. `zeroed` is the mark below which every byte has been
  zeroed or written. A mutant that drops the zeroing is caught by
  `diff_render.py`'s 0xA5 fill. The verifier cannot see it, because
  ctypes buffers start at zero.

`engine/tests/test_render.c` checks the contract on every leg against
two golden vectors (`a_fast`, `hello_default`):

- the query's capacity, rendered in place;
- exactly the rendered length, rendered through the library's buffer;
- one byte short: `SAM_E_SHORTBUF`, with `out` left untouched;
- nothing written past the capacity;
- the four argument errors, and a list with no frames.

This is also the first golden check the Linux legs run through ctest.

How much faster this is was not measured. That is R.9's job, against
§7's baseline.

## 4.8 The four legs

`python engine/tools/build_matrix.py`, 2026-10-03:

```
leg        build    tests              notes
msvc       ok       7/10 (3 skipped)   0 warnings
clang-cl   ok       7/10 (3 skipped)   0 warnings
wsl-gcc    ok       3/3                0 warnings
wsl-clang  ok       3/3                0 warnings
```

On Windows the passing tests are `abi`, `render`, `tables_current`,
`verify_tables`, `verify_frames`, `verify_prepare` (3,000) and
`verify_render` (485). The three skips are R.5 to R.7. On Linux:
`abi`, `render` and `tables_current`.

The four legs' `dump_render` output over `sanitize.py`'s 5,502-case
file has the same MD5 on all of them, `ca6b850b738736d08ff06a8f8868504a`
(CR removed on Windows).

The exports are now exactly `sam_abi_version`, `sam_render` and
`sam_text_abi_version`. That was checked with `dumpbin /exports` on the
MSVC DLL and `nm -D --defined-only` on the gcc `.so`.

## 4.9 The mutation suite

`engine/tools/mutants/r4.py`. There are two checks, both on a Release
build:

- `verify_render.py --impl engine 485`, against the Python;
- `diff_render.py 3000`, against the real tree's `native/` DLL, which
  the scratch copy lacks.

```
mutant                                                     verify_render  diff_render
time table row never moves on (always formants)            killed         killed       ok
50 time units per sample -> 49                             killed         killed       ok
voiced rows 3 and 4 swapped (as the table comments say)    killed         killed       ok
voiced 1-bit level 26 -> 27                                killed         killed       ok
unvoiced 1-bit level 5 -> 4                                killed         killed       ok
noise read from bit 6, not bit 7                           killed         killed       ok
voiced length not complemented                             killed         killed       ok
Q1: voiced length from a byte pitch                        killed         lived        ok
voiced sample does not carry its offset on                 killed         killed       ok
unvoiced 0-bit level from kind 0 always                    killed         killed       ok
phase step freq * 63, not * 64                             killed         killed       ok
square wave flips at 128, not 129                          killed         killed       ok
square wave height 0x70 -> 0x6F                            killed         killed       ok
mux sum floored (>> 5), not truncated (/ 32)               killed         killed       ok
amplitude not masked to 4 bits                             killed         killed       ok
phases not reset at the glottal pulse                      killed         killed       ok
pitch read at pos, not pos & 0xFF (both reads)             killed         killed       ok
unvoiced sample takes one frame, not two                   killed         killed       ok
mem38 = g - g / 4 (rounds up), not int(g * 0.75)           killed         killed       ok
Q3: pulse counters a byte                                  killed         killed       ok
Q3: oracle pulse wraps at a byte                           killed         lived        ok
oracle: no sample table guard (unreached)                  lived          lived        ok
oracle: no values0 guard (unreached)                       lived          lived        ok
oracle: phases kept modulo 256 (equivalent)                lived          lived        ok
oracle: no pos < n guards in the loop (unreached)          lived          lived        ok
no zeroing ahead of a write (the first 3 samples)          lived          killed       ok
mux not clamped (unreached: 3..252 measured)               lived          lived        ok
level not masked to 4 bits ((x * 16) mod 256 is the same)  lived          lived        ok
overflow test pos >= size (equivalent)                     lived          lived        ok
speed counter not restarted after unvoiced (equivalent)    lived          lived        ok

30 mutants, 30 as expected, 0 not
```

What the groups show:

- **SAM's arithmetic.** Every constant, row and branch of the three
  functions is visible to both checks. That includes the time-table
  swap of §4.5, the floor in place of truncation (d), and rounding up
  in (e).
- **Q3.** A byte counter in the rewrite dies under both checks. A byte
  counter in the oracle dies only under `verify_render`, since
  `diff_render` never reads the Python. That is "the voice depends on
  it", run from both sides.
- **The dropped idioms.** Each one taken out of the oracle lives:
  - the sample-table guard;
  - the `values0` guard;
  - the phases kept modulo 256;
  - every `pos < n` guard.
- **What only `diff_render` sees.** Without the zeroing ahead of a
  write, samples 0–2 keep whatever `out` held.
- **Q1 in the voiced length.** Masking the pitch to a byte dies under
  `verify_render`, whose corpus has 3 cases that need the wider pitch
  (§4.3). `diff_render`'s 3,000 cases happen to have none, so there it
  lives.
- **The equivalent edits.** Four live, and the run rechecks that every
  time:
  - The clamp is unreached.
  - The level mask is a no-op.
  - The overflow test `pos >= size` in place of `pos > size` is
    equivalent. Once a write lands at or past the end, the time only
    grows, so nothing is written again. The result is cut at `size`
    either way, and the `last_write` it leaves differs only for writes
    that land nowhere.
  - SAM's restart of the speed counter after an unvoiced sample is a
    no-op. The counter equals `speed` whenever `pos` is new, and it
    starts there. `flags[pos]` cannot change while `pos` does not, so
    an unvoiced sample is always taken at the first step of its frame.

  The first run predicted that both checks would kill the last two, and
  the Q1 mutant. The run showed otherwise, and the three predictions
  were corrected, each with the reason above.

## 4.10 What R.4 did not do

- **No coverage build.** As in R.3, the sorting comes from the
  instrumented oracle over the verifier's corpus (§4.3). The golden
  cases reach none of Q1–Q3. Whether real text does is R.9's question.
- **No speed measurement.** Plan §7 measures at R.9. The direct
  rendering of §4.7 is expected to help, but it was not measured.
- **The size query was not tightened.** It still returns the Python's
  50× reservation, because the API and the addon (`native.py`) depend
  on it. Whether to return less is an R.8 question, for both callers.
- **`native/src` untouched.** One file under `native/` changed:
  `native/tools/verify_render.py`, as the shared verifier (§4.1).
- **The Linux verifiers still wait for R.10.** Linux is checked by
  `test_render`, by `sanitize.py`'s comparison with MSVC, and by the
  four `dump_render` outputs.

## 4.11 Files

New:
- `engine/src/render.c`;
- `engine/tests/test_render.c`;
- `engine/tools/dump_render.c`;
- `engine/tools/reach_render.py`;
- `engine/tools/diff_render.py`;
- `engine/tools/sanitize.py`;
- `engine/tools/mutants/r4.py`;
- this chapter.

Changed:
- `engine/src/quirks.h`: Q3, and the list of dropped idioms.
- `engine/CMakeLists.txt`: `render.c`, `test_render` and
  `dump_render`.
- `native/tools/verify_render.py`: the Python path forced (§4.1), the
  corpus in `fuzz_cases()`, and the closing line names the
  implementation.
- `docs/c17-rewrite-plan.md`: status, the R.4 row, a note on the exit
  count, and the log.
- `docs/c17/00-r0-scaffold.md` and `docs/c-engine-port.md`: a dated note
  on their 485-case claim (§4.1).
- `README.md`: the rewrite's status, which still said "only the
  scaffolding".

Not touched:
- `native/src`, `native/include`;
- the Python;
- the golden vectors;
- `sam-native.zip`;
- the author's uncommitted driver work.

**Known, inferred, guessed.**
- *Known* (run and recorded above):
  - The rewrite equals the Python on 16 golden and 2,898 random cases.
  - It equals `native/` on 20,000 wider cases, and on 5,502 under both
    sanitizers, where it raises nothing.
  - `native/` overflows an `int` on valid input.
  - `verify_render.py`'s fuzz compared the DLL with itself.
  - Proofs (a)–(f).
- *Inferred:*
  - The port's original 485-case run compared with the Python. That
    rests on the commit order, not on a recorded run.
  - The clamp is unreachable from real speech. It was never reached
    (3..252), but not proved.
- *Guessed:* nothing in this stage's results.
