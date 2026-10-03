# 1. Stage R.1 — the renderer tables

Stage R.1 of [the C17 rewrite plan](../c17-rewrite-plan.md), on branch
`c17-r1-tables`. The first engine code: the sixteen tables the renderer
reads, generated from the Python, and the checks that hold them there.

**Result:** `engine/src/tables.[ch]` hold all 16 tables, 2,392 values,
and `verify_tables.py --impl engine` finds every one equal to
`renderer_tables.py`. Both generators, `native/`'s and the engine's, now
have `--check`, and both pass. The engine builds on all four legs with
zero warnings. Its quick tests pass on all four, and `verify_tables`
passes on the two Windows legs, where the verifiers run. The mutation
suite has 16 mutants, and each was killed by exactly the checks
expected.

---

## 1.1 What was done to the tables, and what was not

The tables are SAM's own data, the 6502 original's tables as published
by Macke and Schiffler. Plan §1.2 keeps them: the values, and the
layout as SAM had it, one column per quantity indexed by phoneme. No
table was merged, split or reordered. The renderer stages (R.2–R.4)
read them as `native/` does, so this is the one module the rewrite
changes only in how it is written down.

What is new in `engine/tools/gen_tables.py`, compared with
`native/tools/gen_tables.py`, which it was rewritten from:

- **Each table has a comment** saying what it holds and what indexes it.
  Every comment was checked against the code that reads the table in
  `native/src/sam_frames.c` and `sam_render.c` before it was kept.
  Four first drafts were wrong and were corrected:
  - `sam_stress_pitch` is scaled by inflection / 50, truncated, and
    *then* added to the pitch modulo 256 (`sam_frames.c:151`, `:180`).
    It is not a plain byte added with wrap-around.
  - `sam_time_table` counts in fiftieths of a sample.
    `output_write_array` divides the accumulated position by 50
    (`sam_render.c:35`).
  - `sam_sinus` serves formants 1 and 2 only. Formant 3 is a square
    wave (`sam_render.c:192`, `rp3`).
  - `sam_amplitude_rescale`: "decibels to linear" is the Python's
    phrase, so the comment quotes it as the Python's and does not make
    the claim itself.
- **Every size is a named constant.** `SAM_PHONEME_COUNT` and
  `SAM_SAMPLE_TABLE_SIZE` were already constants in `native/`. Six are
  new: `SAM_SINUS_SIZE`, `SAM_STRESS_LEVELS`, `SAM_AMPLITUDE_LEVELS`,
  `SAM_SAMPLED_CONSONANT_KINDS`, and `SAM_TIME_TABLE_ROWS` and
  `_COLS`. Each is computed from the Python table's length, and the
  generator stops if a table's length does not match its declared
  dimensions.
- **`--check`**: regenerate in memory, compare with the files on disk
  (CRLF read as LF), write nothing, and exit 1 if they differ. CMake
  runs it as the ctest `tables_current`, labelled `quick`. It needs only
  Python, so it runs on all four legs, including Linux.
- **The banner names its origin**: SAM, then Macke and Schiffler, with a
  pointer to `NOTICE.md`.

The names did not change. They are `sam_freq1` … `sam_time_table`, as
in `native/`, so the dump tool prints the names `verify_tables.py`
already keys on. With `C_VISIBILITY_PRESET hidden` they are not exported:
`dumpbin /exports` on the MSVC `sam_render.dll` and `nm -D` on the gcc
`libsam_render.so` each list two functions, `sam_abi_version` and
`sam_text_abi_version`, and nothing else.

`sam_sinus` is still computed by the Python (`int(math.sin(…) * 127)`)
and stored as integers. The engine needs no libm, and does not depend
on any C library's `sin` rounding the way CPython's does.

## 1.2 `native/tools/gen_tables.py --check`

The plan's exit test says "generators run with `--check`", plural. The
frozen engine's generator got the same switch: it was additive, and
`native/src` was not touched (plan §2, `native/README.md`). It
reports `native/src/sam_tables.[ch] current`.

**A slip on the way, caught and undone.** The first attempt at this
edit failed to apply: Git Bash's heredoc ate the backslashes in the
edit script, as in R.0. The check was then run against the *unedited*
generator, which ignores unknown arguments, so it regenerated
`native/src/sam_tables.[ch]` instead of checking them. `git diff
--ignore-cr-at-eol` showed no content change, only LF in place of the
checkout's CRLF. Both files were restored with `git checkout`, and the
edit was made with the editor tool instead. `native/src` is unchanged
in this stage's commit.

## 1.3 The dump tool

`engine/tools/dump_tables.c` prints the same lines as
`native/tools/dump_tables.c`. It differs in two ways:

- The length of each table comes from its declared type
  (`sizeof t / sizeof t[0]`), not from a hand-written count.
