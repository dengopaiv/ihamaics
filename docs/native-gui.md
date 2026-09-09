# The native GUI

`gui-native/` builds `sam_gui.exe`: the desktop application with no Python
behind it. One file, no installer, no runtime to put on the machine first.

```
python native\tools\gen_dict.py     :: once, and after any dictionary change
gui-native\build.cmd x64
gui-native\build.cmd x86
```

Output is `gui-native/build/sam_gui-{x64,x86}.exe`, about 4.0 MB — most of
which is the pronunciation dictionary.

## Why this needed more than the DLL

[The C engine port](c-engine-port.md) covered the renderer, and stopped
there on purpose: the renderer was **99.7%** of synthesis cost and the
front end was 0.3%, so porting the rest would have bought nothing a
screen reader user could hear. That was the right call for the NVDA
addon, which keeps a Python interpreter around anyway.

It is exactly the wrong split for an application with no interpreter. So
the front end is ported too — not for speed, but because a 3.6 MB
dictionary and 2,300 lines of Python are what stand between this and a
single executable:

| Stage | Python | C |
|---|---|---|
| Rules-based text→phonemes | `reciter.py`, `reciter_tables.py` | `native/src/sam_reciter.c` |
| CMU dictionary lookup | `cmudict.py` | `native/src/sam_text.c` |
| Numbers→words | `reciter.py` (`expand_numbers`) | `native/src/sam_text.c` |
| Phoneme parser | `parser.py`, `parser_tables.py` | `native/src/sam_parser.c` |
| Renderer / DSP | `renderer.py` | `native/src/sam_render.c` (already done) |
| GUI | `sam_gui.py` (wxPython) | `gui-native/sam_gui.cpp` |

The whole Python package now has a C counterpart. `native.py` and the
NVDA addon still use the DLL for synthesis only, which is unchanged —
`sam_render.h` stays at ABI 1 and the front end is versioned separately
in `sam_text.h`, so an installed addon and a newer DLL do not have to
move in lockstep.

## The tables are generated, never typed

`native/tools/gen_frontend_tables.py` writes the phoneme flag and length
tables, the 403 reciter rules, the 41 punctuation rules and the ARPABET
map straight from the Python. Same reason `gen_tables.py` exists for the
renderer: transliterating a few thousand values by hand is how a voice
quietly changes. Edit the Python and regenerate; the generated files say
so at the top.

## The dictionary is a blob, not an array

126k entries and 3.3 MB of strings would be tens of megabytes of C source
and a minute of compiler time for data that never needs compiling. So
`native/tools/gen_dict.py` writes `native/data/sam.dict`: a sorted word
list with an offset table, binary-searched in place.

The GUI links it as an `RCDATA` resource and hands the engine a pointer;
the test tools read the file and pass that. The engine never owns it,
never copies it and never frees it, which is why the same code serves
both. Every key is ASCII, so a C byte comparison and Python's own string
ordering agree — `gen_dict.py` asserts that rather than assuming it.

The blob is generated, so it is gitignored. `build.cmd` refuses to build
without it and says which command to run.

## What the GUI does

Feature for feature, `sam_gui.py`:

- multi-line text box
- speed (1–255), pitch, mouth, throat (0–255), inflection (0–100)
- **Preview** — synthesizes on a worker thread and plays it, with the
  button disabled until playback finishes
- **Render to WAV** — standard save dialog, 8-bit unsigned 22050 Hz mono

Plus four controls the engine has always supported and no GUI exposed:

- **Phoneme mode** — the input is raw phonemes, `text_to_audio(phonetic=True)`
- **Convert to Phonemes** — replaces the text with its phoneme string and
  switches to phoneme mode
- **Sing mode** — the renderer's `singmode`, a `text_to_wav` argument that
  `sam_gui.py` never wired to anything
- **Voice preset** — the six voices from `VOICE_PRESETS` in `sam.py`,
  which are the table printed in the 1982 manual

### How the preset combo behaves

Choosing a preset writes its four numbers — speed, pitch, mouth, throat —
into the boxes. Inflection is left alone, because `sam.py`'s presets do
not carry one.

