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
SPEC_DIR = os.path.dirname(os.path.abspath(SPECPATH)) if 'SPECPATH' in dir() else os.path.dirname(os.path.abspath('installer/tenths.spec'))
PROJECT_ROOT = os.path.dirname(SPEC_DIR) if os.path.basename(SPEC_DIR) == 'installer' else SPEC_DIR

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
