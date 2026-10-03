# 0. Stage R.0 — scaffold and freeze

Stage R.0 of [the C17 rewrite plan](../c17-rewrite-plan.md), on branch
`c17-r0-scaffold`. It produces no engine code. It sets up everything the
later stages are checked with, and it takes the measurements they are
compared against.

**Result:** `engine/` builds as C17 on four toolchains with zero warnings.
Its one test passes on all four. On the two Windows legs the seven
differential verifiers are registered, and each skips until its stage.
The verifiers now check either implementation (`--impl native|engine`).
On `native/` their output is byte-identical to what they printed before
any of them was touched. The 32-bit builds are gone from every build and
packaging script, and the addon needs NVDA 2026.1. The baseline
measurements are in §0.6.

---

## 0.1 Before anything changed: the baseline run

`native\build.cmd` was run on the unmodified tree (still building x64 and
x86 at that point). Then every verifier was run and its full output kept,
so later runs could be diffed against it rather than eyeballed:

| Verifier | Result on `native/`, 2026-10-03 |
|---|---|
| `verify_tables.py` | all 16 tables match, 2,392 values |
| `verify_frames.py` | `sam_set_mouth_throat` matches for all 65,536 (mouth, throat) pairs |
| `verify_prepare.py` | 416 comparable cases (16 golden + 400 random), all 8 rows |
| `verify_prepare.py 3000` | 3,015 comparable cases (16 golden + 3,000 random; Python raised `IndexError` on 1, which the C survives) |
| `verify_render.py 485` | 16 golden cases and 485 random sequences byte-identical. *Overtaken 2026-10-03, R.4:* the 485 compared the DLL with itself, not the Python ([04](04-r4-renderer.md) §4.1); against the Python, 470 comparable cases, all identical |
| `check_golden.py` | all 16 cases byte-identical |
| `verify_parser.py` | 136,096 cases |
| `verify_reciter.py` | 146,692 cases |
| `verify_text.py` | 144,272 cases, and 4,216 for `expand_numbers` |
| `verify_gui.py` | x64 and x86 exes byte-identical to the Python GUI, 39 cases each |
| `verify_gui_presets.py` | presets round-trip in both builds |

`verify_gui_keyboard.py` was not run. It sends real keystrokes to a GUI
window, which would land in whatever the author was doing at the time.

**A correction to the plan, found here.** The plan's R.3 exit test
quoted `c-engine-port.md`'s "3,000 randomised cases" for
`verify_prepare.py`. The script's default is 400; 3,000 is its
argument. The R.3 exit test is `verify_prepare.py 3000`, and the plan
now says so. The ctest entry passes 3000.

## 0.2 `engine/`

```
engine/
  CMakeLists.txt
  include/sam_render.h     copied from native/include, cmp-identical
  include/sam_text.h       copied from native/include, cmp-identical
  src/version.c            sam_abi_version, sam_text_abi_version, and the
                           _Static_asserts on the two struct sizes
  tests/test_abi.c         the library links and reports its versions
  tools/build_matrix.py    configure, build, test and count warnings, per leg
```

`CMakeLists.txt` follows the plan's §3.3:

- C17 with extensions off;
- a fatal error on any 32-bit configuration;
- `/W4` on MSVC, `-Wall -Wextra -Wpedantic -Wshadow -Wconversion`
  elsewhere;
- one static and one shared library from one source list, with hidden
  visibility. The shared one is named `sam_render`, as the addon expects.

**The version.** Read from `nvda-addon/manifest.ini` (1.5.0), the
project's one version number. `gui-native/sam_gui.rc` copies it, and
`tools/make_release.py` checks that copy. A third hand-kept copy is
how they drift (commit `3cb0fb2`).

**A bug found and fixed on the way: the Windows legs built Debug.** The
first matrix run showed `/Od /RTC1 -MDd` in MSVC's `build.ninja`. The
Release default was written after `project()`, and on Windows `project()`
has already filled in `CMAKE_BUILD_TYPE`, so the test never fired. The
default now comes before `project()`, and every leg's flags were checked
in its `build.ninja` afterwards:

