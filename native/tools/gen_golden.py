#!/usr/bin/env python3
"""Dump golden vectors from the Python renderer.

The C port must reproduce these byte for byte. Run from the repository
root; writes native/tests/golden/.

    python native/tools/gen_golden.py

Each case is stored as:
    <name>.in.json   parser output + voice params (the render() inputs)
    <name>.pcm       expected raw 8-bit unsigned PCM, 22050 Hz mono
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'nvda-addon', 'synthDrivers', 'sam'))

from reciter import text_to_phonemes      # noqa: E402
from parser import parse                  # noqa: E402
from renderer import render               # noqa: E402

OUT = os.path.join(ROOT, 'native', 'tests', 'golden')

# Spread over the parameter space the driver actually reaches: the speed
# extremes come from SynthDriver._update_sam_params (10..255 after clamping),
# the presets from VOICE_PRESETS, singmode and inflection from the settings.
CASES = [
    ('hello_default',      'hello',        dict(pitch=64,  speed=72,  mouth=128, throat=128)),
    ('a_fast',             'a',            dict(pitch=64,  speed=10,  mouth=128, throat=128)),
    ('a_slow',             'a',            dict(pitch=64,  speed=255, mouth=128, throat=128)),
    ('elf_preset',         'testing',      dict(pitch=64,  speed=72,  mouth=160, throat=110)),
    ('et_preset',          'testing',      dict(pitch=64,  speed=100, mouth=200, throat=150)),
    ('old_lady_preset',    'testing',      dict(pitch=32,  speed=82,  mouth=145, throat=145)),
    ('pitch_floor',        'zero',         dict(pitch=0,   speed=72,  mouth=128, throat=128)),
    ('pitch_ceiling',      'high',         dict(pitch=255, speed=72,  mouth=128, throat=128)),
    ('mouth_throat_zero',  'edge',         dict(pitch=64,  speed=72,  mouth=0,   throat=0)),
    ('mouth_throat_max',   'edge',         dict(pitch=64,  speed=72,  mouth=255, throat=255)),
    ('singmode',           'lalala',       dict(pitch=64,  speed=72,  mouth=128, throat=128, singmode=True)),
    ('monotone',           'flat',         dict(pitch=64,  speed=72,  mouth=128, throat=128, inflection=0)),
    ('dramatic',           'wow',          dict(pitch=64,  speed=72,  mouth=128, throat=128, inflection=100)),
    ('question',           'really?',      dict(pitch=64,  speed=72,  mouth=128, throat=128)),
    ('long_word',          'incomprehensibility',
                                           dict(pitch=64,  speed=72,  mouth=128, throat=128)),
    ('sentence',           'the quick brown fox',
                                           dict(pitch=64,  speed=72,  mouth=128, throat=128)),
]


def main():
    os.makedirs(OUT, exist_ok=True)
    manifest = []
    for name, text, params in CASES:
        phonemes = text_to_phonemes(text)
        if phonemes is False:
            raise SystemExit(f'{name}: reciter rejected {text!r}')
        phoneme_list = parse(phonemes)
        if not phoneme_list:
            raise SystemExit(f'{name}: parser rejected {phonemes!r}')

        p = dict(pitch=64, speed=72, mouth=128, throat=128,
                 singmode=False, inflection=50)
        p.update(params)
        audio = render(phoneme_list, p['pitch'], p['mouth'], p['throat'],
                       p['speed'], p['singmode'], p['inflection'])

        with open(os.path.join(OUT, name + '.pcm'), 'wb') as f:
            f.write(bytes(audio))
        spec = {'text': text, 'phonemes': phonemes,
                'phoneme_list': phoneme_list, 'params': p,
                'expected_samples': len(audio)}
        with open(os.path.join(OUT, name + '.in.json'), 'w', encoding='utf-8') as f:
            json.dump(spec, f, indent=2)

        manifest.append({'name': name, 'samples': len(audio),
                         'ms': round(len(audio) / 22050 * 1000, 1)})
        print(f'  {name:20} {len(audio):8} samples  '
              f'{len(audio)/22050*1000:8.1f} ms')

    with open(os.path.join(OUT, 'manifest.json'), 'w', encoding='utf-8') as f:
        json.dump(manifest, f, indent=2)
    total = sum(m['samples'] for m in manifest)
    print(f'\n{len(manifest)} cases, {total} samples '
          f'({total/1024:.0f} KiB) -> {os.path.relpath(OUT, ROOT)}')


if __name__ == '__main__':
    main()
