# -*- mode: python ; coding: utf-8 -*-

import sys
from pathlib import Path

block_cipher = None

app_root = Path(sys.argv[0]).resolve().parent

a = Analysis(
    ['main.py'],
    pathex=[str(app_root.parent.parent), str(app_root)],
    binaries=[],
    datas=[
        (str(app_root / 'resources' / 'icons'), 'src/app/resources/icons'),
        (str(app_root / 'resources' / 'styles'), 'src/app/resources/styles'),
        (str(app_root / 'templates'), 'src/app/templates'),
        (str(app_root.parent.parent / 'skills'), 'skills'),
    ],
    hiddenimports=[
        'PySide6.QtCore',
        'PySide6.QtGui',
        'PySide6.QtWidgets',
        'PySide6.QtSvg',
        'PySide6.QtXml',
        'qt_material',
        'yaml',
        'markdown',
    ],
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
    [],
    exclude_binaries=True,
    name='DocKit Studio',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(app_root / 'resources' / 'icons' / 'dropbox.ico'),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='DocKit Studio',
)
