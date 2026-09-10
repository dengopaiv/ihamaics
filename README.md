# IHAMAICS — I Have A Mouth And I Can Scream

SAM (Software Automatic Mouth), the 1982 Commodore 64 speech
synthesizer, as an NVDA screen reader voice and a small desktop app.
It was ported to Python first and then to C. Both ports are here;
the C one is what ships.

SAM was the first commercial all-software speech synthesizer for
home computers, published by Don't Ask Software (Mark Barton). It
needed no hardware and it sounded like nothing else. This project
brings that voice back as a working accessibility tool.

## What is in here

| Path | What it is |
|------|------------|
| `sam-native.zip` | **The release** — the addon and the desktop app, both native |
| `nvda-addon/` | Source of the NVDA synthesizer addon |
| `native/` | The C engine: renderer, parser, reciter, dictionary |
| `gui-native/` | `sam_gui.exe` — the desktop app with no Python behind it |
| `tools/make_release.py` | Builds `sam-native.zip` |
| `sam_gui.py` | wxPython app: type text, preview, save a WAV |
| `src/`, `test/`, `dist/` | The upstream JavaScript port, kept as reference |
| `docs/` | The original 1982 SAM manual and scans |

`sam-native.zip` is the only archive in the repository and the only
thing a user has to download. Everything in it is native: the addon
carries the C renderer with no Python fallback, and `sam_gui.exe` has
no Python behind it at all, so neither one asks for a runtime first.

The Python addon and `sam_gui.py` are not in the archive and are not
released as binaries. They stay here as source — they are the
reference the C engine is checked against, word for word, and they
still run from a checkout.

The engine in `nvda-addon/synthDrivers/sam/` is a direct port of the
JavaScript in `src/` — every module names the `.es6` file it came
from — so the JavaScript tree stays here as the reference
implementation and test corpus.

## The NVDA addon

Needs NVDA 2023.1 or newer; last tested on 2025.3.2.

1. Download `sam-native.zip` and unpack it
2. Double-click `sam.nvda-addon` with NVDA running, accept the prompt
3. Restart NVDA
4. NVDA menu → Preferences → Settings → Speech
5. Choose "SAM (Software Automatic Mouth)"

Rate, pitch, inflection and volume behave as usual. Mouth, Throat
and Sing mode are added to the settings ring.

Speech is streamed a word at a time, so it starts talking before
the whole utterance is synthesized. Pronunciation comes from the
CMU Pronouncing Dictionary (134k words) with SAM's own rule-based
reciter as the fallback.

Rebuild the release from source — it repackages the addon,
validates it, and writes the archive:

    python tools/make_release.py

It needs the DLLs and both executables built first, and names the
command for whatever is missing. For the addon on its own:

    python nvda-addon/package_addon.py

which builds the native addon. Add `--python-fallback` for a build
that keeps the Python renderer in as a fallback; that variant is for
working on the port, and is not what gets released.

More detail in [nvda-addon/README.md](nvda-addon/README.md).

## The desktop app

Two builds of the same application, and they produce byte-identical
audio for the same settings.

**Native** — one self-contained executable, no Python, no wxPython,
no runtime to install first. Prebuilt for both architectures in
`sam-native.zip`; to build it yourself:

    python native\tools\gen_dict.py
    gui-native\build.cmd x64

That writes `gui-native/build/sam_gui-x64.exe` (about 4 MB, most of
it the pronunciation dictionary). Everything the Python app has,
plus four things the engine always supported and no GUI exposed:
phoneme mode, a Convert to Phonemes button, sing mode, and a voice
preset dropdown. See [docs/native-gui.md](docs/native-gui.md).

**Python** — source only, run from a checkout:

    python sam_gui.py

Type text, set Speed, Pitch, Mouth, Throat and Inflection, then
Preview or Render to WAV. Needs `wxPython`. `pyinstaller
sam_gui.spec` still builds a standalone executable from it, but that
build is not released — the native one is.