The selection is **derived from the values, not remembered**. After any
change to those four boxes the combo is recomputed: it names whichever
preset the numbers describe, or says Custom when they describe none.
Selecting Custom deliberately does nothing, since there is no custom set
of numbers to apply.

That direction matters. A combo that remembered the last thing clicked
would go on saying "Little Robot" after the speed was edited by hand,
which is a GUI claiming one voice while speaking another. Deriving it
also means applying a preset needs no re-entrancy guard: the sync settles
on the preset just applied, so it is a fixed point, and `CB_SETCURSEL`
sends no notification back.

`sam.py`'s presets are duplicated in `PRESETS` in `sam_gui.cpp`, because a
Win32 combo cannot import a Python dict. `verify_gui.py` diffs the two on
every run — these four values have been transposed once already, in
commit `2116629`.

## Three quirks carried over deliberately

Each of these is a bug. Each is reproduced exactly, because the C has to
agree with the Python rather than with what the Python meant, and because
"fixing" any of them silently changes output that is already verified.

**A word between two words costs two spaces.** `text_to_phonemes` reads:

```python
rule_result = _rule_based_phonemes(token)
if rule_result and rule_result is not False:
    result_parts.append(rule_result.strip())
```

The truthiness test is on the *unstripped* string, and the value appended
is the *stripped* one. The space between two words is its own token and
strips to `''`, so it contributes an empty part that still takes a
separator from the final `' '.join()`. `"RUN CORRESPONDINGLY"` comes out
with two spaces in it. Testing the stripped length instead — the obvious
way to write it — changes every multi-word phoneme string in the
language. This was caught by `verify_text.py` on 5,500 of 144,272 cases,
not by reading the code.

**Sixteen dictionary words are unspeakable.** `cmudict.py` splits each
line on whitespace and keeps `parts[1:]` as the pronunciation, so an
entry like

```
aalborg AO1 L B AO0 R G # place, danish
```

stores `#`, `place,` and `danish` as if they were phonemes.
`arpabet_to_sam` passes unknown tokens through unchanged, the parser
cannot read the result, and `text_to_audio` returns `None` — **no audio
at all for the whole utterance**, not just the one word. Any sentence
containing "Aalborg", "Aalen", "Aalsmeer" and thirteen others is silent.
`verify_gui.py` covers this case and asserts that both implementations
refuse together.

**`parse(".")` writes through index -1.** In `adjust_lengths`, a
punctuation phoneme at position 0 walks the cursor to -1, and Python's
`phoneme_length[-1] = value` means *the last element*. It is reachable:
`parse(".")` returns a length of 1 where the table says 18. The C port
reproduces the wrap in `py_set()` rather than clamping.

The first of these is worth fixing one day; the second is worth fixing
soon, since it makes ordinary sentences silent. Both are decisions about
the voice and the Python, not about this port, so neither is made here.

## Accessibility

Standard Win32 controls throughout, with a static label immediately
before each control in z-order, `&` accelerators on every label, and
`IsDialogMessage` in the message loop so tab order, arrow keys within
groups and the default button all behave. The spin controls are real
up-downs with buddy edits rather than a custom widget.

This is not decoration. The program is a front end for a screen reader
voice, and a custom-drawn UI would look identical and be unusable.

It splits into two claims, and they need checking in different ways.

**Does a screen reader read the controls?** That is not something a tool
can settle, so it stays a question for whoever is at the keyboard.

**Can you get to them?** That half is mechanical, and it is checked by
`verify_gui_keyboard.py`. It had to be. Everything in the paragraph above
was true of the sibling project's GUI and it was still a keyboard trap:
the multiline text box answered `WM_GETDLGCODE` with `DLGC_WANTALLKEYS`,
`IsDialogMessage` returned before its own `VK_TAB` handling, and focus
went into the box and stayed there. Every label was correct and
unreachable.

So the box here is subclassed to stand aside for a Tab keydown and
nothing else — Enter still inserts a newline, the arrow keys still
navigate the text, typing is untouched — and the check is run rather than
asserted. The GUI reports `WM_GETDLGCODE` of `0x8d`
(`WANTARROWS | WANTALLKEYS | HASSETSEL | WANTCHARS`) and Tab leaves it
anyway.

