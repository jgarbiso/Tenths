# -*- mode: python ; coding: utf-8 -*-
"""
Tenths PyInstaller Spec File
==============================
Builds a single-directory Windows application with no console window.
The entry point is the system tray app (tenths.service.tray:main).

Build command:
    pyinstaller installer/tenths.spec

Output:
    dist/Tenths/Tenths.exe
"""

import os
import sys

block_cipher = None

# Paths
# PyInstaller sets SPECPATH to the *directory* containing this spec file, so it
# must not be passed through dirname() again — doing so pointed SPEC_DIR at the
# project root and made version_info.txt resolve one level too high.
SPEC_DIR = os.path.abspath(SPECPATH) if 'SPECPATH' in dir() else os.path.abspath('installer')
PROJECT_ROOT = os.path.dirname(SPEC_DIR) if os.path.basename(SPEC_DIR) == 'installer' else SPEC_DIR

VERSION_FILE = os.path.join(SPEC_DIR, 'version_info.txt')
if not os.path.isfile(VERSION_FILE):
    raise SystemExit(
        f"Version resource missing: {VERSION_FILE}\n"
        "Without it the exe ships with no product name or version. Fix the path "
        "rather than dropping the version= argument."
    )

a = Analysis(
    [os.path.join(PROJECT_ROOT, 'tenths', 'service', 'tray.py')],
    pathex=[PROJECT_ROOT],
    binaries=[],
    datas=[
        # Include assets (icon)
        (os.path.join(PROJECT_ROOT, 'assets', 'tenths.ico'), 'assets'),
        # Include track map files (legacy .md fallback)
        (os.path.join(PROJECT_ROOT, 'tracks'), 'tracks'),
        # Include bundled track landmark data (PRIMARY track source — 457 tracks)
        (os.path.join(PROJECT_ROOT, 'tenths', 'data'), 'data'),
    ],
    hiddenimports=[
        'tenths',
        'tenths.cli',
        'tenths.config',
        'tenths.applog',
        'logging.handlers',
        'tenths.analyzer',
        'tenths.process',
        'tenths.report',
        'tenths.summary',
        'tenths.track_map',
        'tenths.track_map_generator',
        'tenths.results',
        'tenths.incidents',
        'tenths.service',
        'tenths.service.watcher',
        'tenths.service.notifier',
        'tenths.service.tray',
        'winotify',
        'pystray',
        'watchdog',
        'watchdog.observers',
        'watchdog.events',
        'pandas',
        'numpy',
        'yaml',
        'irsdk',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter',
        'matplotlib',
        'scipy',
        'IPython',
        'jupyter',
        'notebook',
        # sqlite3 is pulled in by pandas.io.sql but Tenths never uses SQL storage.
        # Saves ~1.5 MB (sqlite3.dll + _sqlite3.pyd).
        'sqlite3',
        # pytest and _pytest are collected via numpy._pytesttester but never
        # actually shipped as directories; the TOC references are harmless.
        # Listed here defensively in case a future PyInstaller version bundles them.
        'pytest',
        '_pytest',
    ],
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
    name='Tenths',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # No console window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=os.path.join(PROJECT_ROOT, 'assets', 'tenths.ico'),
    # Windows product/version metadata. Without it the exe shows no product
    # name or version in its properties.
    version=VERSION_FILE,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='Tenths',
)
