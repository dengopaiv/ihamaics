# 2. Stage R.2 — the voice

Stage R.2 of [the C17 rewrite plan](../c17-rewrite-plan.md), on branch
`c17-r2-voice`. The engine gets a voice: SAM's mouth and throat settings,
applied to the formant table.

**Result:** `engine/src/voice.[ch]` reproduce `set_mouth_throat()`.
`verify_frames.py --impl engine` finds all 65,536 (mouth, throat) pairs
equal to the Python, on both Windows legs. The four legs build with zero
warnings, and their `dump_frames` output is identical. One idiom of
`native/` was sorted into "no input reaches it" and dropped: the formant
rows are bytes again, and a `_Static_assert` holds the bound that makes
that exact. The mutation suite has 19 mutants, and each one did exactly
what was expected. Two of them are equivalent mutants that should live,
and did.

---

## 2.1 What the function does

`set_mouth_throat(mouth, throat)` (`renderer.py:74`) starts from the
three formant columns of `FREQUENCY_DATA`. For phonemes 5..29 (IY … NX:
vowels and sonorants) and 48..53 (EY … UW: diphthongs) it replaces

- F1 by `((mouth * F1) >> 8 & 0xFF) << 1`, and
- F2 by `((throat * F2) >> 8 & 0xFF) << 1`.

That is the table value times factor / 128, rounded down to an even
number. F3 and every other phoneme keep their table values. Both ranges
and the arithmetic are SAM's (plan §1.2) and stay as they are. In
`voice.c` the ranges are named constants (`VOICED_FIRST` …
`DIPHTHONG_END`), and the loop body is written once and called for each
range.

`native/src/sam_frames.c:20–52` is the C this was rewritten from. In the
plan's layout (§3.2) the function gets its own module, `voice.c`.
`frames.c` (R.3) is its only caller.

## 2.2 The idiom sorted: `uint16_t` formant rows

`native/` holds the result in `uint16_t` (`sam_internal.h`,
`sam_freqdata_t`). Its comment gives the reason: the transform "can
reach 510", and matching Python's unbounded integers "is cheaper than
proving a bound". This is the first row of the plan's §1.1 table, as far
as it concerns this function. Plan §1.2 asks which bin it goes in.

**No input reaches it.** It was established three ways:

1. **Algebra.** `mouth`, `throat` and every table value are bytes. So
   `factor * f <= 255 * 255`, and `>> 8` alone leaves at most 254. The
   Python's `& 0xFF` cannot change a value. Doubling stays within a byte
   exactly when `(255 * f) >> 8 <= 127`, that is, when `f <= 128`.
2. **Measurement of the tables.** The largest value in all three
   formant columns is 127, for UL and UM, which are not scaled. Within
   the scaled ranges, the largest F1 is 27 and the largest F2 is 86
   (NX).
3. **Measurement of the output.** Running the Python over all 65,536
   (mouth, throat) pairs, the largest value produced in any row is 170.
   That is F2 of NX at throat 254 or 255.

The facts in 2 and 3 were printed by a one-off script over
`renderer.set_mouth_throat` and `renderer_tables.FREQUENCY_DATA`, run
on 2026-10-03. The script is not kept, because the next paragraph turns
its conclusion into a check that runs on every build.

So the rewrite's `sam_freqdata_t` (`voice.h`) has `uint8_t` rows, and the
transform is written as `((factor * f) >> 8) << 1` with no mask. The
bound it relies on is stated, as §1.2 asks:

- `gen_tables.py` now writes `SAM_FREQ_MAX`, the largest value in
  `sam_freq1..3`, into `tables.h`. It is 127.
- `voice.c` asserts at compile time that
  `((255 * SAM_FREQ_MAX) >> 8) << 1 <= UINT8_MAX`.

If the tables ever hold a frequency above 128, the build stops. Then
"no input reaches it" would no longer be true, and the idiom would have
to come back. A table edited by hand without regenerating is caught by
`tables_current` and `verify_frames` instead (§2.5).

**Nothing went to `quirks.h`.** Nothing in this function is a quirk the
voice depends on. The mask is a no-op and the widening is unreachable.
§2.5 shows both claims holding in the mutation suite.

## 2.3 The dump tool

`engine/tools/dump_frames.c` prints the same 65,536 lines as
`native/tools/dump_frames.c`: `mouth throat checksum`. The checksum is
the same FNV-1a, over each value as two little-endian bytes, because
that is how `verify_frames.py` hashes the Python's rows. The engine's
values are bytes, so the dump hashes a high byte of 0 for each one,
explicitly, with a comment saying why. `verify_frames.py` itself is
unchanged.

The tool is added to the dump-tool `foreach` in `engine/CMakeLists.txt`.
The `verify_frames` ctest, registered since R.0, therefore turns from
skipped to run.

## 2.4 The four legs

`python engine/tools/build_matrix.py`, 2026-10-03:

```
leg        build    tests              notes
msvc       ok       4/9 (5 skipped)    0 warnings
clang-cl   ok       4/9 (5 skipped)    0 warnings
wsl-gcc    ok       2/2                0 warnings
wsl-clang  ok       2/2                0 warnings
```

On Windows the four that pass are `abi`, `tables_current`,
`verify_tables` and `verify_frames`. The five skips are R.3–R.7.

The verifiers do not run on Linux yet (R.10). As a stand-in, the
`dump_frames` output of all four legs was hashed: the two Windows legs
with CR removed, the two WSL legs from their build trees.
All four gave MD5 `64db3f9b8164adad670747eaa2b4df75`. So gcc and clang
on Linux compute the same 65,536 checksums that `verify_frames` accepts
on Windows.

