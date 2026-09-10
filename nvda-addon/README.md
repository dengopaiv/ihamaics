# IHAMAICS - I Have A Mouth And I Can Scream

SAM (Software Automatic Mouth) as an NVDA screen reader synthesizer addon.

## What is SAM?

SAM was the first commercial all-software speech synthesizer for personal computers, released in 1982 by Don't Ask Software (Mark Barton). It was famous for its distinctive robotic voice and ran on Commodore 64, Apple II, and Atari computers.

This project brings SAM back to life as an accessibility tool for NVDA screen reader users.

## Features

- **Native C engine** - the renderer, parser and reciter are C; the addon loads them through `ctypes`
- **NVDA synthesizer driver** - works as a native NVDA speech synthesizer
- **CMU Pronouncing Dictionary** - 134,000+ words with proper pronunciation
- **Word-level streaming** - minimal latency, words play immediately
- **Punctuation pauses** - natural pauses at commas, periods, etc.
- **Multiple voice presets** - Sam, Elf, Little Robot, Stuffy Guy, and more

## Installation

1. Download `sam-native.zip` and unpack it
2. Double-click `sam.nvda-addon` with NVDA running
3. Accept the installation prompt
4. Restart NVDA
5. Go to NVDA Menu → Preferences → Settings → Speech
6. Select "SAM (Software Automatic Mouth)" as your synthesizer

## Voice Presets

| Voice | Description |
|-------|-------------|
| Sam | Default SAM voice |
| Elf | Higher formants |
| Little Robot | Robotic quality |
| Stuffy Guy | Nasal quality |
| Little Old Lady | Lower pitch |
| Extra-Terrestrial | Unusual formants |

## Credits

This project stands on the shoulders of giants:

- **Original SAM (1982)** - Don't Ask Software (Mark Barton)
- **JavaScript port** - [discordier/sam](https://github.com/discordier/sam)
- **CMU Pronouncing Dictionary** - Carnegie Mellon University
- **Python port & NVDA integration** - Created with Claude Code

## License

SAM is reverse-engineered software whose copyright is held by SoftVoice, Inc.;
it cannot be placed under an open source licence, and neither can this port.
The bundled CMU Pronouncing Dictionary is licensed separately by Carnegie
Mellon University. See [NOTICE.md](../NOTICE.md) for the full attributions,
which also ship inside the built addon.

## Building it

    python nvda-addon/package_addon.py

writes `sam.nvda-addon`. It needs `sam_render-x64.dll` and
`sam_render-x86.dll` in `native/build/` - run `native\build.cmd`
first - and fails rather than shipping an addon that cannot render.

`--python-fallback` builds the older shape instead, with the pure
Python renderer left in as a fallback and a `[python fallback]` marker
in the summary so it is not mistaken for the release. It is there for
working on the port. The released addon has no fallback, so a DLL that
fails to load raises instead of quietly sounding identical but slower.

`python nvda-addon/validate_addon.py` checks a built addon: the
manifest, that every module the driver imports is in the archive, that
the DLLs are the architectures they claim, and that the packaged
engine really renders.

To build the whole release - this addon plus both desktop
executables, into `sam-native.zip` - use `python tools/make_release.py`
from the repository root.

## Technical Details

The synthesizer pipeline:
```
Text → Reciter (text to phonemes) → Parser → Renderer → Audio
```

- **Reciter**: Converts text to phonemes using CMU dictionary with rule-based fallback
- **Parser**: Processes phonemes into frame data
- **Renderer**: Generates 8-bit PCM audio at 22050 Hz

Reciter, parser and renderer all run in C in the released addon. The
Python implementations of each stay in this directory: they are the
reference the C is verified against, over all 126,052 dictionary
words, and they are not shipped.

## Contributing

Contributions welcome! This is an accessibility project - help make it better for screen reader users.