| Leg | Compiler | Flags as built |
|---|---|---|
| msvc | MSVC 19.51.36260.0 | `/O2 /Ob2 /DNDEBUG -std:c17 -MD /W4` |
| clang-cl | clang-cl 22.1.3 (VS 18's LLVM) | `/O2 … -std:c17 … /W4` |
| wsl-gcc | gcc 14.2.0, Debian 13.7 | `-O3 -DNDEBUG -std=c17 -fvisibility=hidden -Wall -Wextra -Wpedantic -Wshadow -Wconversion` |
| wsl-clang | clang 19.1.7, Debian 13.7 | the same |

CMake 4.4.3 and Ninja 1.12.1 on Windows; CMake 3.31.6 and Ninja 1.12.1
under WSL. The WSL legs build under `$HOME/sam-engine-build/`, on the
Linux file system, not inside the Windows checkout.

**The result:**

```
leg        build    tests              notes
msvc       ok       1/8 (7 skipped)    0 warnings
clang-cl   ok       1/8 (7 skipped)    0 warnings
wsl-gcc    ok       1/1                0 warnings
wsl-clang  ok       1/1                0 warnings
```

`build_matrix.py` counts skips apart from passes because ctest does not.
It prints `100% tests passed` with seven of eight skipped. CMake 4's
ctest also drops the "0 tests failed" clause when nothing failed, and
the first version of the script's pattern missed it for that reason.

## 0.3 The verifiers check either implementation

The plan's R.0 bullet assumed one switch in `_build.py`. Reading the
tools showed it was more than that:

- `verify_tables.py`, `verify_frames.py` and `verify_prepare.py` each
  carried a private copy of the MSVC lookup and the compile step;
- `verify_render.py` loaded the DLL from `native/build` through ctypes;
- the three GUI checks look for `gui-native/build/sam_gui-*.exe`.

**Step 1: fold the copies in, changing nothing.** `build_and_run()` in
`_build.py` gained two options:

- `defines`, for `dump_prepare.c`'s `_CRT_SECURE_NO_WARNINGS`;
- `text`, which decodes stdout and reads `\r\n` as `\n`, as
  `subprocess`'s `text=True` did for the private copies.

The three private copies became calls to it. Counting step 2's lines as
well, the three files lost 151 lines and gained 18.
Their output was diffed against the baseline logs of §0.1: identical,
byte for byte, for all three.

**Step 2: the switch.** `take_impl()` removes `--impl native|engine`
from `sys.argv`, so each script's own positional arguments stay where
they were. `build_and_run()` and `engine_dll()` follow the choice:

- `native` compiles the dump tool from `native/tools` against
  `native/src`, as before;
- `engine` runs the dump tool of the same name from the rewrite's build
  tree (`SAM_ENGINE_BUILD`, default `engine/build-msvc`). That tool is a
  CMake target, written in the stage that needs it, and prints the same
  format, so the same Python checks both. A tool that does not exist yet
  exits 77, which ctest reports as skipped;
- `verify_render.py` loads the rewrite's DLL and skips while it does
  not export `sam_render` (stage R.4);
- the GUI checks skip under `--impl engine` until R.8 builds a GUI
  against the rewrite.

After step 2, the whole suite was run again on `native/` with the
default switch. All ten outputs were byte-identical to the baseline.
Under `--impl engine` every verifier exits 77 and names what it is
waiting for. A wrong `--impl` value is refused.

## 0.4 `native/` frozen

`native/README.md` says what frozen means:
- `src/` and `include/` change only for a bug that is fixed in both
  engines;
- `tools/` and `tests/golden/` are shared, and move out before
  `native/` leaves `master`.

The plan had offered a header line in each source file as the
alternative. That was rejected for two reasons. Four of the files are
generated and say "do not edit". And `make_release.py` refuses to ship a
DLL older than its sources, so touching every source would mark a
correct binary stale.

## 0.5 No more 32-bit builds; NVDA 2026.1 (decision D3)

| File | Change |
|---|---|
| `nvda-addon/manifest.ini` | `minimumNVDAVersion = 2026.1.0` (was 2023.1.0) |
| `native/build.cmd` | builds `sam_render-x64.dll` only |
| `gui-native/build.cmd` | `x64` only; `x86` is refused with a message |
| `nvda-addon/synthDrivers/sam/native.py` | loads `sam_render-x64.dll` only |
| `nvda-addon/package_addon.py` | packages the x64 DLL only |
| `nvda-addon/validate_addon.py` | a 32-bit DLL in the package is a failure, no longer a warning |
| `tools/make_release.py` | no x86 inputs; the archive's readme says 64-bit Windows and NVDA 2026.1 |
| `native/tools/verify_gui*.py` | check x64 only |
| `README.md`, `nvda-addon/README.md`, `docs/native-gui.md` | say x64 and NVDA 2026.1, and that 1.5.0 and earlier carried x86 |
| `docs/c-engine-port.md` | a dated *Overtaken* note; the old reasoning stays as written |

Each file that changed says, at the place it changed, that release 1.5.0
and earlier carried 32-bit builds. Those releases are not touched (D3).
`sam-native.zip` in the tree is the 1.5.0 release, x86 and all. It was
not rebuilt, because rebuilding it would be a release.

Checked after the change:
- `native\build.cmd` builds only `sam_render-x64.dll`;
- `gui-native\build.cmd x86` refuses;
- `package_addon.py` packages only the x64 DLL;
- `validate_addon.py` reports `NVDA 2026.1.0+`, `sam_render-x64.dll is x64`
  and a packaged engine that renders natively;
- `verify_render.py 485`, `verify_gui.py` and `verify_gui_presets.py` pass.

The x86 DLL and exe from earlier builds still sit in the ignored build
directories. Nothing reads them any more.

## 0.6 Baseline measurements (plan §7)

`native/tools/measure.py` (new) times the renderer two ways:
- directly, through `native/tools/bench_render.c` (new), compiled with
  the DLL's `/O2 /MT`;
- through ctypes, as the NVDA driver calls it.

It renders a fixed 20-word sentence, the latency grid, and the worst
case. The phonemes come from the Python front end, so both
implementations render the same input.

**Machine:** Intel Core i7-8850H at 2.60 GHz, Windows 10.0.26340 on AC
power with the Balanced power plan, Python 3.13.15. **Renders:** median
of 200, after one warm-up.

**A first run was wrong, and is not counted.** The direct figure came out
at 7.5 ms against 1.65 ms through ctypes, which cannot be right. The
cause: `build_and_run` compiles unoptimised, which is right for
checking values and wrong for timing them. It gained a `flags` option,
and the bench is built with the DLL's flags.

Three runs after the fix:

| | run 1 | run 2 | run 3 |
|---|---|---|---|
| sentence, ctypes median | 1.806 ms | 1.645 ms | 1.633 ms |
| sentence, direct median | 1.680 ms | 1.661 ms | 1.639 ms |
| `"comfortable"`, speed 72 | 0.198 ms | 0.467 ms | 0.453 ms |
| `"comfortable"`, speed 150 | 0.379 ms | 0.402 ms | 0.585 ms |
| `"incomprehensibility"`, speed 150 | 1.145 ms | 0.923 ms | 0.965 ms |

The sentence: *The quick brown fox jumps over the lazy dog while seven
wizards quietly judge every boxing match in the town*. That is 184,501
samples, or 8,367 ms of audio, so the real-time factor is 0.0002 by
either path. Sizes: `sam_render-x64.dll` 159,232 bytes,
`sam_gui-x64.exe` 4,037,632 bytes.

**What these numbers are fit for:**

- **The sentence figure is stable** to within about 10 % across runs,
  and direct and ctypes agree. At this size, ctypes costs nothing
  measurable. This is the figure R.9 compares against.
- **The sub-millisecond latency cells are not stable.** "comfortable" at
  speed 72 moved from 0.198 to 0.467 ms between runs, and once it came
  out slower than at speed 150. The Balanced plan lets the clock wander,
  and a render this short sees it. Before the grid is used for a claim
  in R.9, it needs a fixed power plan or many more renders. Until then
  it shows orders of magnitude, nothing finer.
- **Not comparable with `c-engine-port.md`**, which reported 17.2 ms and
  a real-time factor of 0.0021 for "a 20-word sentence" through ctypes.
  Which sentence, and how the time was taken, were not recorded, so the
  tenfold difference here is not explained and is not claimed as a
  change.

## 0.7 What R.0 did not do

- **No `--check` mode for the generators** (`gen_tables.py`,
  `gen_frontend_tables.py`). The plan's `quick` ctest label waits for
  R.1, where the rewrite's generated tables first exist.
- **The Linux legs run only `test_abi`.** The verifiers are registered
  on Windows only, because they expect `.exe` and `.dll`. Verifying the
  Linux builds from Windows is R.10.
- **`verify_gui_keyboard.py` was edited and not run**, for the reason in
  §0.1. Its change is the x64-only architecture list and the
  `--impl engine` skip; the skip was run, the x64 path was not.
- **ARM64 is not configured.** The CMake guard allows it, and no leg
  builds it.

## 0.8 Files

New:
- `engine/CMakeLists.txt`;
- `engine/include/` (copies);
- `engine/src/version.c`;
- `engine/tests/test_abi.c`;
- `engine/tools/build_matrix.py`;
- `native/README.md`;
- `native/tools/bench_render.c`;
- `native/tools/measure.py`;
- this chapter.

Changed: the verifiers and `_build.py` (§0.3), and the build, packaging
and documentation files of §0.5. `.gitignore` now ignores the engine
build trees.

Not touched:
- `native/src` and `native/include`;
- the Python engine;
- the golden vectors;
- `sam-native.zip`;
- the uncommitted driver work in `nvda-addon/synthDrivers/sam/__init__.py`
  and `nvda-addon/smoke_driver.py`, which predates this stage and is
  not part of it.

**Known, inferred, guessed.**
- *Known:* every result line above was printed by the command named
  next to it, on 2026-10-03.
- *Inferred:* that the latency noise comes from the power plan. It fits
  the evidence and was not tested by changing the plan.
- *Guessed:* nothing.
