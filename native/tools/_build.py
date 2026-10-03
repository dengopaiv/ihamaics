#!/usr/bin/env python3
"""Compile and run a host tool from native/tools against native/src.

verify_frames.py grew its own copy of this because it was the only one
that needed it. The front-end port adds three more differential tests, so
the MSVC lookup, the vcvarsall shell and the temporary build directory
live here instead of in each of them. verify_tables.py, verify_frames.py
and verify_prepare.py kept private copies until stage R.0 of the C17
rewrite folded them in here too (docs/c17-rewrite-plan.md).

Not used by the shipped DLL or the GUI; those have build.cmd.

Which implementation is checked
-------------------------------
Every verifier takes `--impl native|engine`, default native. take_impl()
reads it, and build_and_run() and engine_dll() follow it:

  native   native/, the frozen C port: each dump tool is compiled from
           native/tools against native/src, as it always was.
  engine   engine/, the C17 rewrite: each dump tool is a CMake target of
           the same name in engine/, built by engine/tools/build_matrix.py,
           and it prints the same format, so the same Python checks it.
           A tool the rewrite does not have yet is a skip (exit 77), not
           a failure: the stage that adds it is the one that must pass.

The Python under nvda-addon/ is the oracle for both.
"""
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC = os.path.join(ROOT, 'native', 'src')
INC = os.path.join(ROOT, 'native', 'include')
TOOLS = os.path.join(ROOT, 'native', 'tools')

IMPLS = ('native', 'engine')
IMPL = 'native'
ENGINE_BUILD = os.environ.get('SAM_ENGINE_BUILD',
                              os.path.join(ROOT, 'engine', 'build-msvc'))

# ctest's SKIP_RETURN_CODE, and what a verifier exits with when the
# implementation it was asked to check has nothing to check yet.
SKIP = 77


def take_impl(argv=None):
    """Remove `--impl NAME` (or `--impl=NAME`) from argv and select NAME.

    argv defaults to sys.argv, and is edited in place so each verifier's
    own positional arguments stay where they were. Returns the name.
    """
    global IMPL
    argv = sys.argv if argv is None else argv
    for i, a in enumerate(argv):
        if a == '--impl' and i + 1 < len(argv):
            name = argv[i + 1]
            del argv[i:i + 2]
            break
        if a.startswith('--impl='):
            name = a.split('=', 1)[1]
            del argv[i]
            break
    else:
        return IMPL
    if name not in IMPLS:
        raise SystemExit('--impl must be one of: ' + ', '.join(IMPLS))
    IMPL = name
    return IMPL


def skip(why):
    """Report that there is nothing to check yet, and exit with SKIP."""
    print('skipped (--impl %s): %s' % (IMPL, why))
    raise SystemExit(SKIP)


def engine_dll():
    """Path of the renderer DLL for the selected implementation."""
    if IMPL == 'engine':
        return os.path.join(ENGINE_BUILD, 'sam_render.dll')
    return os.path.join(ROOT, 'native', 'build', 'sam_render-x64.dll')


def find_vs():
    """Installation path of the latest MSVC toolset, or None."""
    vswhere = os.path.join(
        os.environ.get('ProgramFiles(x86)', r'C:\Program Files (x86)'),
        'Microsoft Visual Studio', 'Installer', 'vswhere.exe')
    if not os.path.exists(vswhere):
        return None
    out = subprocess.run(
        [vswhere, '-latest', '-products', '*', '-requires',
         'Microsoft.VisualStudio.Component.VC.Tools.x86.x64',
         '-property', 'installationPath'],
        capture_output=True, text=True).stdout.strip()
    return out or None


def build_and_run(tool, sources, stdin_data=None, args=(), arch='x64',
                  timeout=600, defines=(), text=False, flags=()):
    """Compile tool + sources and run it once.

    tool is a file name in native/tools; sources are file names in
    native/src. stdin_data is bytes or None. defines are extra /D macros,
    such as _CRT_SECURE_NO_WARNINGS for a tool that uses fopen. flags are
    extra cl options; the default build is unoptimised, which is right
    for checking values and wrong for timing them, so measure.py passes
    the shipped DLL's /O2 /MT. Returns
    the tool's stdout as bytes, or as str with newlines normalised when
    text is true, or None if the toolchain is missing or the build failed
    (the build log is printed in that case).

    With --impl engine, nothing is compiled here: the tool of the same
    name is taken from engine's build directory, sources, defines and
    arch are ignored (the rewrite is x64 only), and a tool that is not
    there yet ends the run as a skip.
    """
    if IMPL == 'engine':
        exe = os.path.join(ENGINE_BUILD, os.path.splitext(tool)[0] + '.exe')
        if not os.path.exists(exe):
            skip('%s has no %s yet; build engine/ or wait for the stage '
                 'that adds it' % (ENGINE_BUILD, os.path.basename(exe)))
        return _run(exe, tool, stdin_data, args, timeout, text)

    vs = find_vs()
    if vs is None:
        print('no MSVC toolset found; cannot verify')
        return None

    vcvars = os.path.join(vs, 'VC', 'Auxiliary', 'Build', 'vcvarsall.bat')
    tmp = tempfile.mkdtemp(prefix='samverify')
    try:
        exe = os.path.join(tmp, os.path.splitext(tool)[0] + '.exe')
        log = os.path.join(tmp, 'build.log')
        bat = os.path.join(tmp, 'go.cmd')
        srcs = ' '.join('"%s"' % os.path.join(SRC, s) for s in sources)

        with open(bat, 'w') as f:
            f.write('@echo off\n')
            f.write('call "%s" %s >nul 2>nul\n' % (vcvars, arch))
            f.write('cd /d "%s"\n' % tmp)
            defs = ''.join(' /D%s' % d for d in defines)
            defs += ''.join(' %s' % f for f in flags)
            f.write('cl /nologo /W4 /WX%s /I "%s" /I "%s" "%s" %s '
                    '/Fe:"%s" > "%s" 2>&1 || exit /b 1\n'
                    % (defs, SRC, INC, os.path.join(TOOLS, tool), srcs, exe, log))

        r = subprocess.run(['cmd', '/c', bat], capture_output=True)
        if r.returncode != 0:
            print('build failed (exit %d):' % r.returncode)
            if os.path.exists(log):
                print(open(log, encoding='utf-8', errors='replace').read())
            sys.stdout.write(r.stdout.decode('utf-8', 'replace')[-2000:])
            return None

        return _run(exe, tool, stdin_data, args, timeout, text)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _run(exe, tool, stdin_data, args, timeout, text):
    run = subprocess.run([exe] + list(args), input=stdin_data,
                         capture_output=True, timeout=timeout)
    if run.returncode != 0:
        print('%s exited %d' % (tool, run.returncode))
        sys.stdout.write(run.stderr.decode('utf-8', 'replace')[-2000:])
        return None
    if text:
        # What subprocess's text=True gave the tools that used to
        # build themselves: decoded, with \r\n read as \n.
        out = run.stdout.decode('utf-8', 'replace')
        return out.replace('\r\n', '\n').replace('\r', '\n')
    return run.stdout
