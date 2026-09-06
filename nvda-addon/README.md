# IHAMAICS - I Have A Mouth And I Can Scream

A pure Python implementation of SAM (Software Automatic Mouth) as an NVDA screen reader synthesizer addon.

## What is SAM?

SAM was the first commercial all-software speech synthesizer for personal computers, released in 1982 by Don't Ask Software (Mark Barton). It was famous for its distinctive robotic voice and ran on Commodore 64, Apple II, and Atari computers.

This project brings SAM back to life as an accessibility tool for NVDA screen reader users.

## Features

- **Complete Python port** of the SAM speech synthesis engine
- **NVDA synthesizer driver** - works as a native NVDA speech synthesizer
- **CMU Pronouncing Dictionary** - 134,000+ words with proper pronunciation
- **Word-level streaming** - minimal latency, words play immediately
- **Punctuation pauses** - natural pauses at commas, periods, etc.
- **Multiple voice presets** - Sam, Elf, Little Robot, Stuffy Guy, and more

## Installation

1. Download `sam.nvda-addon` from the releases
2. Double-click the file with NVDA running
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

## Technical Details

The synthesizer pipeline:
```
Text → Reciter (text to phonemes) → Parser → Renderer → Audio
```

- **Reciter**: Converts text to phonemes using CMU dictionary with rule-based fallback
- **Parser**: Processes phonemes into frame data
- **Renderer**: Generates 8-bit PCM audio at 22050 Hz

## Contributing

Contributions welcome! This is an accessibility project - help make it better for screen reader users.
