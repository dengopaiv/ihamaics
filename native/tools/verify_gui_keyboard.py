#!/usr/bin/env python3
"""Check that the SAM GUI can be driven from the keyboard alone.

    python native/tools/verify_gui_keyboard.py [x64|x86]

verify_gui.py proves the executable renders the right audio. It says
nothing about whether anyone can reach the button that renders it.

This launches the real GUI, puts focus where the program puts it, and
walks the tab order by posting actual VK_TAB messages into its queue -
the same messages a keypress delivers, processed by the same
IsDialogMessage call in the same loop. After each one it reads back where
the focus actually went. Nothing is simulated except the finger.

What it demands:

  * Tab moves focus off every control, the multiline text box included.
    A control that swallows Tab is a keyboard trap: someone navigating
    without a mouse cannot get past it, and for a screen reader voice
    that is not a cosmetic problem.
  * Tab reaches every control that declares WS_TABSTOP.
  * The order cycles back to where it started rather than dead-ending.
  * Shift+Tab walks the same ring backwards.

It exists because this exact trap shipped in the sibling project: a
multiline EDIT answers WM_GETDLGCODE with DLGC_WANTALLKEYS,
IsDialogMessage honours that by returning before its own Tab handling,
and focus goes into the box and stays there. Every label was correct and
unreachable. A design argument for accessibility is not evidence that the
built program is accessible.

Exit status is 0 when the whole ring is reachable, 1 otherwise.
"""
import ctypes
import ctypes.wintypes as w
import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

BUILD = os.path.join(ROOT, 'gui-native', 'build')
EXE = 'sam_gui-{arch}.exe'
WINDOW_CLASS = 'SAMMainWindow'

WM_KEYDOWN, WM_KEYUP, WM_CLOSE, WM_GETDLGCODE = 0x0100, 0x0101, 0x0010, 0x0087
VK_TAB, VK_SHIFT = 0x09, 0x10
GWL_STYLE, GWL_ID = -16, -12
WS_TABSTOP, WS_DISABLED = 0x00010000, 0x08000000

# WM_GETDLGCODE bits, for explaining a failure rather than just reporting
# it. DLGC_WANTALLKEYS and DLGC_WANTMESSAGE are the same bit (0x0004) in
# winuser.h; the name is just which way you read it.
DLGC = [
    (0x0001, 'WANTARROWS'), (0x0002, 'WANTTAB'),
    (0x0004, 'WANTALLKEYS/WANTMESSAGE'), (0x0008, 'HASSETSEL'),
    (0x0010, 'DEFPUSHBUTTON'), (0x0020, 'UNDEFPUSHBUTTON'),
    (0x0040, 'RADIOBUTTON'), (0x0080, 'WANTCHARS'),
    (0x0100, 'STATIC'), (0x2000, 'BUTTON'),
]

# gui-native/resource.h, so a failure names a control instead of a handle.
NAMES = {
    1000: 'text label', 1001: 'text box', 1002: 'phoneme mode',
    1003: 'speed label', 1004: 'speed', 1005: 'speed spin',
    1006: 'pitch label', 1007: 'pitch', 1008: 'pitch spin',
    1009: 'mouth label', 1010: 'mouth', 1011: 'mouth spin',
    1012: 'throat label', 1013: 'throat', 1014: 'throat spin',
    1015: 'inflection label', 1016: 'inflection', 1017: 'inflection spin',
    1018: 'Preview', 1019: 'Convert', 1020: 'Render',
    1021: 'sing mode', 1022: 'preset label', 1023: 'voice preset',
}

u32 = ctypes.WinDLL('user32', use_last_error=True)


class GUITHREADINFO(ctypes.Structure):
    _fields_ = [('cbSize', w.DWORD), ('flags', w.DWORD),
                ('hwndActive', w.HWND), ('hwndFocus', w.HWND),
                ('hwndCapture', w.HWND), ('hwndMenuOwner', w.HWND),
                ('hwndMoveSize', w.HWND), ('hwndCaret', w.HWND),
                ('rcCaret', w.RECT)]


