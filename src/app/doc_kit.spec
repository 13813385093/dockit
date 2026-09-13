# -*- mode: python ; coding: utf-8 -*-

import sys
from pathlib import Path, PurePosixPath

block_cipher = None

app_root = Path(sys.argv[0]).resolve().parent

# 已下线的复合类型文档：即使工作区残留也不得进入安装包
LEGACY_DOC_FILES = {'charter.md', 'module-design.md', 'feature-package.md'}


def _datas_tree(src_dir, dest) -> list[tuple[str, str]]:
    """递归收集 src_dir 下需打包的文件，返回 PyInstaller datas 条目。

    跳过 LEGACY_DOC_FILES 中的已下线复合类型文档；目标路径统一用
    PurePosixPath 拼接（正斜杠，Windows 上 PyInstaller 同样接受）。
    返回值按源路径排序，保证多次构建结果可重现。
    """
    src_dir = Path(src_dir)
    items: list[tuple[str, str]] = []
    for file in src_dir.rglob('*'):
        if not file.is_file():
            continue
        if file.name in LEGACY_DOC_FILES:
            continue
        dest_dir = str(PurePosixPath(dest) / file.relative_to(src_dir).parent)
        items.append((str(file), dest_dir))
    return sorted(items)


a = Analysis(
    ['main.py'],
    pathex=[str(app_root.parent.parent), str(app_root)],
    binaries=[],
    datas=(
        _datas_tree(app_root / 'resources' / 'icons', 'src/app/resources/icons')
        + _datas_tree(app_root / 'resources' / 'styles', 'src/app/resources/styles')
        + _datas_tree(app_root / 'templates', 'src/app/templates')
        + _datas_tree(app_root.parent.parent / 'skills', 'skills')
    ),
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
