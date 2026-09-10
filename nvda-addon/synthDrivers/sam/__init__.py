# SAM (Software Automatic Mouth) NVDA Synthesizer Driver
# Provides the classic 1982 SAM voice for NVDA

import threading
import time

from synthDriverHandler import SynthDriver as BaseSynthDriver, VoiceInfo, synthIndexReached, synthDoneSpeaking
from speech.commands import IndexCommand, CharacterModeCommand, BreakCommand, PitchCommand, RateCommand, VolumeCommand
from autoSettingsUtils.driverSetting import BooleanDriverSetting, NumericDriverSetting
import nvwave
import config
from logHandler import log

from .sam import SAM, VOICE_PRESETS
from .reciter import expand_numbers
from . import cmudict
from . import native


class SynthDriver(BaseSynthDriver):
    """SAM (Software Automatic Mouth) synthesizer driver for NVDA."""

    name = "sam"
    description = "SAM (Software Automatic Mouth)"

    supportedSettings = (
        BaseSynthDriver.VoiceSetting(),
        BaseSynthDriver.RateSetting(),
        BaseSynthDriver.PitchSetting(),
        BaseSynthDriver.InflectionSetting(),
        BaseSynthDriver.VolumeSetting(),
        NumericDriverSetting("mouth", "Mouth", availableInSettingsRing=True),
        NumericDriverSetting("throat", "Throat", availableInSettingsRing=True),
        BooleanDriverSetting("singmode", "Sing mode", defaultVal=False),
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

        # Parsing the 126k-word pronunciation dictionary takes ~150ms and is
        # otherwise paid lazily on the first word spoken, which is the most
        # conspicuous moment possible. Start it now, in parallel with the
        # player setup below.
        cmudict.preload_async()

        # Say which renderer is in use. The native one is roughly 16x
        # faster, and a fallback to Python is inaudible, so it would
        # otherwise be invisible until someone profiled it.
        if native.available():
            log.info("SAM: native renderer active (%s)" % native.library_path())
        else:
            log.info("SAM: native renderer unavailable, using the Python renderer")

        self._sam = SAM()
        self._voice = "sam"
        self._rate = 50  # 0-100 scale
        self._pitch = 50  # 0-100 scale
        self._inflection = 50  # 0-100 scale
        self._volume = 100  # 0-100 scale
        self._mouth = 50  # 0-100 scale, maps to 0-255
        self._throat = 50  # 0-100 scale, maps to 0-255
        self._singmode = False
        # Volume for the utterance being spoken. Prosody commands last
        # for one utterance, so they write here and to the engine, never
        # to the settings behind them - _volume is what NVDA reads back
        # and saves to its config file.
        self._speak_volume = self._volume
        self._speaking = False
        self._cancel_flag = threading.Event()
        self._speech_thread = None

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

    @staticmethod
    def _sam_speed(rate):
        """NVDA's 0-100 rate as SAM's speed: 0-100 maps to roughly 15-150.

        Inverted, because SAM's number is a frame duration: lower is
        faster.
        """
        return max(10, min(255, int(15 + (150 - 15) * (100 - rate) / 100)))

    @staticmethod
    def _sam_pitch(pitch):
        """NVDA's 0-100 pitch as SAM's pitch: 0-100 maps to roughly 20-120.

        Inverted, because SAM's number is a glottal pulse period: lower
        is a higher voice.
        """
        return max(0, min(255, int(20 + (120 - 20) * (100 - pitch) / 100)))

    def _update_sam_params(self):
        """Update SAM parameters based on current settings."""
        # Get base preset values
        preset = VOICE_PRESETS.get(self._voice, VOICE_PRESETS['sam'])

        self._sam.speed = self._sam_speed(self._rate)
        self._sam.pitch = self._sam_pitch(self._pitch)

        # Mouth: 0-100 maps to 0-255
        mouth = int(self._mouth * 255 / 100)
        self._sam.mouth = max(0, min(255, mouth))

        # Throat: 0-100 maps to 0-255
        throat = int(self._throat * 255 / 100)
        self._sam.throat = max(0, min(255, throat))

        # Singmode
        self._sam.singmode = self._singmode

        # Inflection
        self._sam.inflection = self._inflection

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
            # Apply preset's mouth/throat as new base (convert 0-255 to 0-100)
            preset = VOICE_PRESETS[value]
            self._mouth = int(preset['mouth'] * 100 / 255)
            self._throat = int(preset['throat'] * 100 / 255)
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
        self._speak_volume = self._volume

    def _get_inflection(self):
        return self._inflection

    def _set_inflection(self, value):
        self._inflection = max(0, min(100, value))
        self._sam.inflection = self._inflection

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

    @staticmethod
    def _command_value(command, fallback):
        """The absolute 0-100 setting a prosody command asks for.

        NVDA computes newValue from the user's configured setting, so it
        is already absolute rather than a delta on whatever the engine
        happens to be doing now: PitchCommand(offset=30) means "the
        configured pitch plus 30", and a bare PitchCommand() means "back
        to the configured pitch". NVDA brackets every capital with that
        pair when raise-pitch-for-capitals is on.

        Reading .offset instead, and skipping the command when it was
        zero, threw away the half of the pair that puts the voice back.

        A command NVDA cannot price - no current synth, a config section
        that is not there - falls back to the setting itself, because a
        wrong pitch for one utterance beats a silent one.
        """
        try:
            value = command.newValue
        except Exception as e:
            log.debugWarning(
                "SAM: cannot read %s.newValue: %s" % (type(command).__name__, e))
            value = None
        if value is None:
            value = fallback
        return max(0, min(100, int(value)))

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

        # Prosody commands are scoped to one utterance. Put the
        # configured values back before this one starts, so a sequence
        # that ended without its closing PitchCommand() cannot colour
        # everything spoken afterwards.
        self._update_sam_params()
        self._speak_volume = self._volume

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
                    time.sleep(item.time / 1000.0 if item.time else 0.1)

                elif isinstance(item, PitchCommand):
                    # Speak what is buffered first: the change applies to
                    # what follows it, not to text already accumulated.
                    if text_buffer:
                        self._speak_text(''.join(text_buffer))
                        text_buffer = []
                    self._sam.pitch = self._sam_pitch(
                        self._command_value(item, self._pitch))

                elif isinstance(item, RateCommand):
                    if text_buffer:
                        self._speak_text(''.join(text_buffer))
                        text_buffer = []
                    self._sam.speed = self._sam_speed(
                        self._command_value(item, self._rate))

                elif isinstance(item, VolumeCommand):
                    if text_buffer:
                        self._speak_text(''.join(text_buffer))
                        text_buffer = []
                    self._speak_volume = self._command_value(item, self._volume)

            # Speak any remaining text
            if text_buffer and not self._cancel_flag.is_set():
                self._speak_text(''.join(text_buffer))

        except Exception as e:
            log.error(f"SAM speech error: {e}")
        finally:
            self._speaking = False

    def _speak_text(self, text):
        """Synthesize and play text with word-level streaming for low latency."""
        if not text.strip():
            return

        try:
            # Expand numbers to words first: "60" -> "sixty"
            text = expand_numbers(text)

            # Split into words for streaming
            words = text.split()

            for word in words:
                if self._cancel_flag.is_set():
                    return

                # Skip empty words
                word = word.strip()
                if not word:
                    continue

                # Generate audio for this word
                audio_data = self._sam.speak(word)
                if audio_data is None or len(audio_data) == 0:
                    continue

                # Apply volume if needed
                if self._speak_volume < 100:
                    audio_data = self._apply_volume(audio_data)

                # Apply fade in/out to avoid clicks at word boundaries
                audio_data = self._fade_audio(audio_data)

                # Feed audio to player immediately - starts playing while we synthesize next word
                self._player.feed(audio_data, len(audio_data))

            # Wait for all audio to finish playing
            if not self._cancel_flag.is_set():
                self._player.idle()

        except Exception as e:
            log.error(f"SAM synthesis error: {e}")

    def _apply_volume(self, data):
        """Apply volume scaling to audio data."""
        if self._speak_volume >= 100:
            return data

        scale = self._speak_volume / 100.0
        result = bytearray(len(data))
        for i, sample in enumerate(data):
            # Convert unsigned 8-bit to signed, scale, convert back
            signed = sample - 128
            scaled = int(signed * scale)
            result[i] = max(0, min(255, scaled + 128))
        return bytes(result)

    def _fade_audio(self, data, fade_ms=5):
        """Apply fade in/out to avoid clicks at word boundaries."""
        if len(data) < 20:
            return data

        samples = int(22050 * fade_ms / 1000)  # ~110 samples for 5ms
        samples = min(samples, len(data) // 4)  # Don't fade more than 1/4 of audio

        result = bytearray(data)

        # Fade in (from silence at 128 to full)
        for i in range(samples):
            scale = i / samples
            result[i] = int(128 + (result[i] - 128) * scale)

        # Fade out (from full to silence at 128)
        for i in range(samples):
            idx = len(result) - 1 - i
            scale = i / samples
            result[idx] = int(128 + (result[idx] - 128) * scale)

        return bytes(result)

    def cancel(self):
        """Cancel current speech."""
        self._cancel_flag.set()
        self._speaking = False
        if self._player:
            self._player.stop()
        if self._speech_thread and self._speech_thread.is_alive():
            # Best effort: the thread re-checks _cancel_flag between words, so
            # it exits within one word's synthesis. Measured worst case after
            # the renderer optimisation is ~95ms ("incomprehensibility" at the
            # slowest rate), so 0.5s only ever added dead time on the NVDA
            # main thread. See docs/c-engine-port.md.
            self._speech_thread.join(timeout=0.2)

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
