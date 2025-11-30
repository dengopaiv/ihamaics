# SAM (Software Automatic Mouth) NVDA Synthesizer Driver
# Provides the classic 1982 SAM voice for NVDA

import threading
import wave
import io
import os
import tempfile
import re
import time

from synthDriverHandler import SynthDriver, VoiceInfo, synthIndexReached, synthDoneSpeaking
from speech.commands import IndexCommand, CharacterModeCommand, LangChangeCommand, BreakCommand, PitchCommand, RateCommand, VolumeCommand
import nvwave
import config
from logHandler import log

from .sam import SAM, VOICE_PRESETS, text_to_phonemes


def split_for_streaming(text):
    """Split text into words, numbers, and punctuation for streaming synthesis."""
    # Split into words (with apostrophes), numbers, and everything else
    tokens = re.findall(r"[A-Za-z']+|[0-9]+|[^A-Za-z0-9']+", text)
    return [t for t in tokens if t.strip()]


# Pause durations in seconds for punctuation marks
PUNCTUATION_PAUSES = {
    '.': 0.3,   # Period - sentence end
    '?': 0.3,   # Question mark
    '!': 0.3,   # Exclamation
    ',': 0.15,  # Comma - clause break
    ';': 0.15,  # Semicolon
    ':': 0.15,  # Colon
}


