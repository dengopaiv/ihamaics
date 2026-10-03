# The C17 rewrite of SAM: plan

Written 2026-10-03, before any of it is done. Nothing below is a finding
about the rewrite; it is the baseline later work is measured against.
When something here turns out wrong, it is corrected in place with a dated
note (*Overtaken 2026-…, §…*), not rewritten silently.

**Status: stage R.0 done and merged (2026-10-03). R.1 is next.**

| Step | State | Logged in | Open |
|---|---|---|---|
| Survey of the other rewrites in this tree | done 2026-10-03 | §11 | — |
| Decisions for the author | D1–D5 decided 2026-10-03 | §9 | — |
| R.0 scaffold and freeze | done 2026-10-03 | [docs/c17/00](c17/00-r0-scaffold.md) | — |
| R.1 onward | not started | — | — |

---

## 1. Why, and what "rewrite" means here

The author's house rule (decided 2026-09-24): every synthesizer worked
on here is eventually rewritten in C17, builds on Windows and on
Unix-likes, and ships no data files it could compile in. SAM is a port
of reverse engineering that was already public: s-macke's C, then
discordier's JavaScript, then our Python, then our C. The rewrite stays
public, like `ihamaics` itself.

**The current C is already C17-clean.** This was measured before anything
else (2026-10-03, WSL Debian), with every file in `native/src` compiled
`-fsyntax-only`:

| Compiler | `-std=c17 -pedantic -Wall -Wextra` | plus `-Wshadow -Wconversion` |
|---|---|---|
| gcc 14.2.0 | 0 warnings | 2 (`-Wsign-conversion`) |
| clang 19.1.7 | 0 warnings | 2 (`-Wsign-conversion`) |

So the rewrite is not about the language standard. Moving the port to
`/std:c17` would be a flag. What a rewrite would buy is a change of
shape: the port's shape is the shape of what it was *checked against*,
not the shape of the engine.

### 1.1 What makes the port read like Python

`native/` was written to agree with `renderer.py`, `parser.py` and
`reciter.py` byte for byte, and they in turn transliterate
JavaScript. Matching them forced idioms that belong to Python, not
to SAM:

| Idiom in `native/src` | Where | What it imitates |
|---|---|---|
| `int` rows where SAM had bytes ("unbounded integers") | `sam_internal.h` (`sam_frames_t`, `sam_freqdata_t`), `sam_frontend.h` (`sam_plist_t`) | Python's unbounded `int` |
| `SAM_NO_PHONEME (-1)` sentinel, distinct from phoneme 0 | `sam_frontend.h`, `sam_parser.c` | `None` from `get_phoneme()` past either end |
| `py_set()` writing through index −1 to the last element | `sam_parser.c:137–190`, `:525` | `row[-1] = value` |
| `kind == -1` selecting the last of `SAMPLED_CONSONANT_VALUES0` | `sam_render.c:108–118` | negative indexing |
| negative frame index wrapping | `sam_frames.c:238–246`, `:362–366` | negative indexing |
| `int(change / width)` truncation | `sam_frames.c:210` | true division, then `int()` |
| silent return on output overflow | `sam_render.c` `output_write_array` | where Python raises `RuntimeError` |
| slice clamping, `str.strip()` set, regex `-?\d+\.?\d*` | `sam_reciter.c`, `sam_text.c` | Python string semantics |
| three parallel lists in place of one record | `sam_parser.c` | closures over three lists |

### 1.2 What is SAM's own behaviour and stays

The original runs on a 6502. Its arithmetic is eight-bit, and the
`& 0xFF` masks, the wrapping phase accumulators, the 256-entry tables and
the timetable are the engine itself. Those stay, written as the byte
arithmetic they are.

So every idiom in §1.1 has to be sorted into one of two bins, and each
sorting is recorded with how it was established:

- **The voice depends on it.** Some input in the verified domain reaches
  it and changes the output. Then it stays, as a named function or
  constant next to the code it belongs to, with a comment saying which
  Python line it reproduces. A quirk that is reachable is part of this
  voice, whatever its origin.
- **No input reaches it.** Coverage over the whole verified domain (§5)
  shows it is never taken. Then it goes, and the rewrite states the bound
  it relies on with a `_Static_assert` or an `assert`, plus the test that
  measured it. Example: pitches were measured from −194 to 366
  (`sam_internal.h`), so `int16_t` is provably enough and `uint8_t` is not.

