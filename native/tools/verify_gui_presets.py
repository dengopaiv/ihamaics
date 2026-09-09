#!/usr/bin/env python3
"""Check that the preset combo and the spin controls agree, in the real GUI.

    python native/tools/verify_gui_presets.py [x64|x86]

verify_gui.py proves the executable renders the right audio for a given
set of numbers, and it reaches the presets by passing their numbers in.
That says nothing about whether choosing "Little Robot" in the combo
actually puts 92, 60, 190 and 190 into the boxes, which is the only part
of the feature a user touches.

So this drives the real window: it selects each preset the way the combo
does - CB_SETCURSEL followed by the CBN_SELCHANGE the control sends to
its parent - and reads the four parameter boxes back. Then it goes the
other way, typing a value into an edit box and checking the combo follows
the numbers to Custom, and back onto a named preset when the numbers land
on one again.

That round trip is the whole contract. Getting it backwards - a combo
that remembers what was last chosen rather than describing what the
values now say - is how a GUI ends up claiming "SAM" while playing
something else.

Exit status is 0 when every preset round-trips, 1 otherwise.
"""
import ctypes
import ctypes.wintypes as w
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _build import ROOT  # noqa: E402

sys.path.insert(0, os.path.join(ROOT, 'nvda-addon', 'synthDrivers', 'sam'))

from sam import VOICE_PRESETS  # noqa: E402

BUILD = os.path.join(ROOT, 'gui-native', 'build')
EXE = 'sam_gui-{arch}.exe'
WINDOW_CLASS = 'SAMMainWindow'

# gui-native/resource.h
IDC_PRESET = 1023
EDIT = {'speed': 1004, 'pitch': 1007, 'mouth': 1010, 'throat': 1013}

WM_COMMAND = 0x0111
WM_CLOSE = 0x0010
WM_CHAR = 0x0102
WM_GETTEXT = 0x000D
WM_KEYDOWN = 0x0100
VK_UP = 0x26
EM_SETSEL = 0x00B1
CB_GETCOUNT, CB_GETCURSEL, CB_GETLBTEXT = 0x0146, 0x0147, 0x0148
CB_SETCURSEL = 0x014E
CBN_SELCHANGE = 1

# The order the combo lists them in, and the sam.py key for each.
ORDER = [
    ('SAM', 'sam'),
    ('Elf', 'elf'),
    ('Little Robot', 'little_robot'),
    ('Stuffy Guy', 'stuffy_guy'),
    ('Little Old Lady', 'little_old_lady'),
    ('Extra-Terrestrial', 'extra_terrestrial'),
]
CUSTOM = len(ORDER)

u32 = ctypes.WinDLL('user32', use_last_error=True)

# Declare these rather than letting ctypes guess. A window handle is a
# pointer, and the default int return would truncate it on x64; lParam is
# signed and pointer-wide, and EM_SETSEL's -1 has to survive as -1.
u32.FindWindowW.restype = w.HWND
u32.FindWindowW.argtypes = [w.LPCWSTR, w.LPCWSTR]
u32.GetDlgItem.restype = w.HWND
u32.GetDlgItem.argtypes = [w.HWND, ctypes.c_int]
u32.SendMessageW.restype = ctypes.c_ssize_t
u32.SendMessageW.argtypes = [w.HWND, ctypes.c_uint, ctypes.c_size_t,
                             ctypes.c_ssize_t]
u32.PostMessageW.argtypes = [w.HWND, ctypes.c_uint, ctypes.c_size_t,
                             ctypes.c_ssize_t]


def send(hwnd, msg, wp=0, lp=0):
    return int(u32.SendMessageW(hwnd, msg, wp, lp))


