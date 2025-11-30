#!/usr/bin/env python3
"""
Test script for SAM Python port.
Run this to verify the synthesizer works before installing in NVDA.
"""

import sys
import os

# Add the sam module directory directly to avoid loading __init__.py with NVDA dependencies
sam_module_path = os.path.join(os.path.dirname(__file__), 'synthDrivers', 'sam')
sys.path.insert(0, sam_module_path)

# Import directly from the module files, not the package
from sam import SAM, text_to_phonemes, VOICE_PRESETS


def test_text_to_phonemes():
    """Test text to phoneme conversion."""
    print("Testing text to phoneme conversion...")

    test_cases = [
        ("Hello", True),
        ("World", True),
        ("Hello World", True),
        ("Test 123", True),
        ("How are you?", True),
    ]

    for text, should_succeed in test_cases:
        result = text_to_phonemes(text)
        success = result is not False and result is not None
        status = "PASS" if success == should_succeed else "FAIL"
        print(f"  [{status}] '{text}' -> {repr(result)[:50]}...")

    print()


def test_sam_synthesis():
    """Test audio synthesis."""
    print("Testing SAM audio synthesis...")

    sam = SAM()

    test_texts = [
        "Hello",
        "Hello World",
        "This is a test.",
        "How are you today?",
    ]

    for text in test_texts:
        audio = sam.speak(text)
        if audio and len(audio) > 0:
            print(f"  [PASS] '{text}' -> {len(audio)} bytes of audio")
        else:
            print(f"  [FAIL] '{text}' -> No audio generated")

    print()


def test_wav_generation():
    """Test WAV file generation."""
    print("Testing WAV file generation...")

    sam = SAM()
    wav_data = sam.wav("Hello World")

    if wav_data and len(wav_data) > 44:  # WAV header is 44 bytes
        # Check WAV header
        if wav_data[:4] == b'RIFF' and wav_data[8:12] == b'WAVE':
            print(f"  [PASS] Generated valid WAV file: {len(wav_data)} bytes")

            # Save test file
            test_file = os.path.join(os.path.dirname(__file__), 'test_output.wav')
            with open(test_file, 'wb') as f:
                f.write(wav_data)
            print(f"  [INFO] Saved test WAV to: {test_file}")
        else:
            print(f"  [FAIL] Invalid WAV header")
    else:
        print(f"  [FAIL] WAV generation failed")

    print()


def test_voice_presets():
    """Test voice presets."""
    print("Testing voice presets...")

    for preset_name in VOICE_PRESETS.keys():
        sam = SAM.with_preset(preset_name)
        audio = sam.speak("Test")
        if audio and len(audio) > 0:
            print(f"  [PASS] Preset '{preset_name}': {len(audio)} bytes")
        else:
            print(f"  [FAIL] Preset '{preset_name}': No audio")

    print()


def test_parameter_ranges():
    """Test parameter edge cases."""
    print("Testing parameter ranges...")

    sam = SAM()

    # Test pitch range
    for pitch in [0, 32, 64, 128, 200, 255]:
        sam.pitch = pitch
        audio = sam.speak("Hi")
        status = "PASS" if audio and len(audio) > 0 else "FAIL"
        print(f"  [{status}] pitch={pitch}")

    # Test speed range
    for speed in [20, 50, 72, 100, 150, 200]:
        sam.speed = speed
        audio = sam.speak("Hi")
        status = "PASS" if audio and len(audio) > 0 else "FAIL"
        print(f"  [{status}] speed={speed}")

    print()


def main():
    print("=" * 60)
    print("SAM Python Port - Test Suite")
    print("=" * 60)
    print()

    test_text_to_phonemes()
    test_sam_synthesis()
    test_wav_generation()
    test_voice_presets()
    test_parameter_ranges()

    print("=" * 60)
    print("Tests complete!")
    print("If test_output.wav was created, try playing it to hear SAM.")
    print("=" * 60)


if __name__ == '__main__':
    main()
