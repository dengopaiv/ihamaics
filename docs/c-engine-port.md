# Porting the SAM engine to C

**Status: done.** The native renderer is byte-identical to the Python one
and 28.8x faster than the original baseline. renderer.py delegates to it
when the DLL loads and falls back to Python otherwise.

| | sentence render | real-time factor | worst-case latency |
|---|---|---|---|
| Python, original | 496.3 ms | 0.060 | 227 ms |
| Python, optimised | 269.1 ms | 0.0326 | 95 ms |
| **C via ctypes** | **17.2 ms** | **0.0021** | **4.2 ms** |

Worst case is "incomprehensibility" at the slowest rate. The C timings
include ctypes overhead, because that is what the driver pays.

Verification, all byte-for-byte:

- 16 golden vectors, native and Python paths, and against each other
- 485 randomised phoneme sequences through ctypes
- 3000 randomised cases through sam_prepare_frames, all 8 rows
- all 65536 (mouth, throat) combinations through sam_set_mouth_throat
- all 2392 table values, compiled and dumped from C
- the packaged addon, loading its own bundled DLL
- the packaged addon with the DLLs deleted, falling back to Python

The rest of this document is the plan the work followed, kept because the
measurements explain the design.

All timings below were measured on this repository, not estimated.

## The finding that shapes everything

The engine is **not** broadly slow. Measured over a 20-word sentence:

| Stage | Time | Share |
|-------|------|-------|
| reciter (text to phonemes) | 0.4 ms | 0.1% |
| parser | 1.0 ms | 0.2% |
| **renderer** | **496.3 ms** | **99.7%** |

Synthesis runs at a **real-time factor of 0.060** — 16x faster than
playback — and that ratio holds across the whole speed range. Within
the renderer, one function dominates:

| Function | tottime | Calls |
|----------|---------|-------|
| `process_frames` | 0.911 s | 20 |
| `sinus` | 0.288 s | 496,080 |
| `builtins.len` | 0.261 s | 2,101,880 |

So this is not a rewrite of SAM. It is a rewrite of **`process_frames`**
— roughly 160 lines of `renderer.py` — plus the helpers it calls in its
inner loop. The reciter, the parser, all the rule tables and the CMU
dictionary integration stay in Python, where they cost nothing and where
the awkward, table-heavy logic is far easier to maintain.

## Latency, which is what "too slow" actually means

Throughput is fine; the number a screen reader user feels is the delay
before the first sound. Synthesis time per utterance, by speed setting:

| speed | `"a"` | `"the"` | `"comfortable"` |
|-------|-------|---------|-----------------|
| 15 (fastest) | 0.9 ms | 1.8 ms | 14.0 ms |
| 72 (default) | 4.1 ms | 8.7 ms | 55.6 ms |
| 150 (slowest) | 8.3 ms | 17.7 ms | 111.5 ms |

Worst realistic case, `"incomprehensibility"` at speed 150: **227 ms**
before audio begins.

Two things follow. First, synthesis cost tracks the *length of the audio
produced*, so the slow speech settings are the expensive ones. Second,
these are numbers from a modern desktop. NVDA users routinely run older
and lower-power hardware, where a 16x margin can fall to 2-3x and the
word-by-word streaming in `_speak_text` starts to underrun.
**Headroom, not the desktop average, is the reason to do this.**

## Scope

Port to C:

- `process_frames` and its inner loop
- `render_sample` / `render_sample_inner`
- `create_frames`, `create_transitions`, `prepare_frames`
- `set_mouth_throat`
- the numeric tables in `renderer_tables.py`

Leave in Python:

- `reciter.py`, `reciter_tables.py`, `cmudict.py` (0.1% of cost)
- `parser.py`, `parser_tables.py` (0.2% of cost)
- the NVDA driver, the settings plumbing, the GUI

The seam is exactly where `render()` is called today, and the parser's
output — a list of `[phoneme, length, stress]` triples — is already a
flat array of bytes, so it crosses the boundary with no marshalling.