def find_window(cls, timeout=10.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        hwnd = u32.FindWindowW(cls, None)
        if hwnd:
            return hwnd
        time.sleep(0.05)
    return None


def item(hwnd, cid):
    return u32.GetDlgItem(hwnd, cid)


def box_value(hwnd, name):
    """What the parameter box is showing.

    WM_GETTEXT, not GetWindowText. GetWindowText will not fetch the live
    text of a control belonging to another process - it answers from a
    cached caption, so it returns whatever the box held when it was
    created and never changes. That reads exactly like the GUI ignoring
    every update, and it cost an afternoon of chasing a bug that was in
    this file rather than in the program. WM_GETTEXT is marshalled across
    the process boundary and reports the truth.
    """
    buf = ctypes.create_unicode_buffer(64)
    send(item(hwnd, EDIT[name]), WM_GETTEXT, 64,
         ctypes.cast(buf, ctypes.c_void_p).value)
    return int(buf.value) if buf.value.strip().isdigit() else None


def box_values(hwnd):
    return {k: box_value(hwnd, k) for k in EDIT}


def combo_sel(hwnd):
    return send(item(hwnd, IDC_PRESET), CB_GETCURSEL)


def combo_text(hwnd, index):
    buf = ctypes.create_unicode_buffer(128)
    send(item(hwnd, IDC_PRESET), CB_GETLBTEXT, index,
         ctypes.cast(buf, ctypes.c_void_p).value)
    return buf.value


def choose_preset(hwnd, index):
    """Select an item the way the combo control itself would.

    CB_SETCURSEL deliberately does not notify - that is what lets the
    program set the selection without looping - so the CBN_SELCHANGE the
    user's click would have produced is sent separately.
    """
    combo = item(hwnd, IDC_PRESET)
    send(combo, CB_SETCURSEL, index)
    send(hwnd, WM_COMMAND, (CBN_SELCHANGE << 16) | IDC_PRESET, combo)
    time.sleep(0.03)


def type_into(hwnd, name, value):
    """Type a number into a box, one WM_CHAR at a time.

    Not SetWindowText: that replaces the text without the control ever
    seeing a keystroke, so it proves nothing about what happens when
    somebody actually types. Each character goes through the edit's own
    window procedure here, which is what raises EN_CHANGE and what the
    preset combo listens for.
    """
    e = item(hwnd, EDIT[name])
    send(e, EM_SETSEL, 0, -1)              # select all; the first key replaces it
    for ch in str(value):
        send(e, WM_CHAR, ord(ch), 1)
    time.sleep(0.05)


def check(arch):
    exe = os.path.join(BUILD, EXE.format(arch=arch))
    if not os.path.exists(exe):
        print('missing: %s' % EXE.format(arch=arch))
        return 1

    proc = subprocess.Popen([exe])
    failures = 0
    hwnd = None
    try:
        hwnd = find_window(WINDOW_CLASS)
        if hwnd is None:
            print('  FAIL  %s: the window never appeared' % arch)
            return 1
        time.sleep(0.4)

        count = send(item(hwnd, IDC_PRESET), CB_GETCOUNT)
        if count != CUSTOM + 1:
            print('  FAIL  %s: combo has %d items, expected %d'
                  % (arch, count, CUSTOM + 1))
            failures += 1
        else:
            names = [combo_text(hwnd, i) for i in range(count)]
            expected = [label for label, _ in ORDER] + ['Custom']
            if names != expected:
                print('  FAIL  %s: combo lists %r, expected %r'
                      % (arch, names, expected))
                failures += 1
            else:
                print('  ok    %s: combo offers %s' % (arch, ', '.join(names)))

        # It opens on SAM, and the boxes agree with that.
        sel = combo_sel(hwnd)
        got = box_values(hwnd)
        want = VOICE_PRESETS['sam']
        if sel != 0 or got != want:
            print('  FAIL  %s: opens on item %d with %s, expected SAM with %s'
                  % (arch, sel, got, want))
            failures += 1
        else:
            print('  ok    %s: opens on SAM, boxes agree' % arch)

        # Choosing a preset writes its numbers, and the combo stays on it.
        for i, (label, key) in enumerate(ORDER):
            choose_preset(hwnd, i)
            got = box_values(hwnd)
            want = VOICE_PRESETS[key]
            if got != want:
                print('  FAIL  %s: %s put %s in the boxes, expected %s'
                      % (arch, label, got, want))
                failures += 1
                continue
            if combo_sel(hwnd) != i:
                print('  FAIL  %s: %s applied but the combo moved to %r'
                      % (arch, label, combo_text(hwnd, combo_sel(hwnd))))
                failures += 1
        if not failures:
            print('  ok    %s: all %d presets write their own numbers'
                  % (arch, len(ORDER)))

        # Editing a value by hand takes it off the preset.
        choose_preset(hwnd, 2)                  # Little Robot
        type_into(hwnd, 'speed', 99)
        sel = combo_sel(hwnd)
        if sel != CUSTOM:
            print('  FAIL  %s: after editing speed the combo says %r, '
                  'expected Custom' % (arch, combo_text(hwnd, sel)))
            failures += 1
        else:
            print('  ok    %s: editing a value moves the combo to Custom'
                  % arch)

        # And typing the numbers of a preset finds it again.
        elf = VOICE_PRESETS['elf']
        for name in ('speed', 'pitch', 'mouth', 'throat'):
            type_into(hwnd, name, elf[name])
        sel = combo_sel(hwnd)
        if sel != 1:
            print('  FAIL  %s: typing the Elf numbers left the combo on %r'
                  % (arch, combo_text(hwnd, sel)))
            failures += 1
        else:
            print('  ok    %s: typing a preset\'s numbers selects it again'
                  % arch)

        # The third way a value can change: the up-down's own arrow keys,
        # which it handles by subclassing the buddy edit (UDS_ARROWKEYS).
        # This path writes the box without the program's help, so it is
        # the one the other two checks cannot stand in for.
        choose_preset(hwnd, 0)                  # SAM: speed 72
        before = box_value(hwnd, 'speed')
        send(item(hwnd, EDIT['speed']), WM_KEYDOWN, VK_UP, 1)
        time.sleep(0.08)
        after = box_value(hwnd, 'speed')
        if after != before + 1:
            print('  FAIL  %s: the up arrow took speed from %r to %r, '
                  'expected %r' % (arch, before, after, before + 1))
            failures += 1
        elif combo_sel(hwnd) != CUSTOM:
            print('  FAIL  %s: after the up arrow the combo says %r, '
                  'expected Custom'
                  % (arch, combo_text(hwnd, combo_sel(hwnd))))
            failures += 1
        else:
            print('  ok    %s: the spin arrows update the box and the combo'
                  % arch)

    finally:
        if hwnd:
            u32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()

    return failures


def main():
    arches = [a for a in sys.argv[1:] if a in ('x64', 'x86')] or ['x64', 'x86']

    total = 0
    checked = 0
    for arch in arches:
        if not os.path.exists(os.path.join(BUILD, EXE.format(arch=arch))):
            print('missing: %s' % EXE.format(arch=arch))
            continue
        total += check(arch)
        checked += 1
        print()

    if checked == 0:
        print('nothing built to check; run gui-native\\build.cmd first')
        return 1
    if total:
        print('%d preset problems' % total)
        return 1
    print('presets round-trip correctly in all %d builds checked' % checked)
    return 0


if __name__ == '__main__':
    sys.exit(main())
