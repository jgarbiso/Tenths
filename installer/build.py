"""
Tenths Build Script
====================
Builds the distributable Windows application.

Usage:
    python installer/build.py          # Build PyInstaller bundle
    python installer/build.py --full   # Build bundle + Inno Setup installer

Prerequisites:
    pip install pyinstaller
    Inno Setup installed (for --full): https://jrsoftware.org/isinfo.php
"""

import os
import sys
import subprocess
import shutil

# Emoji in the status output crashes on a stock cp1252 console. That is tolerable
# on the success path but not on the failure path, where the UnicodeEncodeError
# replaced the actual build error and made the real cause invisible.
for _stream in (sys.stdout, sys.stderr):
    _reconfigure = getattr(_stream, "reconfigure", None)
    if callable(_reconfigure):
        try:
            _reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):
            pass

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPEC_FILE = os.path.join(PROJECT_ROOT, "installer", "tenths.spec")
DIST_DIR = os.path.join(PROJECT_ROOT, "dist")
ISS_FILE = os.path.join(PROJECT_ROOT, "installer", "tenths_setup.iss")


def build_pyinstaller():
    """Run PyInstaller to create the application bundle."""
    print("=" * 60)
    print("Building Tenths with PyInstaller...")
    print("=" * 60)

    # Clean previous build
    for d in ['build', 'dist']:
        path = os.path.join(PROJECT_ROOT, d)
        if os.path.exists(path):
            print(f"  Cleaning {d}/...")
            shutil.rmtree(path)

    # Run PyInstaller
    cmd = [
        sys.executable, '-m', 'PyInstaller',
        '--clean',
        '--noconfirm',
        SPEC_FILE,
    ]
    print(f"  Command: {' '.join(cmd)}")
    print()

    result = subprocess.run(cmd, cwd=PROJECT_ROOT)
    if result.returncode != 0:
        print("\n❌ PyInstaller build FAILED")
        sys.exit(1)

    # Verify output
    exe_path = os.path.join(DIST_DIR, "Tenths", "Tenths.exe")
    if os.path.exists(exe_path):
        size_mb = os.path.getsize(exe_path) / 1_000_000
        print(f"\n✅ Build successful: {exe_path}")
        print(f"   Exe size: {size_mb:.1f} MB")

        # Check total dist size
        total = sum(
            os.path.getsize(os.path.join(dirpath, f))
            for dirpath, _, filenames in os.walk(os.path.join(DIST_DIR, "Tenths"))
            for f in filenames
        )
        print(f"   Total bundle: {total / 1_000_000:.1f} MB")
    else:
        print(f"\n❌ Expected output not found: {exe_path}")
        sys.exit(1)

    return exe_path


def build_installer():
    """Run Inno Setup to create the Windows installer."""
    print("\n" + "=" * 60)
    print("Building Windows installer with Inno Setup...")
    print("=" * 60)

    # Find Inno Setup compiler
    iscc_paths = [
        r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
        r"C:\Program Files\Inno Setup 6\ISCC.exe",
    ]
    iscc = None
    for p in iscc_paths:
        if os.path.exists(p):
            iscc = p
            break

    if not iscc:
        print("\n⚠️  Inno Setup not found. Install from: https://jrsoftware.org/isinfo.php")
        print("   Skipping installer creation. PyInstaller bundle is ready in dist/Tenths/")
        return None

    cmd = [iscc, ISS_FILE]
    print(f"  Command: {' '.join(cmd)}")
    result = subprocess.run(cmd)
    if result.returncode != 0:
        print("\n❌ Inno Setup build FAILED")
        sys.exit(1)

    output_path = os.path.join(PROJECT_ROOT, "installer", "Output", "TenthsSetup.exe")
    if os.path.exists(output_path):
        size_mb = os.path.getsize(output_path) / 1_000_000
        print(f"\n✅ Installer created: {output_path}")
        print(f"   Size: {size_mb:.1f} MB")
        return output_path
    else:
        print(f"\n⚠️  Installer output not found at expected path")
        return None


def main():
    full_build = '--full' in sys.argv

    # Step 1: PyInstaller
    exe_path = build_pyinstaller()

    # Step 2: Inno Setup (optional)
    if full_build:
        build_installer()
    else:
        print("\n💡 To also build the installer, run: python installer/build.py --full")

    print("\n" + "=" * 60)
    print("DONE")
    print("=" * 60)


if __name__ == "__main__":
    main()