- `sam_time_table` is printed row by row. Reading all 25 values through
  a pointer to `sam_time_table[0][0]` would index past the first row,
  which strict C does not allow.

It is a CMake target in a `foreach` over dump tools. Later stages add
their own tools to that list, and each lands at the top of the build
tree, where `_build.py` looks for it.

## 1.4 The four legs

`python engine/tools/build_matrix.py`, 2026-10-03:

```
leg        build    tests              notes
msvc       ok       3/9 (6 skipped)    0 warnings
clang-cl   ok       3/9 (6 skipped)    0 warnings
wsl-gcc    ok       2/2                0 warnings
wsl-clang  ok       2/2                0 warnings
```

On Windows the three that pass are `abi`, `tables_current` and
`verify_tables`. The six skips are the verifiers of R.2–R.7. On Linux
the two are `abi` and `tables_current`.

Separately, `verify_tables.py --impl engine` and `--impl native` each
print `all 16 tables match, 2392 values verified`.

## 1.5 The mutation suite

`engine/tools/mutate.py` is the driver every stage from here on shares.
`engine/tools/mutants/r1.py` is this stage's list. The mutants are
klattsch's kind: literal find-and-replace, one edit each. klattsch edits
its tree in place and restores it afterwards. This driver works on a
copy instead, so an interrupted run cannot leave a mutant behind:

1. It copies `engine/`, `native/` and `nvda-addon/` to a scratch
   directory, leaving out build trees and binaries.
2. It builds the copy once with MSVC and Ninja.
3. It requires every check to pass on the unmutated copy.
4. For each mutant, it applies the edit, rebuilds, runs every check,
   and restores the file.

Each mutant names the checks that must kill it, and the result has to
match exactly. An anchor that is not found exactly once, a mutant that
does not build, and a check that skips are all errors. The working tree
is never written.

R.1's two checks see different things. `verify_tables` sees the compiled
values. `tables_current` sees the generated text. So the suite includes
mutants that only one of them can catch:

```
mutant                                              verify_tables  tables_current
freq1[0] 0 -> 1                                     killed         killed          ok
ampl3[79] 16 -> 17 (last entry)                     killed         killed          ok
out_blend_length[79] 160 -> 161 (last entry)        killed         killed          ok
sample_table[1279] 252 -> 253 (last byte)           killed         killed          ok
sinus[1] 3 -> 4                                     killed         killed          ok
sinus[255] -3 -> 3 (sign)                           killed         killed          ok
stress_pitch[1] 224 -> 225                          killed         killed          ok
amplitude_rescale[15] 15 -> 14                      killed         killed          ok
sampled_consonant_values0[0] 24 -> 25               killed         killed          ok
time_table[4][4] 54 -> 55 (last cell)               killed         killed          ok
Python STRESS_PITCH_TABLE changed, not regenerated  killed         killed          ok
tables.h comment edited by hand                     lived          killed          ok
dump prints freq2 under the name freq1              killed         lived           ok
dump prints sinus as unsigned                       killed         lived           ok
dump drops the last time_table row                  killed         lived           ok
dump omits a table                                  killed         lived           ok

16 mutants, 16 as expected, 0 not
```

The run took 18 seconds. The last entry of a table and the last byte
of the sample table are there deliberately, because an off-by-one in a
dump loop would miss them. The "Python changed" mutant edits the
copy's `renderer_tables.py`, so the oracle itself is never touched.

## 1.6 What R.1 did not do

- **`gen_frontend_tables.py` has no `--check` yet.** It generates the
  parser and reciter tables, and the rewrite's version of it belongs to
  R.5 and R.6.
- **No sanitizer or coverage run.** Tables are data. The plan puts
  sanitizers at R.4 and R.7, and coverage with the quirks.
- **The mutation suite runs on MSVC only.** It is the same source on
  every leg, and the checks run from Windows until R.10.

## 1.7 Files

New:
- `engine/src/tables.c`, `engine/src/tables.h` (generated);
- `engine/tools/gen_tables.py`;
- `engine/tools/dump_tables.c`;
- `engine/tools/mutate.py`;
- `engine/tools/mutants/r1.py`;
- this chapter.

Changed:
- `engine/CMakeLists.txt`: `tables.c` added to the library, the
  dump-tool target, and the `tables_current` test;
- `native/tools/gen_tables.py`: `--check` added.

Not touched:
- `native/src`;
- the Python;
- the golden vectors;
- `sam-native.zip`;
- the author's uncommitted driver work.

**Known, inferred, guessed.**
- *Known:* every table and result line above was printed by the command
  named with it, on 2026-10-03. Every table comment was checked against
  the `native/src` line cited for it.
- *Inferred:* that the column layout is the original's. Macke's C and
  Schiffler's JavaScript both have it, and the 6502 source was not
  consulted.
- *Guessed:* nothing.