What we do not do is "fix" anything during the rewrite. The three quirks
in `native-gui.md` (two spaces between words, the 16 unspeakable
dictionary words, `parse(".")` writing through −1) are reproduced.
Fixing them is a decision about the voice, made separately, opt-in and
logged (§8).

### 1.3 What the rewrite also fixes that is not code

The present tree breaks two house rules. Neither needs a rewrite to fix,
and both should be fixed whether or not the rewrite goes ahead:

- **32-bit builds.** `native/build.cmd` builds `sam_render-x86.dll`,
  `gui-native/build.cmd` takes `x86`, `sam-native.zip` ships
  `sam_gui-x86.exe`, and `docs/c-engine-port.md` still says "ship both"
  (the house rule: no 32-bit build of anything). *Decided
  2026-10-03 (D3):* the releases already made keep their 32-bit builds.
  No new release has one, and the rewrite has no 32-bit target at all.
- **NVDA version.** `nvda-addon/manifest.ini` says
  `minimumNVDAVersion = 2023.1.0`, and so does the README. *Decided
  2026-10-03 (D3):* it is raised to 2026.1, for 64-bit NVDA only.

And one portability gap: the dictionary reaches the engine as a Windows
`RCDATA` resource in the GUI (§6).

---

## 2. What does not change

- **The Python is the oracle.** `nvda-addon/synthDrivers/sam/*.py` stays
  what every result is checked against, as it is for `native/` today.
- **`native/` is frozen** as the second reference: the verified,
  measured C port. A bug found in it is fixed in it and in the rewrite,
  and the golden vectors are regenerated only if the Python changed on
  purpose. Once the rewrite replaces it, it moves to a branch of its own
  (§3.1), where it stays buildable.
- **The public API.** `sam_render.h` (ABI 1) and `sam_text.h` (text
  ABI 1) are kept as they are, names, structs and error codes. The
  addon's `native.py`, the native GUI and every `verify_*.py` then run
  against the rewrite unchanged. `sizeof(sam_phoneme_t) == 3` and
  `sizeof(sam_voice_t) == 12` become `_Static_assert`s.
- **The output.** Byte for byte. SAM is integer arithmetic throughout,
  so there is no tolerance tier as klattsch needed for libm.
- **Attribution.** Every rewritten file names the file it was rewritten
  from, and `NOTICE.md` gains a line for the rewrite. A rewrite of
  s-macke's and Schiffler's work is still theirs.

---

## 3. Shape

### 3.1 Where it lives

*Decided 2026-10-03 (D1, D2):* in this repository. While the work is
under way, the rewrite is a new top-level `engine/`, with `native/`
frozen beside it. When it is finished, the old engine goes onto a branch
of its own and the rewrite is what `master` carries.

Everything SAM is checked against is in this repository, so the
rewrite needs no repository of its own.

**What the switch needs.** Three things live inside `native/` but serve
both engines. They have to move out before `native/` leaves `master`:

- the verifiers, generators and dump tools (`native/tools/`);
- the golden vectors (`native/tests/golden/`);
- the dictionary generator, `gen_dict.py`.

The verifiers go to the top-level `tools/` and the vectors to `tests/`.
Both stay on `master`, together with the Python they check against.
The packaging also reads from `native/build`: `package_addon.py` at line
37 and `make_release.py` at line 50, along with the commands they print.
Both are repointed at the CMake build. The order is fixed in stage R.11.

### 3.2 Modules, by function

```
engine/
  CMakeLists.txt
  include/sam_render.h      unchanged copy of native/include
  include/sam_text.h        unchanged copy
  src/tables.c   .h         renderer tables, generated (tools/gen_tables.py)
  src/voice.c    .h         set_mouth_throat: the formant table for a voice
  src/frames.c   .h         create_frames, create_transitions, prepare_frames
  src/render.c   .h         process_frames, sampled consonants, the output timetable
  src/phoneme.c  .h         the phoneme record, flags and lengths (parser tables)
  src/parser.c   .h         phoneme string to [phoneme, length, stress]
  src/reciter.c  .h         English rules, generated rule tables
  src/numbers.c  .h         numbers to words
  src/dict.c     .h         the CMU lookup and ARPABET to SAM
  src/text.c                the pipeline: text, phonemes, audio
  src/quirks.h              every reproduced Python idiom, named, in one place
  tools/                    dump tools, one per boundary (§5)
  cli/samsay.c              text or phonemes to WAV, the Unix entry point
```

