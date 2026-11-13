# -*- mode: python ; coding: utf-8 -*-
import os
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_all

# The release workflow passes the tag version; local builds use the default.
APP_VERSION = os.environ.get('APP_VERSION') or '0.1.0'

is_macos = sys.platform == 'darwin'
codesign_identity = (os.environ.get('MACOS_CODESIGN_IDENTITY') or None) if is_macos else None
entitlements_file = (os.environ.get('MACOS_ENTITLEMENTS_FILE') or None) if is_macos else None
icon = None
if sys.platform == 'win32':
    icon = 'assets/app-icon.ico'
elif is_macos and Path('assets/app-icon.icns').is_file():
    icon = 'assets/app-icon.icns'

datas = [
    ('qml', 'qml'),
    ('styles', 'styles'),
    ('assets', 'assets'),
]
binaries = []
hiddenimports = []
tmp_ret = collect_all('kokoro')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('language_tags')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('espeakng_loader')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('en_core_web_sm')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('misaki')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=['pyinstaller_runtime_hook.py'],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='BookTTSReader',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=codesign_identity,
    entitlements_file=entitlements_file,
    icon=icon,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='BookTTSReader',
)

if is_macos:
    app = BUNDLE(
        coll,
        name='Book TTS Reader.app',
        icon=icon,
        bundle_identifier='com.assemani.BookTTSReader',
        version=APP_VERSION,
        info_plist={
            'CFBundleShortVersionString': APP_VERSION,
            'NSHighResolutionCapable': True,
            'LSMinimumSystemVersion': '12.0',
        },
        codesign_identity=codesign_identity,
        entitlements_file=entitlements_file,
    )