## C, not C++

Recommend **C99**, for concrete reasons rather than taste:

- The algorithm is straight-line fixed-point integer DSP over static
  tables. No allocation, no ownership, no polymorphism — nothing C++
  would simplify.
- `ctypes` needs `extern "C"` regardless, so C++ buys an internal
  convenience at the cost of an ABI wrapper.
- No C++ runtime to redistribute. `votraxsc01` ships a 216 KB DLL with
  no dependency beyond the CRT; we should match that.
- The reference implementations to port *from* — `s-macke/SAM` and the
  `c-conv` transliterations that were then in `test/` — are C.

## Deployment

Confirmed on this machine:

- NVDA at `C:\Program Files\NVDA` is **x64**, bundling **Python 3.13**
  (`python313.dll`), which matches the local dev interpreter exactly.
  A DLL built here loads in NVDA without cross-compiling.
- NVDA still ships 32-bit builds, so ship both and select at runtime.

`votraxsc01`, already installed, is the working template: it ships
`sc01-x64.dll` and `sc01-x86.dll` side by side in its `synthDrivers`
directory and picks between them with

```python
return "sc01-x64.dll" if ctypes.sizeof(ctypes.c_void_p) == 8 else "sc01-x86.dll"
```

Its driver also carries a warning worth heeding: declaring `argtypes`
is not optional polish. Without it `ctypes` guesses at marshalling and
the failures are silent and data-dependent.

The ABI is defined in [`native/include/sam_render.h`](../native/include/sam_render.h):
caller-allocated output buffer, `out == NULL` to query the required
size, negative returns for errors, and no globals so it stays
thread-safe.

## Verification

`native/tools/gen_golden.py` dumps 16 reference cases from the current
Python renderer into `native/tests/golden/` — 195,288 samples covering
the speed extremes (10 and 255), every voice preset, pitch floor and
ceiling, mouth and throat at 0 and 255, sing mode, monotone and
dramatic inflection, a question, a long word and a full sentence.

**The C port must reproduce these byte for byte.** SAM is fixed-point
integer arithmetic throughout, so bit-exactness is achievable and is
the only honest test — a renderer that is merely "close" has a
different voice, and this project exists for the voice.

During the port, the `test/renderer/fixtures/` corpus from the
JavaScript tree served as a second, independent oracle for the same
code path. That tree is no longer vendored here; the golden vectors
above are what the build checks against now.

`native/tools/check_golden.py` renders each case from its recorded
inputs and diffs against the recorded output; it is what proved the
Python optimisations above changed nothing.

Regenerate the vectors only when the Python renderer changes on
purpose. A diff there during the port means the port is wrong.

## Toolchain

Present on this machine and verified working end to end:

- **Visual Studio 18 Community**, `C:\Program Files\Microsoft Visual Studio\18\Community`
- **MSVC 14.51.36231**, with both `Hostx64/x64` and `Hostx64/x86`
  targets, so one machine builds both DLLs NVDA needs.

`cl.exe` is not on `PATH` — it only exists inside a developer shell.
`native\build.cmd` locates the install with `vswhere`, calls
`vcvarsall.bat` per architecture, and emits
`native/build/sam_render-{x64,x86}.dll`. Run it from anywhere:

```
native\build.cmd
```

(`vcvarsall.bat` prints a harmless `'vswhere.exe' is not recognized`
line from its own internals; the build succeeds regardless.)

Two things this scaffolding already settled, either of which would
otherwise have cost an afternoon:

- **MSVC exports no symbols by default.** `ctypes` fails with
  `AttributeError: function 'sam_abi_version' not found` until the
  build defines `SAM_BUILD_DLL` and the header decorates each entry
  point with `__declspec(dllexport)`. Both are in place.
- **Struct layout agrees across the boundary**, verified by loading the
  DLL from Python: `sizeof(sam_phoneme_t) == 3` (no padding) and
  `sizeof(sam_voice_t) == 12`. Keep it that way; adding a field to
  `sam_voice_t` without bumping `SAM_ABI_VERSION` will silently
  misread arguments.