`quirks.h` is a deliberate break from "next to the code it belongs to".
SAM's quirks are few and all have the same cause (one reference
language's semantics). Gathering them gives one list to read when D5 is
decided. Each one still carries a comment at its call site.

### 3.3 Build

From the start, not at the end (klattsch's rule):

- CMake ≥ 3.16. Version read from the public header, one constant.
- `CMAKE_C_STANDARD 17`, `CMAKE_C_STANDARD_REQUIRED ON`,
  `CMAKE_C_EXTENSIONS OFF`. Write C17 that is also valid C23.
- `if(CMAKE_SIZEOF_VOID_P EQUAL 4) message(FATAL_ERROR …)`. x64 and ARM64.
- MSVC `/W4`; others `-Wall -Wextra -Wpedantic -Wshadow -Wconversion`.
  Warning-free on every leg is part of each exit test.
- One static and one shared library from one source list,
  `C_VISIBILITY_PRESET hidden`, plus `samsay`.
- ctest, with labels `quick` (tables current, goldens untouched) and
  `validation` (the differential tests).
  `SKIP_RETURN_CODE 77` when Python is missing.

Use of C11/C17: `_Static_assert`, `static inline`, `<stdbool.h>`,
`<stdint.h>`. Not used: VLAs (MSVC has none), `<threads.h>`,
`_Generic`, atomics (the API is stateless and needs none).

### 3.4 Toolchains

Available on this machine, checked 2026-10-03:

| Leg | Where |
|---|---|
| MSVC 19.51 (VS 18 Community, toolset 14.51) | Windows |
| clang-cl (VS 18's bundled LLVM) | Windows |
| gcc 14.2.0 | WSL Debian |
| clang 19.1.7 | WSL Debian |

cmake 3.31 and ninja are on both sides. klattsch found that MSVC
under `/std:c17` accepts binary literals and digit separators, so MSVC
alone does not prove the code is C17. That is why every stage is built
on all four legs, from R.1.

---

## 4. Stages

Back to front, as `native/` was built: the renderer first, because it
has the strongest oracle, then the front end. Every stage is checked
against something that already works. One branch per stage
(`c17-r1-tables`, …); `master` gets only verified stages. One chapter per
stage in `docs/c17/`, written as it happens.

| # | Stage | Exit test |
|---|---|---|
| R.0 | Scaffold and freeze | see below |
| R.1 | Tables | all 2,392 table values identical (`verify_tables.py`); generators run with `--check` |
| R.2 | Voice | all 65,536 (mouth, throat) pairs (`verify_frames.py`) |
| R.3 | Frames | `verify_frames.py`, `verify_prepare.py 3000` (3,000 randomised cases, all 8 rows; the default is 400, see docs/c17/00 §0.1) |
| R.4 | Renderer | 16 golden vectors byte for byte (`check_golden.py`, `verify_render.py`), and `verify_render.py`'s randomised fuzz against the Python with a count at least the 485 the port passed |
| R.5 | Parser | `verify_parser.py` over the whole dictionary |
| R.6 | Reciter and numbers | `verify_reciter.py`; `verify_text.py`'s `expand_numbers` part |
| R.7 | Pipeline | `verify_text.py`, 144,272 cases, with and without the dictionary. The dictionary is read from today's `sam.dict` blob, format unchanged (§6) |
| R.8 | API and swap-in | the addon packaged against `engine/` (`validate_addon.py`); `verify_gui.py`, `verify_gui_presets.py`, `verify_gui_keyboard.py` on the GUI built against it |
| R.9 | Measure | §7 |
| R.10 | Unix and CI | `samsay` on Linux reproduces the golden vectors; GitHub Actions runs the gcc leg |
| R.11 | Switch | the shared tools and vectors moved out of `native/` (§3.1) and every verifier passes from their new place; `native/` on its own branch and still building there; packaging repointed; `make_release.py` produces an archive whose engine is `engine/` |
| R.12 | Dictionary | §6: measured and decided; the silent words fixed (§6.1); `verify_text.py` passes, with only the fixed words changed, and those listed |
| R.13 | GUI connector | waits for the connector header to exist (§10) |

**R.0** produces no engine code:

- `engine/` with `CMakeLists.txt`, the two headers copied unchanged, and
  an empty library that builds on all four legs.
- The verifiers learn which implementation to check: a
  `--impl native|engine` switch, defaulting to `native`. This touches
  more than `_build.py`. `verify_tables.py`, `verify_frames.py` and
  `verify_gui*.py` carry their own copy of the MSVC lookup.
  `verify_render.py` loads the DLL from `native/build` through ctypes.
  The lookups are folded into `_build.py` first, without changing behaviour,
  then the switch is added. This is the only edit to `native/`, and it
  is additive.
- The baseline in §7, measured on `native/`.
- `native/README` or a header line in each `native/src` file saying
  "frozen reference; the rewrite is `engine/`, see docs/c17-rewrite-plan.md".
- The NVDA minimum raised to 2026.1 in `manifest.ini` and the README,
  and the x86 targets taken out of the build scripts for the next
  release (§1.3, D3). Earlier releases are left as they are.

Each stage after R.0 also gets a **mutation suite**, as klattsch has.
It is a list of single find-and-replace edits to the rewrite, and the
stage's verifier must fail on every one. A list entry the verifier
cannot reach is kept and marked, so the claim is rechecked every run.
A verifier that cannot fail proves nothing.

---

## 5. Verification

The differential tests already exist and are domain-wide, which makes
this rewrite cheaper than most. Nothing has to be captured; the oracle is Python, and it runs on every machine here.

- **Same tests, other sources.** The `verify_*.py` scripts compile a dump
  tool from `native/tools/dump_*.c` against a source list. The rewrite
  gets its own dump tools in `engine/tools/`, built against its own
  internal headers. Each dump tool writes **the same output format** as
  its `native/` counterpart, so one Python verifier checks both.
- **One process per implementation.** `native/` and `engine/` export the
  same `sam_*` names, so they are never linked together. Where a direct
  C-to-C comparison helps (speed, fuzzing past what Python can do in
  reasonable time), two dump processes are diffed.
- **Coverage, to sort the quirks.** A gcc `--coverage` build of the
  rewrite run over the full R.5–R.7 corpus. Every line in `quirks.h` is
  listed as taken or not taken, and that list is what §1.2's sorting
  cites.
- **Sanitizers.** `-fsanitize=address,undefined` on the gcc and clang
  legs, clean over the whole corpus, as part of R.4 and R.7.
- **Unix leg checked from Windows.** The WSL build writes its dumps to a
  directory and the Python verifiers read them. klattsch does this, and
  it means Linux needs no copy of the Python reference.

---

## 6. The dictionary

Today: `gen_dict.py` writes `native/data/sam.dict` (sorted words, offset
table, about 3.3 MB of strings for 126k entries). The engine takes
`(dict, dict_len)` and borrows it. The GUI links it as `RCDATA`, which
is a Windows-only mechanism. The addon does not use it; it keeps the
Python dictionary.

*Decided 2026-10-03 (D4):* the dictionary comes after the synthesizer
is done. Until R.12, the rewrite reads the blob exactly as `native/`
does: same format, same `gen_dict.py`, same lookup behaviour. Only the
code is rewritten. That keeps R.7's check a plain comparison with the
Python.

The house target is no runtime data. Three ways there, to be measured
in R.12:

1. **A byte array in generated C.** Straightforward and portable.
   `gen_dict.py` estimated tens of MB of source and a minute of compile
   time. That estimate is to be measured, not repeated.
2. **A compact encoding, then a byte array.** The words are sorted, so
   front coding (shared prefix length plus suffix) shrinks them a lot.
   Pronunciations are drawn from 39 ARPABET symbols plus stress, so
   they fit in one byte per phoneme. The generated source may come down
   to something an ordinary compile handles. This changes the lookup
   code, so the old blob format stays available.
3. **Keep the blob, optional.** `#embed` would solve this, but it is
   C23 and MSVC does not have it (klattsch measured, 2026-09-23).

Whatever is chosen, `(dict, dict_len)` stays in the API. `dict == NULL`
still selects the rules-only path, and a compiled-in dictionary is one
more way to pass a non-NULL pointer.


### 6.1 The silent words (D5)

*Decided 2026-10-03:* fixed, in R.12, after the synthesizer is done.

**The cause.** Twenty-two lines of `cmudict.txt` end in a comment, such as
`aalborg AO1 L B AO0 R G # place, danish`. `cmudict.py` splits each line
on whitespace and keeps everything after the word as phonemes, so `#`,
`place,` and `danish` are stored as phonemes too. The parser cannot read
the result, and the whole utterance comes out with no audio. Sixteen
words are affected: the other six commented lines are `(2)` variants,
and the first pronunciation wins. Among the sixteen are everyday
abbreviations: in the Python, `hiv` gives `EY4CHAY4VIY4#abbrev` and `gdp`
gives `GIY4DIY4PIY4#abbrev`. `fine(2)` carries a comment too, but
`fine` gives `FAY4N` and is unaffected. Checked 2026-10-03 with the
Python's `text_to_phonemes`.

**The fix.** Drop everything from `#` onward when the dictionary is
read. It goes into the Python (`cmudict.py`), into `gen_dict.py`, and
into the rewrite, in one change. The Python is the oracle, so the oracle
is fixed with it; a fix in the C alone would show up as a mismatch. It
is not behind a flag: what changes is silence becoming speech, and no
other word moves.

**What has to change with it.** `gen_dict.py`'s docstring describes the
sixteen. `verify_gui.py` asserts that both implementations refuse
together. `native-gui.md` describes the bug as open. The exit test is
`verify_text.py` with exactly those sixteen words changed. `native/`,
frozen on its branch by then, is not changed.
---

## 7. Measurements

Taken on one named machine, before (R.0, on `native/`) and after (R.9,
on `engine/`). Any speed or size claim about the rewrite cites this
table and nothing else:

- render time and real-time factor of the 20-word sentence from
  `c-engine-port.md`, direct call and through ctypes;
- the latency table (`"a"`, `"the"`, `"comfortable"` at speeds 15, 72
  and 150) and the worst case, `"incomprehensibility"` at speed 150;
- DLL size, GUI size, and `samsay` size;
- compile time of the dictionary, for each option in §6 (in R.12, not R.9).

The known starting point is `c-engine-port.md`: 17.2 ms for the
sentence through ctypes, real-time factor 0.0021. The rewrite is not
expected to be faster, and that is not its purpose. Narrower types
(§1.2) might help a little. The table will say.

---

## 8. Decisions made in advance

- **Fidelity is the default.** Byte-identical to the Python over every
  domain the verifiers cover, or it is a bug in the rewrite.
- **No fixes during the rewrite.** A quirk that is part of the voice is
  reproduced. A fix comes after, is logged, and is made only if the
  author asks for it. A fix that changes how something sounds is off by
  default. The one fix decided so far, the silent words (D5, §6.1), is
  on by default, because it turns silence into speech and leaves every
  other word as it was.
- **Generated tables are generated.** No table is typed, in either
  direction.
- **The reference is frozen.** `native/` and the Python move only for a
  bug fixed in both, with the golden vectors regenerated and the reason
  logged.
- **Measure before claiming.** §7, both sides, same machine.
- **NVDA is started only by the author**, and the GUI is not finished
  until the author has driven it with NVDA from the keyboard.

---

## 9. Open decisions for the author

| # | Question | Answer |
|---|---|---|
| D1 | `engine/` in `ihamaics`, or a separate repository? | **Decided 2026-10-03:** in `ihamaics`. |
| D2 | What becomes of `native/` when the rewrite is done? | **Decided 2026-10-03:** it goes to a branch of its own, and the rewrite becomes what `master` carries (§3.1, R.11). The Python stays the oracle on `master`. |
| D3 | 32-bit builds and the NVDA minimum? | **Decided 2026-10-03:** the 32-bit builds stay in the releases already made, and no new release has one. The NVDA minimum is raised to 2026.1. |
| D4 | The dictionary: compile it in, or keep the blob? | **Decided 2026-10-03:** after the synthesizer is done (R.12). Until then the blob is read unchanged. |
| D5 | Fix any of the three known quirks afterwards (two spaces, 16 silent words, `parse(".")`)? | **Decided 2026-10-03:** the 16 silent words are fixed, after the rewrite, in R.12 (§6.1). The other two stay as part of the voice. |

---

## 10. A GUI connector

The author plans a shared, accessible front end that would serve as
every engine's GUI, through a C17 header implemented in each engine's
repository. That header does not exist yet. R.13 starts when it does.

What SAM brings to any such interface, so the rewrite does not paint
itself into a corner:

- **Output format.** SAM renders 8-bit unsigned PCM at 22,050 Hz. A
  connector that needs signed 16-bit converts (`(s - 128) << 8`); the
  engine's API does not change.
- **Streaming.** `sam_render` renders an utterance at once. A connector
  that pulls audio in pieces can render a sentence and serve it from a
  buffer at first. A real streaming renderer is a later change, and it
  would need its own exit test: concatenated output identical to the
  one-shot output.
- **Parameters.** Speed, pitch, mouth, throat, inflection and sing mode,
  plus the six presets from the manual as voices.
- **Phoneme input and timing.** `sam_speak_phonemes` takes phonemes
  directly. SAM's phoneme triples carry lengths and the renderer has a
  pitch per frame, so per-phoneme durations and a pitch contour are both
  reachable, which matters for singing.

---

## 11. Log

**2026-10-03 — survey and plan (Opus 5.5, as the session, with two
read-only subagents).** Read `native/` whole and its two documents
(`c-engine-port.md`, `native-gui.md`), and the build and verify tools in
outline. Surveyed through subagents:

- the C17 rewrite of [klattsch](https://github.com/dengopaiv/klattsch-NVDA)
  (`docs/REWRITE.md`, stage chapters 12–18, CMake and CI);
- the layout of [Votraxxion](https://github.com/dengopaiv/Votraxxion);
- the author's private rewrite and port plans for other engines.

Taken from them:

- from the private plans: the frozen reference, back-to-front order,
  one branch per stage, the comparator as the gate, the sorting of
  every check into "engine behaviour" or "artefact of the port", and
  the before-and-after measurement table;
- from klattsch: CMake from the first stage, the four-leg matrix, one
  dump tool per boundary feeding one verifier, mutation suites, and the
  Unix leg verified from Windows;

Measured: the strict-C17 warning count in §1 (gcc 14.2.0, clang 19.1.7,
`-fsyntax-only` over `native/src/*.c`), and the toolchains in §3.4.

Not done, and so not claimed:

- the MSVC `/std:c17` build of `native/`;
- the coverage of the §1.1 idioms;
- the dictionary size estimates in §6;
- any timing in §7.

The Python and the frozen port were read for their idioms only; nothing
in them was re-verified today.

**2026-10-03 — the author's decisions (Opus 5.5, as the session).**
D1–D4 settled, recorded in §9 and at each place they apply (§1.3, §2,
§3.1, §4, §6). Two consequences found while recording them, and added to
the plan:

- **The tools have to move before `native/` can leave `master`.** The
  shared tools and golden vectors live inside `native/`, and the
  packaging reads `native/build`. That gave the new stage R.11.
- **The dictionary is now a stage of its own, R.12.** The GUI
  connector moved from R.11 to R.13.

No code was changed.

**2026-10-03 — D5 decided (Opus 5.5, as the session).** The 16 silent
dictionary words are fixed in R.12. Their cause was traced to the 22
commented lines of `cmudict.txt`. One suspicion was checked and ruled
out: `fine(2)` has a comment, but the main `fine` entry wins, and the
word speaks. Written up in §6.1. No code was changed.

**2026-10-03 — stage R.0 (Opus 5.5, as the session).** Done on branch
`c17-r0-scaffold`. The chapter is [docs/c17/00](c17/00-r0-scaffold.md).
What turned out different from this plan:

- **The verifier switch.** Three verifiers had private copies of the
  build step, so the switch needed a refactor first. It was proved
  output-identical against a baseline taken before any edit.
- **The R.3 exit count.** `verify_prepare.py` runs 400 random cases by
  default, not 3,000; R.3 now names the argument.
- **The freeze marker** is `native/README.md`, not a line in each source
  file. Four of those files are generated, and touching all of them
  would trip `make_release.py`'s staleness check.
- **The latency grid of §7** is too noisy under the Balanced power plan
  to support a claim. The 20-word sentence figure (1.64 ms median, real
  time factor 0.0002) is stable, and is the one R.9 compares against.
