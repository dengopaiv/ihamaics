# Renderer for a native-only build.
#
# package_addon.py --native-only ships this file as renderer.py and omits
# the pure Python renderer and renderer_tables.py entirely, so the C
# library is the only thing that can produce audio.
#
# The point of such a build is that a fallback cannot hide a problem: if
# the library does not load there is nothing to fall back to, so this
# raises loudly instead of quietly sounding identical but slower. Use the
# standard build for everyday use; use this one to prove which engine is
# actually doing the work.

try:
    from . import native
except ImportError:
    import native


class NativeRendererUnavailable(RuntimeError):
    """The native library is missing, unloadable, or refused the input."""


def render(phonemes, pitch=64, mouth=128, throat=128, speed=72,
           singmode=False, inflection=50):
    """Render phonemes to 8-bit unsigned PCM using the native library.

    Same signature and return value as the full renderer. Raises
    NativeRendererUnavailable instead of falling back to Python.
    """
    pitch = pitch & 0xFF
    mouth = mouth & 0xFF
    throat = throat & 0xFF
    if speed is None:
        speed = 72
    speed = speed & 0xFF

    # An empty phoneme list is not an error; the full renderer returns an
    # empty buffer for it rather than raising.
    if not phonemes:
        return b''

    if not native.available():
        raise NativeRendererUnavailable(
            "the SAM native renderer could not be loaded, and this is a "
            "native-only build with no Python fallback")

    audio = native.render(phonemes, pitch, mouth, throat, speed,
                          singmode, inflection)
    if audio is None:
        raise NativeRendererUnavailable(
            "the SAM native renderer refused the input")
    return audio
