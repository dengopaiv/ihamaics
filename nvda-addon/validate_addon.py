#!/usr/bin/env python3
"""Validate sam.nvda-addon before installing it into NVDA.

Checks the things that turn into a broken install or a silent fallback:
the manifest NVDA parses, that every module the driver imports is
actually in the archive, that the DLLs are the architectures they claim,
and that the packaged engine really renders.

    python nvda-addon/validate_addon.py [path-to-addon]

Exit status is 0 when the addon looks installable.
"""
import ast
import configparser
import os
import struct
import subprocess
import sys
import tempfile
import shutil
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

REQUIRED_MANIFEST = ['name', 'summary', 'description', 'author', 'url',
                     'version', 'minimumNVDAVersion', 'lastTestedNVDAVersion']

MACHINE = {0x14c: 'x86', 0x8664: 'x64', 0xaa64: 'ARM64'}

# Modules NVDA itself provides; not expected inside the addon.
NVDA_PROVIDED = {
    'synthDriverHandler', 'speech', 'autoSettingsUtils', 'nvwave', 'config',
    'logHandler', 'addonHandler', 'languageHandler', 'ui', 'globalPluginHandler',
}


def fail(msg, problems):
    problems.append(msg)
    print(f'  FAIL  {msg}')


def ok(msg):
    print(f'  ok    {msg}')


def pe_machine(path):
    with open(path, 'rb') as f:
        f.seek(0x3c)
        pe = struct.unpack('<I', f.read(4))[0]
        f.seek(pe + 4)
        return struct.unpack('<H', f.read(2))[0]


def main():
    addon = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, 'sam.nvda-addon')
    problems = []

    if not os.path.exists(addon):
        print(f'no addon at {addon}; run package_addon.py first')
        return 1
    print(f'validating {os.path.relpath(addon, ROOT)} '
          f'({os.path.getsize(addon) / 1024 / 1024:.2f} MB)\n')

    if not zipfile.is_zipfile(addon):
        print('  FAIL  not a zip archive')
        return 1

    zf = zipfile.ZipFile(addon)
    bad = zf.testzip()
    if bad:
        fail(f'corrupt entry: {bad}', problems)
    else:
        ok(f'archive intact, {len(zf.namelist())} entries')

    names = set(zf.namelist())

    # --- manifest ---------------------------------------------------
    if 'manifest.ini' not in names:
        fail('manifest.ini missing', problems)
        return 1
    cp = configparser.ConfigParser()
    try:
        cp.read_string('[DEFAULT]\n' + zf.read('manifest.ini').decode('utf-8'))
        man = cp['DEFAULT']
        missing = [k for k in REQUIRED_MANIFEST if k not in man]
        if missing:
            fail(f'manifest missing keys: {", ".join(missing)}', problems)
        else:
            ok(f'manifest complete: {man["name"]} v{man["version"]}, '
               f'NVDA {man["minimumNVDAVersion"]}+')
    except Exception as e:
        fail(f'manifest unparseable: {e}', problems)
        man = {}

    # --- driver entry point -----------------------------------------
    entry = 'synthDrivers/sam/__init__.py'
    if entry not in names:
        fail(f'{entry} missing: NVDA would not see a synthesizer', problems)
        return 1

    tree = ast.parse(zf.read(entry).decode('utf-8'))
    classes = [n.name for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]
    if 'SynthDriver' not in classes:
        fail('no SynthDriver class in the entry point', problems)
    else:
        ok('SynthDriver class present')

    # --- every imported module is present ---------------------------
    py_members = {n for n in names if n.endswith('.py')}
    pkg_modules = {os.path.basename(n)[:-3] for n in py_members
                   if n.startswith('synthDrivers/sam/')}
    unresolved = set()
    for member in sorted(py_members):
        src = zf.read(member).decode('utf-8')
        for node in ast.walk(ast.parse(src)):
            if isinstance(node, ast.ImportFrom) and node.level > 0:
                # relative: from . import x  /  from .x import y
                if node.module:
                    if node.module.split('.')[0] not in pkg_modules:
                        unresolved.add(f'{member}: .{node.module}')
                else:
                    for a in node.names:
                        if a.name not in pkg_modules:
                            unresolved.add(f'{member}: .{a.name}')
    if unresolved:
        for u in sorted(unresolved):
            fail(f'unresolved relative import {u}', problems)
    else:
        ok(f'all relative imports resolve within the package '
           f'({len(pkg_modules)} modules)')

    # --- native libraries -------------------------------------------
    dlls = sorted(n for n in names if n.endswith('.dll'))
    if not dlls:
        print('  warn  no native DLLs bundled; the addon will use the '
              'Python renderer')
    else:
        expected = {'sam_render-x64.dll': 0x8664, 'sam_render-x86.dll': 0x14c}
        tmp = tempfile.mkdtemp()
        try:
            for d in dlls:
                base = os.path.basename(d)
                zf.extract(d, tmp)
                m = pe_machine(os.path.join(tmp, d))
                want = expected.get(base)
                if want is None:
                    print(f'  warn  unexpected DLL {base}')
                elif m != want:
                    fail(f'{base} is {MACHINE.get(m, hex(m))}, '
                         f'expected {MACHINE[want]}', problems)
                else:
                    ok(f'{base} is {MACHINE[m]}')
            for base in expected:
                if not any(os.path.basename(d) == base for d in dlls):
                    print(f'  warn  {base} not bundled; that architecture '
                          f'falls back to Python')
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    # --- the packaged engine actually renders -----------------------
    tmp = tempfile.mkdtemp()
    try:
        zf.extractall(tmp)
        sam_dir = os.path.join(tmp, 'synthDrivers', 'sam')
        code = (
            'import sys; sys.path.insert(0, r"%s")\n'
            'import native, sam\n'
            'a = sam.SAM().speak("testing one two three")\n'
            'print("NATIVE", native.available())\n'
            'print("BYTES", len(a) if a else 0)\n'
        ) % sam_dir
        r = subprocess.run([sys.executable, '-c', code],
                           capture_output=True, text=True)
        out = dict(l.split(' ', 1) for l in r.stdout.split('\n') if ' ' in l)
        if r.returncode != 0:
            fail(f'packaged engine failed to run: '
                 f'{(r.stderr or "").strip().splitlines()[-1:]}', problems)
        elif int(out.get('BYTES', 0)) <= 0:
            fail('packaged engine produced no audio', problems)
        else:
            ok(f'packaged engine renders {out["BYTES"]} bytes '
               f'(native: {out.get("NATIVE")})')
            if out.get('NATIVE') != 'True':
                print('  warn  the packaged addon fell back to Python; '
                      'the DLL did not load')
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print()
    if problems:
        print(f'{len(problems)} problem(s); not ready to install')
        return 1
    print('addon looks installable')
    return 0


if __name__ == '__main__':
    sys.exit(main())