ENUMPROC = ctypes.WINFUNCTYPE(w.BOOL, w.HWND, w.LPARAM)


def exe_for(arch):
    path = os.path.join(BUILD, EXE.format(arch=arch))
    return path if os.path.exists(path) else None


def find_window(cls, timeout=10.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        hwnd = u32.FindWindowW(cls, None)
        if hwnd:
            return hwnd
        time.sleep(0.05)
    return None


def children(parent):
    """Direct children in z-order, which is what tab order follows."""
    out = []

    def cb(hwnd, _):
        out.append(hwnd)
        return True

    u32.EnumChildWindows(parent, ENUMPROC(cb), 0)
    return out


def describe(hwnd):
    if not hwnd:
        return 'nothing'
    cid = u32.GetWindowLongW(hwnd, GWL_ID)
    return NAMES.get(cid, 'control %d' % cid)


def tabstops(parent):
    """The controls that claim to be reachable by Tab."""
    out = []
    for hwnd in children(parent):
        style = u32.GetWindowLongW(hwnd, GWL_STYLE)
        if (style & WS_TABSTOP) and not (style & WS_DISABLED) \
                and u32.IsWindowVisible(hwnd):
            out.append(hwnd)
    return out


def dlgcode(hwnd):
    code = u32.SendMessageW(hwnd, WM_GETDLGCODE, 0, 0)
    return code, [n for bit, n in DLGC if code & bit]


def focus_of(thread_id):
    info = GUITHREADINFO()
    info.cbSize = ctypes.sizeof(info)
    if not u32.GetGUIThreadInfo(thread_id, ctypes.byref(info)):
        return None
    return info.hwndFocus


def settle(hwnd, thread_id, timeout=10.0):
    """Wait until the window has finished building itself.

    FindWindow succeeds while WM_CREATE is still running, so enumerating
    children straight away can catch half a dialog. Wait for the child
    count to stop changing, then for focus to reach a control - the
    program sets that last.
    """
    deadline = time.time() + timeout

    count = -1
    while time.time() < deadline:
        now = len(children(hwnd))
        if now == count and now > 0:
            break
        count = now
        time.sleep(0.1)

    while time.time() < deadline:
        focus = focus_of(thread_id)
        if focus and focus != hwnd and u32.IsChild(hwnd, focus):
            return focus
        time.sleep(0.05)
    return None


def press_tab(hwnd, thread_id, shift=False, timeout=2.0):
    """Post a real Tab keypress and wait for the focus to actually move.

    Returns where the focus ended up, which is the same window it started
    on if nothing moved - that is the keyboard-trap case, and it costs the
    full timeout to establish.

    A fixed pause here instead of a wait made the walk flaky. The keypress
    is posted to another process, and when the machine is busy - straight
    after a rebuild, say - that process can take longer to handle it than
    the pause allowed. The focus then reads back unchanged, the walk gives
    up early, and controls that are perfectly reachable get reported as
    unreachable. Waiting for the change is what makes a pass mean the tab
    order is right, rather than that the machine happened to be idle.
    """
    before = focus_of(thread_id)

    if shift:
        u32.PostMessageW(hwnd, WM_KEYDOWN, VK_SHIFT, 1)
    u32.PostMessageW(hwnd, WM_KEYDOWN, VK_TAB, 1)
    u32.PostMessageW(hwnd, WM_KEYUP, VK_TAB, 0xC0000001)
    if shift:
        u32.PostMessageW(hwnd, WM_KEYUP, VK_SHIFT, 0xC0000001)

    deadline = time.time() + timeout
    while time.time() < deadline:
        now = focus_of(thread_id)
        if now and now != before:
            return now
        time.sleep(0.02)
    return focus_of(thread_id)


def walk(thread_id, start, steps, shift=False):
    """Press Tab `steps` times, returning where focus went each time."""
    seen = []
    cur = start
    for _ in range(steps):
        nxt = press_tab(cur, thread_id, shift)
        seen.append(nxt)
        if not nxt or nxt == cur:
            break
        cur = nxt
    return seen


def check_accelerators(hwnd, arch):
    """No two controls may claim the same Alt key.

    Windows does not complain about a duplicate: Alt+V simply cycles
    between the controls that want it instead of activating either, so a
    clash is invisible until someone navigating by keyboard cannot reach
    a button. This started as an eyeball check and immediately found one -
    "&Voice preset" against "Pre&view" - which is why it is a test.
    """
    seen = {}
    clashes = []

    for h in children(hwnd):
        buf = ctypes.create_unicode_buffer(256)
        u32.GetWindowTextW(h, buf, 256)
        text = buf.value
        i = text.find('&')
        # "&&" is a literal ampersand, not an accelerator.
        while i >= 0 and i + 1 < len(text) and text[i + 1] == '&':
            i = text.find('&', i + 2)
        if i < 0 or i + 1 >= len(text):
            continue
        key = text[i + 1].upper()
        if key in seen:
            clashes.append((key, seen[key], describe(h)))
        else:
            seen[key] = describe(h)

    if clashes:
        for key, first, second in clashes:
            print('  FAIL  %s: Alt+%s is claimed by both the %s and the %s'
                  % (arch, key, first, second))
        return len(clashes)

    print('  ok    %s: %d accelerators, all distinct (%s)'
          % (arch, len(seen), ' '.join(sorted(seen))))
    return 0


def check(arch):
    exe = exe_for(arch)
    if exe is None:
        return 1

    proc = subprocess.Popen([exe])
    failures = 0
    hwnd = None
    try:
        hwnd = find_window(WINDOW_CLASS)
        if hwnd is None:
            print('  FAIL  %s: the window never appeared' % arch)
            return 1

        tid = u32.GetWindowThreadProcessId(hwnd, None)
        start = settle(hwnd, tid)
        if not start:
            print('  FAIL  %s: nothing had focus at startup' % arch)
            return 1

        stops = tabstops(hwnd)
        print('  %s: %d controls declare WS_TABSTOP' % (arch, len(stops)))
        print('  %s: focus starts on the %s' % (arch, describe(start)))

        code, names = dlgcode(start)
        print('  %s: it answers WM_GETDLGCODE with %s = %s'
              % (arch, hex(code), ' | '.join(names)))

        # The trap: does Tab get out of the box it starts in?
        after = press_tab(start, tid)
        if after == start:
            print('  FAIL  %s: Tab does not leave the %s - it is a '
                  'keyboard trap' % (arch, describe(start)))
            failures += 1
        else:
            print('  ok    %s: Tab leaves the %s for the %s'
                  % (arch, describe(start), describe(after)))

        # The whole ring, forwards. One extra step so a correct order has
        # room to come back round to where it started.
        seen = walk(tid, after, len(stops) + 1)
        visited = []
        for h in [start, after] + seen:
            if h not in visited:
                visited.append(h)
        missing = [h for h in stops if h not in visited]
        if missing:
            print('  FAIL  %s: Tab never reaches %s'
                  % (arch, ', '.join(describe(h) for h in missing)))
            failures += 1
        else:
            print('  ok    %s: Tab reaches all %d controls'
                  % (arch, len(stops)))

        if start in seen:
            print('  ok    %s: the order cycles back to the %s'
                  % (arch, describe(start)))
        else:
            print('  FAIL  %s: the order never returns to the start' % arch)
            failures += 1

        cur = focus_of(tid)
        back = press_tab(cur, tid, shift=True)
        if back and back != cur:
            print('  ok    %s: Shift+Tab goes back to the %s'
                  % (arch, describe(back)))
        else:
            print('  FAIL  %s: Shift+Tab does not move focus' % arch)
            failures += 1

        failures += check_accelerators(hwnd, arch)

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
        if exe_for(arch) is None:
            print('missing: %s' % EXE.format(arch=arch))
            continue
        total += check(arch)
        checked += 1
        print()

    if checked == 0:
        print('nothing built to check; run gui-native\\build.cmd first')
        return 1
    if total:
        print('%d keyboard navigation problems' % total)
        return 1
    print('reachable from the keyboard in all %d builds checked' % checked)
    return 0


if __name__ == '__main__':
    sys.exit(main())
