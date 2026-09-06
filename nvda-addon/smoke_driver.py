#!/usr/bin/env python3
"""Import and exercise the NVDA synth driver outside NVDA.

synthDrivers/sam/__init__.py imports synthDriverHandler, nvwave, config and
friends, so it normally cannot run anywhere but inside NVDA, which means
the driver module is the one part of the addon that never gets executed
before install. This stubs those modules just far enough to import the
driver, construct it, and push a speech sequence through it, capturing the
audio that would have gone to the sound card.

It is not a substitute for testing in NVDA. It catches the cheap failures:
import errors, typos in the settings declarations, exceptions in
__init__ or the speech thread.

    python nvda-addon/smoke_driver.py
"""
import os
import sys
import types
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))

# Defaults to the working tree; pass a synthDrivers directory (for example
# one extracted from a built .nvda-addon) to test what actually ships.
SAM_PKG = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 \
    else os.path.join(HERE, 'synthDrivers')


# --- stub out the NVDA runtime ------------------------------------------

class _Setting:
    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs


def _make_stub_modules(captured):
    synth = types.ModuleType('synthDriverHandler')

    class SynthDriver:
        def __init__(self):
            pass

        @classmethod
        def VoiceSetting(cls, *a, **k):
            return _Setting('voice')

        @classmethod
        def RateSetting(cls, *a, **k):
            return _Setting('rate')

        @classmethod
        def PitchSetting(cls, *a, **k):
            return _Setting('pitch')

        @classmethod
        def InflectionSetting(cls, *a, **k):
            return _Setting('inflection')

        @classmethod
        def VolumeSetting(cls, *a, **k):
            return _Setting('volume')

    class VoiceInfo:
        def __init__(self, id_, name, language=None):
            self.id, self.name, self.language = id_, name, language

    class _Notifier:
        def notify(self, **kwargs):
            pass

    synth.SynthDriver = SynthDriver
    synth.VoiceInfo = VoiceInfo
    synth.synthIndexReached = _Notifier()
    synth.synthDoneSpeaking = _Notifier()

    commands = types.ModuleType('speech.commands')

    class _Cmd:
        def __init__(self, **kw):
            self.__dict__.update(kw)

    for name in ('IndexCommand', 'CharacterModeCommand', 'LangChangeCommand',
                 'BreakCommand', 'PitchCommand', 'RateCommand', 'VolumeCommand'):
        commands.__dict__[name] = type(name, (_Cmd,), {})
    speech = types.ModuleType('speech')
    speech.commands = commands

    ds = types.ModuleType('autoSettingsUtils.driverSetting')
    ds.BooleanDriverSetting = _Setting
    ds.NumericDriverSetting = _Setting
    autoset = types.ModuleType('autoSettingsUtils')
    autoset.driverSetting = ds

    nvwave = types.ModuleType('nvwave')

    class WavePlayer:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
            self.closed = False

        def feed(self, data, size=None):
            captured.append(bytes(data))

        def idle(self):
            pass

        def stop(self):
            pass

        def pause(self, switch):
            pass

        def close(self):
            self.closed = True

    nvwave.WavePlayer = WavePlayer

    config = types.ModuleType('config')
    config.conf = {'speech': {'outputDevice': 'default'},
                   'audio': {'outputDevice': 'default'}}

    logmod = types.ModuleType('logHandler')

    class _Log:
        def __init__(self):
            self.lines = []

        def info(self, msg, *a):
            self.lines.append(('info', str(msg)))

        def error(self, msg, *a):
            self.lines.append(('error', str(msg)))

        def warning(self, msg, *a):
            self.lines.append(('warning', str(msg)))

        debug = info
    logmod.log = _Log()

    return {
        'synthDriverHandler': synth,
        'speech': speech,
        'speech.commands': commands,
        'autoSettingsUtils': autoset,
        'autoSettingsUtils.driverSetting': ds,
        'nvwave': nvwave,
        'config': config,
        'logHandler': logmod,
    }


def main():
    captured = []
    stubs = _make_stub_modules(captured)
    sys.modules.update(stubs)
    sys.path.insert(0, SAM_PKG)

    print('importing the driver...')
    from sam import SynthDriver  # noqa: E402  (package dir on sys.path)
    print(f'  ok    imported, name={SynthDriver.name!r} '
          f'description={SynthDriver.description!r}')
    print(f'  ok    check() -> {SynthDriver.check()}')
    print(f'  ok    {len(SynthDriver.supportedSettings)} settings, '
          f'{len(SynthDriver.supportedCommands)} commands')

    print('\nconstructing...')
    synth = SynthDriver()
    for level, line in stubs['logHandler'].log.lines:
        print(f'  log[{level}] {line}')

    voices = synth._getAvailableVoices()
    print(f'  ok    {len(voices)} voices: {", ".join(sorted(voices))}')

    print('\nspeaking...')
    cmds = stubs['speech.commands']
    seq = ['Hello world. ',
           cmds.IndexCommand(index=1),
           'This is SAM speaking through the native renderer, ',
           cmds.BreakCommand(time=10),
           cmds.RateCommand(offset=5),
           'faster now. ',
           cmds.PitchCommand(offset=10),
           cmds.VolumeCommand(offset=-10),
           'and finally, 42 units.']
    synth.speak(seq)

    deadline = time.time() + 30
    while synth.isSpeaking and time.time() < deadline:
        time.sleep(0.05)

    total = sum(len(b) for b in captured)
    print(f'  ok    {len(captured)} audio chunks, {total} bytes '
          f'({total / 22050:.2f}s of speech)')
    for level, line in stubs['logHandler'].log.lines:
        if level == 'error':
            print(f'  FAIL  log error: {line}')
            return 1

    print('\ncancelling mid-utterance...')
    synth.speak(['A much longer utterance that we intend to interrupt '
                 'before it has any chance of finishing properly.'])
    time.sleep(0.05)
    t0 = time.time()
    synth.cancel()
    print(f'  ok    cancel() returned in {(time.time() - t0) * 1000:.0f} ms')

    print('\nsetting round-trip...')
    for attr, value in (('rate', 90), ('pitch', 20), ('volume', 50),
                        ('inflection', 0), ('mouth', 10), ('throat', 90),
                        ('singmode', True), ('voice', 'elf')):
        setattr(synth, '_' + attr, getattr(synth, '_' + attr))
        getattr(synth, '_set_' + attr)(value)
        got = getattr(synth, '_get_' + attr)()
        print(f'  ok    {attr:10} -> {got!r}')

    synth.speak(['Elf voice at speed.'])
    deadline = time.time() + 30
    while synth.isSpeaking and time.time() < deadline:
        time.sleep(0.05)

    synth.terminate()
    print('  ok    terminate()')

    errors = [l for lvl, l in stubs['logHandler'].log.lines if lvl == 'error']
    print()
    if errors:
        for e in errors:
            print(f'FAIL  {e}')
        return 1
    print('driver smoke test passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