## The C engine

`native/` holds a C port of the whole engine. The renderer came
first, because it was 99.7% of synthesis cost and the addon loads it
through `ctypes` for a 28.8x speedup — see
[docs/c-engine-port.md](docs/c-engine-port.md). The reciter, parser
and dictionary followed, because a Python-free application needs
them — see [docs/native-gui.md](docs/native-gui.md).

Both halves are verified against the Python by differential testing
over the whole domain rather than by sampling: every one of the
126,052 dictionary words goes through the parser, the rule engine
and the front end, and the results must be identical.

    native\build.cmd                    :: the DLLs the addon loads
    python native\tools\verify_text.py  :: front end vs Python
    python native\tools\verify_gui.py   :: the exe vs the Python app

## Voice presets

The presets from the original manual. The native app offers them in
a dropdown; the addon and `sam_gui.py` carry the same numbers but
have no control for choosing one:

```
DESCRIPTION          SPEED     PITCH     THROAT    MOUTH
Elf                   72        64        110       160
Little Robot          92        60        190       190
Stuffy Guy            82        72        110       105
Little Old Lady       82        32        145       145
Extra-Terrestrial    100        64        150       200
SAM                   72        64        128       128
```

## The JavaScript library

`src/` holds the vanilla JavaScript port this project was ported
from. It still builds and tests on its own:

    yarn install
    yarn test
    yarn build

```javascript
import SamJs from 'sam-js';

let sam = new SamJs();

// Play "Hello world" over the speaker.
// This returns a Promise resolving after playback has finished.
sam.speak('Hello world');

// Generate a wave file containing "Hello world" and download it.
sam.download('Hello world');

// Render the passed text as 8bit wave buffer array (Uint8Array).
const buf8 = sam.buf8('Hello world');

// Render the passed text as 32bit wave buffer array (Float32Array).
const buf32 = sam.buf32('Hello world');
```

`index.html`, `guess.html` and `star-spangled-banner.html` are the
upstream browser demos.

## Original docs

A copy of the original manual is bundled here, see the
[manual](docs/manual.md) in the [docs](docs) directory.

## Based on

This project stands on other people's work:

- **SAM (1982)** — Don't Ask Software, by Mark Barton
- **[s-macke/SAM](https://github.com/s-macke/SAM)** — the C
  adaptation by Stefan Macke
- **[discordier/sam](https://github.com/discordier/sam)** — the
  JavaScript port by Christian Schiffler, which `src/` is a copy
  of and which the Python engine was ported from, with
  refactorings by [Vidar Hokstad](https://github.com/vidarh/SAM)
  and [8BitPimp](https://github.com/8BitPimp/SAM)
- **CMU Pronouncing Dictionary** — Carnegie Mellon University

Analysis of S.A.M. in general is in Artyom Skrobov's (@tyomitch)
blog, https://habr.com/ru/post/500764/ (Russian), or the
[translated version](https://habr-com.translate.goog/ru/post/500764/?_x_tr_sl=auto&_x_tr_tl=en).
Further background at
[retrobits.net](http://www.retrobits.net/atari/sam.shtml).

## License

The software is a reverse-engineered version of a commercial
program published more than 30 years ago. The current copyright
holder is SoftVoice, Inc. (www.text2speech.com)

Any attempt to contact the company failed. The website was last
updated in 2009. The status of the original software can therefore
best be described as Abandonware
(http://en.wikipedia.org/wiki/Abandonware)

As long as this is the case the code cannot be put under any
specific open source software license. Neither this project nor
its maintainers hold copyright in SAM or purport to license it.
Use it at your own risk.

The bundled CMU Pronouncing Dictionary is separately licensed by
Carnegie Mellon University under BSD-2-Clause terms. The full
position is in [LICENSE](LICENSE), and per-component attributions
are in [NOTICE.md](NOTICE.md).

## Contact

If you have questions don't hesitate to ask. If you discovered
some new knowledge about the code, please file an issue.