Also run separately: `verify_frames.py --impl engine` against each
Windows build tree, and `--impl native`. All three print
`sam_set_mouth_throat matches Python for all 65536 (mouth, throat)
combinations`.

`dumpbin /exports` on the MSVC DLL and `nm -D --defined-only` on the gcc
`.so` still list exactly two functions: `sam_abi_version` and
`sam_text_abi_version`. `sam_set_mouth_throat` is internal.

## 2.5 The mutation suite

`engine/tools/mutants/r2.py`. Two checks: `verify_frames`, and
`tables_current`, because `SAM_FREQ_MAX` lives in a generated header.
This stage needs one addition to the driver. A mutant may name `build`
as its killer, which means the edit must not compile. That is how the
`_Static_assert` is tested: a mutant that only "does not build" was an
error in R.1's driver, because a checker that cannot run proves nothing.
Now it is accepted only when the mutant expects exactly that.

```
mutant                                              verify_frames  tables_current
first voiced phoneme 5 -> 4                         killed         lived           ok
voiced range ends at 29, not 30                     killed         lived           ok
first diphthong 48 -> 49                            killed         lived           ok
first diphthong 48 -> 47 (equivalent: ** is all 0)  lived          lived           ok
diphthong range ends at 55, not 54                  killed         lived           ok
diphthongs not scaled at all                        killed         lived           ok
scale not doubled                                   killed         lived           ok
scale shifts by 7, not 8 (wraps in a byte)          killed         lived           ok
mouth and throat swapped                            killed         lived           ok
formant 3 scaled by mouth too                       killed         lived           ok
formant 3 copied from sam_freq2                     killed         lived           ok
tables.c: NX F2 86 -> 200 by hand                   killed         killed          ok
Python: NX F2 86 -> 87, not regenerated             killed         killed          ok
SAM_FREQ_MAX 127 -> 129                             refused by the compiler  ok
SAM_FREQ_MAX 127 -> 128 (still fits)                lived          killed          ok
Python trans() without & 0xFF (equivalent)          lived          lived           ok
dump hashes the high byte as 1                      killed         lived           ok
dump stops at throat 254                            killed         lived           ok
dump skips formant 3                                killed         lived           ok

19 mutants, 19 as expected, 0 not
```

What the rows show:

- **Every range end, both ways where it matters.** A first attempt had
  `first diphthong 48 -> 47` expected to die, and it lived. Phoneme 47
  is `**`, and all three of its frequencies are 0. Scaling 0 gives 0, so
  a range starting at 47 is the same function for every voice. It is
  kept in the list as an equivalent mutant (expected to live), and
  `48 -> 49` was added as the boundary a check can see. The other three
  ends are visible because their outside neighbours have nonzero
  frequencies: phoneme 4 (`-*`, F1 19), 30 (`DX`, F1 6, F2 54) and 54
  (`B*`, F1 6, F2 26).
- **The bound.** `SAM_FREQ_MAX` 127 → 129 is refused by the compiler.
  127 → 128 still fits, so it compiles and gives the same voice. Only
  `tables_current` sees it, as stale generated text.
- **The dropped mask.** Removing `& 0xFF` from the Python oracle (in the
  scratch copy) changes no output, so the mutant lives. That is §2.2's
  claim, run.
- **The tables underneath.** A hand edit of NX's F2 in `tables.c`, and a
  Python table change without regenerating, are each caught by both
  checks.
- **The dump tool lying.** A wrong high byte, a short loop, or a missing
  row: each is caught by `verify_frames` alone.

`python engine/tools/mutate.py r1` was run again after this stage
changed `gen_tables.py` and `tables.h`. Its first run reported 15 of 16:
`freq1[0] 0 -> 1` "did not build", the first mutant built in that
run. Run alone, it built and was killed by both checks. The whole
suite was then run three more times, and each run reported
`16 mutants, 16 as expected, 0 not`. The failed build was not
reproduced, and its log was not kept, because the driver discarded
it. The driver now puts the first error line of a failed build into
the table, so the next one will say why. The cause is not known. A
transient file lock on the freshly linked tool is a guess, not a
finding.

## 2.6 What R.2 did not do

- **No `quirks.h` yet.** The first quirk that stays is expected in R.3
  (negative frame indices, `int(change / width)`).
- **`native/` untouched.** Its `uint16_t` rows stay as the frozen
  reference. Its own `verify_frames.py --impl native` still passes.
- **No sanitizers.** They come at R.4 and R.7, per the plan. This stage
  has no pointer arithmetic beyond fixed-size arrays.

## 2.7 Files

New:
- `engine/src/voice.c`, `engine/src/voice.h`;
- `engine/tools/dump_frames.c`;
- `engine/tools/mutants/r2.py`;
- this chapter.

Changed:
- `engine/tools/gen_tables.py`: writes `SAM_FREQ_MAX`;
- `engine/src/tables.h`: regenerated, with that one constant added;
- `engine/CMakeLists.txt`: `voice.c` added to the library, and
  `dump_frames` added to the tools;
- `engine/tools/mutate.py`: `killed_by=('build',)`, and the first error
  line of a build that fails unexpectedly.

Not touched:
- `native/`;
- the Python;
- the golden vectors;
- `sam-native.zip`;
- the author's uncommitted driver work.

**Known, inferred, guessed.**
- *Known:* every number above was printed by the command named with it,
  on 2026-10-03. The bound is algebra plus a compile-time check, and the
  exhaustive measurement agrees with it.
- *Inferred:* that the 6502 original computes this in bytes too, which
  would make the byte rows the original's shape as well as an exact
  one. The doubling suggests it (an `ASL` of the multiply's high byte),
  but the 6502 source was not consulted.
- *Guessed:* the cause of the one transient build failure in the R.1
  suite rerun (§2.5).
