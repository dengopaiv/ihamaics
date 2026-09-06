# Optional native renderer.
#
# Loads sam_render-{x64,x86}.dll if it is present and usable, and exposes
# render() with the same contract as renderer.render(). Every failure path
# returns None so the caller falls back to the Python renderer: the addon
# must keep speaking even if the library is missing, is built for the
# wrong architecture, or fails to load.
#
# The DLL is byte-identical to the Python renderer; see
# native/tools/verify_render.py.

import ctypes
import os
import threading

ABI_VERSION = 1

_lib = None
_tried = False
_lock = threading.Lock()


class _Phoneme(ctypes.Structure):
    _fields_ = [("phoneme", ctypes.c_ubyte),
                ("length", ctypes.c_ubyte),
                ("stress", ctypes.c_ubyte)]


class _Voice(ctypes.Structure):
    _fields_ = [("pitch", ctypes.c_ubyte), ("mouth", ctypes.c_ubyte),
                ("throat", ctypes.c_ubyte), ("speed", ctypes.c_ubyte),
                ("singmode", ctypes.c_int), ("inflection", ctypes.c_int)]


def _dll_name():
    return ("sam_render-x64.dll" if ctypes.sizeof(ctypes.c_void_p) == 8
            else "sam_render-x86.dll")


def _candidates():
    """Where the library might live: installed addon first, then a dev tree."""
    here = os.path.dirname(os.path.abspath(__file__))
    name = _dll_name()
    yield os.path.join(here, name)
    # Repository layout: nvda-addon/synthDrivers/sam -> native/build
    repo = os.path.abspath(os.path.join(here, '..', '..', '..'))
    yield os.path.join(repo, 'native', 'build', name)


def _load():
    global _lib, _tried
    lib = _lib
    if lib is not None or _tried:
        return lib

    with _lock:
        if _tried:
            return _lib
        _tried = True

        for path in _candidates():
            if not os.path.exists(path):
                continue
            try:
                lib = ctypes.cdll.LoadLibrary(path)

                # Declaring argtypes is not optional: without them ctypes
                # guesses at marshalling and the failures are silent and
                # data dependent.
                lib.sam_abi_version.restype = ctypes.c_int
                lib.sam_abi_version.argtypes = []
                lib.sam_render.restype = ctypes.c_int
                lib.sam_render.argtypes = [
                    ctypes.POINTER(_Phoneme), ctypes.c_int,
                    ctypes.POINTER(_Voice),
                    ctypes.POINTER(ctypes.c_ubyte), ctypes.c_int,
                ]

                if lib.sam_abi_version() != ABI_VERSION:
                    continue

                _lib = lib
                return _lib
            except Exception:
                continue

        return None


def available():
    """True if the native renderer is loaded and usable."""
    return _load() is not None


def library_path():
    """Path of the loaded library, or None. For diagnostics."""
    if _load() is None:
        return None
    for path in _candidates():
        if os.path.exists(path):
            return path
    return None


def render(phonemes, pitch, mouth, throat, speed, singmode, inflection):
    """Render via the native library, or None if it cannot be used.

    None means "fall back to Python", never "silence": callers must treat
    it as no result rather than as an empty buffer.
    """
    lib = _load()
    if lib is None or not phonemes:
        return None

    try:
        count = len(phonemes)
        arr = (_Phoneme * count)()
        for i, entry in enumerate(phonemes):
            arr[i].phoneme = entry[0] & 0xFF
            arr[i].length = entry[1] & 0xFF
            arr[i].stress = entry[2] & 0xFF

        voice = _Voice(pitch & 0xFF, mouth & 0xFF, throat & 0xFF, speed & 0xFF,
                       1 if singmode else 0, int(inflection))

        needed = lib.sam_render(arr, count, ctypes.byref(voice), None, 0)
        if needed < 0:
            return None
        if needed == 0:
            return b''

        buf = (ctypes.c_ubyte * needed)()
        written = lib.sam_render(arr, count, ctypes.byref(voice), buf, needed)
        if written < 0:
            return None
        return ctypes.string_at(buf, written)
    except Exception:
        return None