The stub in `native/src/sam_render.c` implements `sam_abi_version()`
for real and returns `SAM_E_BADARG` from `sam_render()`, so the Python
path stays in charge until the port lands. Error codes were checked
through `ctypes`: valid arguments give -1 (not implemented yet),
`speed == 0` gives -2, and `count == 0` or a NULL pointer give -1.

## Suggested order

1. ~~Stand up a toolchain.~~ **Done** — see Toolchain above;
   `nativeuild.cmd` already produces working DLLs for both
   architectures.
2. Transliterate the tables from `renderer_tables.py` into a `.c` file
   of `static const` arrays. Mechanical; script it rather than typing it.
3. Port `set_mouth_throat`, `create_frames`, `create_transitions` and
   `prepare_frames`. Check each against a Python-side dump of its
   intermediate arrays before moving on.
4. Port `process_frames` last — it is the payoff and the part most
   likely to hide an off-by-one.
5. Wire up `ctypes` behind the existing `render()` signature, keeping
   the Python renderer as a runtime fallback when the DLL is missing.
   The addon must still work if the native library fails to load.
6. Run the golden vectors. Iterate until every case is byte-identical.
7. Re-measure against the baseline in this document.

Expect roughly 30-100x on `process_frames`, which puts a default-speed
word in the region of 0.1 ms and removes the underrun risk on slow
hardware entirely.

## Python optimisations already applied

Done before the port, because they also improve the fallback path that
has to survive a missing DLL. All verified byte-identical against the
golden vectors.

- **`sinus()` is now a 256-entry table.** It was recomputing `math.sin`
  496,080 times per sentence for a pure function of one byte. The
  JavaScript does the same thing, but a JIT hides it and CPython does not.
- **The five-iteration inner loop was recomputing six array lookups
  identically each pass.** `pos` does not change inside that loop, so
  the amplitude and frequency reads, and the phase deltas derived from
  them, are loop invariant. Hoisting them out mattered more than the
  sine table did.
- **`len()` was called 2.1 million times** as loop-invariant bounds
  checks; the lengths are now bound to locals once per call.
- **The CMU dictionary load is now started on a background thread** at
  driver init (`cmudict.preload_async()`) instead of being paid lazily
  on the first word NVDA ever speaks.
- **`load_cmudict()` had a publication race.** It assigned the empty
  dict to the module global *before* spending 150ms filling it, so a
  concurrent lookup could observe a half-built table and return a wrong
  pronunciation. It now builds into a local, publishes under a lock only
  once complete, and was stress-tested with 12 threads racing the cold
  load. Backgrounding the load without this fix would have made that
  race live.
- **`cancel()`'s join timeout dropped from 0.5s to 0.2s.** The join is
  already best effort, and the speech thread re-checks the cancel flag
  between words, so it exits within one word's synthesis.

Result: **2.11x faster, byte-identical output.**

| | before | after |
|---|---|---|
| sentence render | 496.3 ms | 235.5 ms |
| real-time factor | 0.060 | 0.0285 |
| `"comfortable"` @ speed 72 | 55.6 ms | 25.3 ms |
| worst case @ speed 150 | 227 ms | 95 ms |

**This is the baseline the C port must beat**, not the original numbers
above. The remaining structural issue that C will not fix: `speak()`
calls `cancel()` first, so a new utterance still serialises behind the
previous thread. The real fix is a generation counter guarding
`_player.feed()` so stale threads cannot emit audio and the join can go
entirely — deliberately not attempted here, because the NVDA driver
cannot be exercised outside NVDA and a threading bug in a screen reader
is not a good thing to ship untested.

## Reproducing the measurements

```
python native/tools/gen_golden.py     # regenerate reference vectors
```

The stage split, profile and latency table were produced with
`cProfile` over `render()` and `time.perf_counter()` around
`text_to_phonemes` / `parse` / `render`.
