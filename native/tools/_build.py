#!/usr/bin/env python3
"""Compile and run a host tool from native/tools against native/src.

verify_frames.py grew its own copy of this because it was the only one
that needed it. The front-end port adds three more differential tests, so
the MSVC lookup, the vcvarsall shell and the temporary build directory
live here instead of in each of them.

Not used by the shipped DLL or the GUI; those have build.cmd.
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
                  timeout=600):
    """Compile tool + sources and run it once.

    tool is a file name in native/tools; sources are file names in
    native/src. stdin_data is bytes or None. Returns the tool's stdout as
    bytes, or None if the toolchain is missing or the build failed (the
    build log is printed in that case).
    """
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
            f.write('cl /nologo /W4 /WX /I "%s" /I "%s" "%s" %s '
                    '/Fe:"%s" > "%s" 2>&1 || exit /b 1\n'
                    % (SRC, INC, os.path.join(TOOLS, tool), srcs, exe, log))

        r = subprocess.run(['cmd', '/c', bat], capture_output=True)
        if r.returncode != 0:
            print('build failed (exit %d):' % r.returncode)
            if os.path.exists(log):
                print(open(log, encoding='utf-8', errors='replace').read())
            sys.stdout.write(r.stdout.decode('utf-8', 'replace')[-2000:])
            return None

        run = subprocess.run([exe] + list(args), input=stdin_data,
                             capture_output=True, timeout=timeout)
        if run.returncode != 0:
            print('%s exited %d' % (tool, run.returncode))
            sys.stdout.write(run.stderr.decode('utf-8', 'replace')[-2000:])
            return None
        return run.stdout
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