class SynthDriver(SynthDriver):
    """SAM (Software Automatic Mouth) synthesizer driver for NVDA."""

    name = "sam"
    description = "SAM (Software Automatic Mouth)"

    supportedSettings = (
        SynthDriver.VoiceSetting(),
        SynthDriver.RateSetting(),
        SynthDriver.PitchSetting(),
        SynthDriver.VolumeSetting(),
        SynthDriver.NumericSetting("mouth", "Mouth", minStep=1),
        SynthDriver.NumericSetting("throat", "Throat", minStep=1),
        SynthDriver.BooleanSetting("singmode", "Sing mode"),
    )

    supportedCommands = {
        IndexCommand,
        CharacterModeCommand,
        PitchCommand,
        RateCommand,
        VolumeCommand,
        BreakCommand,
    }

    supportedNotifications = {synthIndexReached, synthDoneSpeaking}

    @classmethod
    def check(cls):
        """Check if this synth is available."""
        return True

    def __init__(self):
        super().__init__()
        self._sam = SAM()
        self._voice = "sam"
        self._rate = 50  # 0-100 scale
        self._pitch = 50  # 0-100 scale
        self._volume = 100  # 0-100 scale
        self._mouth = 50  # 0-100 scale, maps to 0-255
        self._throat = 50  # 0-100 scale, maps to 0-255
        self._singmode = False
        self._speaking = False
        self._cancel_flag = threading.Event()
        self._speech_thread = None
        self._index_callback = None

        # Create audio player with NVDA's configured output device
        try:
            outputDevice = config.conf['speech']['outputDevice']
        except:
            outputDevice = config.conf["audio"]["outputDevice"]
        self._player = nvwave.WavePlayer(
            channels=1,
            samplesPerSec=22050,
            bitsPerSample=8,
            outputDevice=outputDevice
        )

        self._update_sam_params()

    def terminate(self):
        """Clean up when synth is terminated."""
        self.cancel()
        if self._player:
            self._player.close()
            self._player = None
        self._sam = None

    def _update_sam_params(self):
        """Update SAM parameters based on current settings."""
        # Get base preset values
        preset = VOICE_PRESETS.get(self._voice, VOICE_PRESETS['sam'])

        # Apply rate (speed): 0-100 maps to roughly 40-150
        # Lower value = faster speech
        speed = int(40 + (150 - 40) * (100 - self._rate) / 100)
        self._sam.speed = max(20, min(255, speed))

        # Apply pitch: 0-100 maps to roughly 20-120
        pitch = int(20 + (120 - 20) * self._pitch / 100)
        self._sam.pitch = max(0, min(255, pitch))

        # Mouth: 0-100 maps to 0-255
        mouth = int(self._mouth * 255 / 100)
        self._sam.mouth = max(0, min(255, mouth))

        # Throat: 0-100 maps to 0-255
        throat = int(self._throat * 255 / 100)
        self._sam.throat = max(0, min(255, throat))

        # Singmode
        self._sam.singmode = self._singmode

    def _getAvailableVoices(self):
        """Return available voices."""
        voices = {}
        for name in VOICE_PRESETS.keys():
            display_name = name.replace('_', ' ').title()
            voices[name] = VoiceInfo(name, display_name, "en")
        return voices

    def _get_voice(self):
        return self._voice

    def _set_voice(self, value):
        if value in VOICE_PRESETS:
            self._voice = value
            self._update_sam_params()

    def _get_rate(self):
        return self._rate

    def _set_rate(self, value):
        self._rate = max(0, min(100, value))
        self._update_sam_params()

    def _get_pitch(self):
        return self._pitch

    def _set_pitch(self, value):
        self._pitch = max(0, min(100, value))
        self._update_sam_params()

    def _get_volume(self):
        return self._volume

    def _set_volume(self, value):
        self._volume = max(0, min(100, value))

    def _get_mouth(self):
        return self._mouth

    def _set_mouth(self, value):
        self._mouth = max(0, min(100, value))
        self._update_sam_params()

    def _get_throat(self):
        return self._throat

    def _set_throat(self, value):
        self._throat = max(0, min(100, value))
        self._update_sam_params()

    def _get_singmode(self):
        return self._singmode

    def _set_singmode(self, value):
        self._singmode = value
        self._update_sam_params()

    def speak(self, speechSequence):
        """
        Speak a sequence of text and commands.

        Args:
            speechSequence: List of text strings and speech commands
        """
        self.cancel()
        self._cancel_flag.clear()

        # Start speech in a separate thread to not block NVDA
        self._speech_thread = threading.Thread(target=self._speak_thread, args=(speechSequence,))
        self._speech_thread.daemon = True
        self._speech_thread.start()

    def _speak_thread(self, speechSequence):
        """Background thread for speech synthesis."""
        self._speaking = True
        text_buffer = []
        pending_index = None

        try:
            for item in speechSequence:
                if self._cancel_flag.is_set():
                    break

                if isinstance(item, str):
                    text_buffer.append(item)

                elif isinstance(item, IndexCommand):
                    # Speak accumulated text before the index
                    if text_buffer:
                        self._speak_text(''.join(text_buffer))
                        text_buffer = []

                    if self._cancel_flag.is_set():
                        break

                    # Notify that we reached this index
                    synthIndexReached.notify(synth=self, index=item.index)

                elif isinstance(item, CharacterModeCommand):
                    # For character mode, speak accumulated text first
                    if text_buffer:
                        self._speak_text(''.join(text_buffer))
                        text_buffer = []
                    # Character mode doesn't change much for SAM

                elif isinstance(item, BreakCommand):
                    # Speak accumulated text, then pause
                    if text_buffer:
                        self._speak_text(''.join(text_buffer))
                        text_buffer = []
                    # Brief pause (SAM doesn't have native pause support)
                    import time
                    time.sleep(item.time / 1000.0 if item.time else 0.1)

                elif isinstance(item, PitchCommand):
                    # Temporarily adjust pitch
                    if item.offset:
                        self._sam.pitch = max(0, min(255, self._sam.pitch + item.offset))

                elif isinstance(item, RateCommand):
                    # Temporarily adjust rate
                    if item.offset:
                        speed = self._sam.speed - item.offset  # Inverted: higher rate = lower speed value
                        self._sam.speed = max(20, min(255, speed))

                elif isinstance(item, VolumeCommand):
                    # Adjust volume
                    if item.offset:
                        self._volume = max(0, min(100, self._volume + item.offset))

            # Speak any remaining text
            if text_buffer and not self._cancel_flag.is_set():
                self._speak_text(''.join(text_buffer))

        except Exception as e:
            log.error(f"SAM speech error: {e}")
        finally:
            self._speaking = False

    def _speak_text(self, text):
        """Synthesize and play text with word-level streaming and punctuation pauses."""
        if not text.strip():
            return

        try:
            # Split into words for streaming - each word synthesized and played immediately
            tokens = split_for_streaming(text)

            for token in tokens:
                if self._cancel_flag.is_set():
                    return

                # Check if token is punctuation that needs a pause
                stripped = token.strip()
                if stripped in PUNCTUATION_PAUSES:
                    # Wait for current audio to finish, then pause
                    self._player.idle()
                    time.sleep(PUNCTUATION_PAUSES[stripped])
                    continue

                # Skip non-word, non-number tokens (other punctuation like quotes, dashes)
                if not re.match(r"[A-Za-z0-9']", token):
                    continue

                # Generate raw PCM audio for this word (8-bit unsigned, 22050 Hz mono)
                audio_data = self._sam.speak(token)
                if audio_data is None or len(audio_data) == 0:
                    continue

                # Apply volume if needed
                if self._volume < 100:
                    audio_data = self._apply_volume(audio_data)

                # Feed audio to player immediately - starts playing while we synthesize next word
                self._player.feed(audio_data, len(audio_data))

            # Wait for all audio to finish playing
            if not self._cancel_flag.is_set():
                self._player.idle()

        except Exception as e:
            log.error(f"SAM synthesis error: {e}")

    def _apply_volume(self, data):
        """Apply volume scaling to audio data."""
        if self._volume >= 100:
            return data

        scale = self._volume / 100.0
        result = bytearray(len(data))
        for i, sample in enumerate(data):
            # Convert unsigned 8-bit to signed, scale, convert back
            signed = sample - 128
            scaled = int(signed * scale)
            result[i] = max(0, min(255, scaled + 128))
        return bytes(result)

    def cancel(self):
        """Cancel current speech."""
        self._cancel_flag.set()
        self._speaking = False
        if self._player:
            self._player.stop()
        if self._speech_thread and self._speech_thread.is_alive():
            self._speech_thread.join(timeout=0.5)

    def pause(self, switch):
        """
        Pause or resume speech.

        Args:
            switch: True to pause, False to resume
        """
        if self._player:
            self._player.pause(switch)

    @property
    def isSpeaking(self):
        """Return whether the synth is currently speaking."""
        return self._speaking
