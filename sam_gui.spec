# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec file for SAM GUI

import os

block_cipher = None

# Path to SAM modules
sam_path = os.path.join('nvda-addon', 'synthDrivers', 'sam')

# Collect all SAM Python files as data
sam_datas = [
    (os.path.join(sam_path, 'sam.py'), '.'),
    (os.path.join(sam_path, 'reciter.py'), '.'),
    (os.path.join(sam_path, 'parser.py'), '.'),
    (os.path.join(sam_path, 'renderer.py'), '.'),
    (os.path.join(sam_path, 'constants.py'), '.'),
    (os.path.join(sam_path, 'parser_tables.py'), '.'),
    (os.path.join(sam_path, 'reciter_tables.py'), '.'),
    (os.path.join(sam_path, 'renderer_tables.py'), '.'),
    (os.path.join(sam_path, 'cmudict.py'), '.'),
    (os.path.join(sam_path, 'cmudict.txt'), '.'),
]

a = Analysis(
    ['sam_gui.py'],
    pathex=[sam_path],
    binaries=[],
    datas=sam_datas,
    hiddenimports=['sam', 'reciter', 'parser', 'renderer', 'constants',
                   'parser_tables', 'reciter_tables', 'renderer_tables', 'cmudict'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='SAM',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