The same script also checks that no two controls claim the same `&`
accelerator. Windows does not complain about a duplicate — Alt+V just
cycles between the two claimants instead of activating either — so the
clash is invisible until someone navigating by keyboard cannot reach a
button. Adding the voice preset introduced exactly that: `&Voice preset`
against `Pre&view`. It is `V&oice preset` now, and the twelve
accelerators are checked to be distinct on every run.

One note for anyone extending these scripts: **`press_tab` waits for the
focus to move rather than sleeping a fixed interval.** The keypress is
posted to another process, and on a busy machine that process can take
longer to handle it than any pause you would be willing to hardcode. With
a fixed sleep the walk gave up early and reported reachable controls as
unreachable — a test that passes when the machine is idle and fails when
it is not is worse than no test, because it teaches you to ignore it.

The lesson is the ordering. Correct labels on controls nobody can reach
are worth nothing, and a design argument for accessibility — however
sound — is not evidence that the built program is accessible.

## Verification

```
python native\tools\verify_parser.py         # parser vs Python
python native\tools\verify_reciter.py        # rule engine vs Python
python native\tools\verify_text.py           # front end vs Python
python native\tools\verify_gui.py            # the exe vs the Python GUI
python native\tools\verify_gui_presets.py    # the preset combo, in the real window
python native\tools\verify_gui_keyboard.py   # its tab order, for real
```

The renderer could be checked with golden vectors because the voice is a
fixed target. The front end is a function over every word in English, so
it is checked against the whole domain instead:

| Check | Cases | Result |
|---|---|---|
| `sam_parse_phonemes` | 136,096 | identical |
| `sam_reciter_rules` | 146,692 | identical |
| `sam_text_to_phonemes`, with dictionary | 144,272 | identical |
| `sam_text_to_phonemes`, rules only | 144,272 | identical |
| `sam_expand_numbers` | 4,216 | identical |
| `sam_gui.exe` vs `sam_gui.py`, x64 and x86 | 39 each | byte-identical |

The 39 include sing mode on and off, every preset spoken and sung, and
the preset table diffed against `sam.py` before any of them run.

Every one of the 126,052 dictionary words appears in the parser, reciter
and front-end corpora. The rest is coined words that force the rule
engine, sentences built from real words, every printable character alone
and in context, and randomised phoneme strings for the paths a real word
never takes.

`verify_gui.py` drives the built executable through a `--selftest` mode
that runs the same code path the Preview and Render buttons run, and
compares the WAV with what `sam_gui.py` produces for the same control
values. That checks the shipped binary rather than a harness that merely
shares its sources — a test sharing the sources would pass while the exe
was missing its dictionary resource.

Two notes on what the comparisons do and do not cover.

**Numbers are compared on digits, not integers.** Python's `int` is
unbounded and `_number_to_words` recurses on `n // 1000000`, so
`"one million million"` is a reachable answer and no C integer type
reproduces it. `sam_text.c` splits the decimal string at the same places
instead, and `verify_text.py` includes 20-, 30- and 40-digit inputs to
say so.

**The front end is verified over ASCII.** Non-ASCII bytes have a
character flag of zero in both implementations and become a space either
way, so they agree without being enumerated. The exception is the handful
of characters whose Unicode uppercase is ASCII and longer than one
character — `ß` uppercases to `SS` in Python and stays one byte here.
Nothing the reciter can pronounce is in that set, and the GUI narrows to
`CP_ACP` bytes before calling in.

**Reading another process's controls needs `WM_GETTEXT`, not
`GetWindowText`.** `GetWindowText` will not fetch the live text of a
control owned by a different process; it answers from a cached caption,
so a parameter box reads as whatever it held when it was created and
never appears to change. `verify_gui_presets.py` used it at first and
reported every preset as broken — the presets were fine, the test was
lying. `WM_GETTEXT` is marshalled across the process boundary and reports
the truth. Worth knowing before believing any future test that drives
these windows from outside.

## Dependencies

```
USER32  GDI32  COMCTL32  WINMM  COMDLG32  SHELL32  KERNEL32
```

Windows system libraries only. The CRT is static (`/MT`), so there is no
Visual C++ redistributable to install, and no Python, wxPython or
PyInstaller anywhere in the picture.
