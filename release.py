"""
Tenths Release Script
======================
Automates the full release pipeline: kill → test → build → smoke test → tag → hash → release.

Usage:
    python release.py "Short description of changes"
    python release.py "Browse Sessions, offline index" --dry-run

The description becomes the tag message and the release notes heading.
"""

import hashlib
import json
import os
import re
import subprocess
import sys

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
INSTALLER_PATH = os.path.join(PROJECT_ROOT, "installer", "Output", "TenthsSetup.exe")
EXE_PATH = os.path.join(PROJECT_ROOT, "dist", "Tenths", "Tenths.exe")
VERSION_PREFIX = "v0.9.0-beta"


def run(cmd, cwd=None, check=True, capture=False):
    """Run a command, print it, and optionally return output."""
    print(f"  $ {cmd}")
    kwargs = {"cwd": cwd or PROJECT_ROOT, "shell": True}
    if capture:
        kwargs["capture_output"] = True
        kwargs["text"] = True
    result = subprocess.run(cmd, **kwargs)
    if check and result.returncode != 0 and not capture:
        print(f"\n  FAILED (exit {result.returncode})")
        sys.exit(1)
    return result


def get_next_tag():
    """Determine the next beta tag number."""
    result = run(f'git tag --list "{VERSION_PREFIX}.*"', capture=True)
    existing = result.stdout.strip().split("\n") if result.stdout.strip() else []
    numbers = []
    for tag in existing:
        match = re.search(r"beta\.(\d+)$", tag)
        if match:
            numbers.append(int(match.group(1)))
    next_num = max(numbers) + 1 if numbers else 1
    return f"{VERSION_PREFIX}.{next_num}"


def sha256(filepath):
    """Compute SHA256 hash of a file."""
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest().upper()


def main():
    # Parse arguments
    dry_run = "--dry-run" in sys.argv
    args = [a for a in sys.argv[1:] if not a.startswith("--")]

    if not args:
        print("Usage: python release.py \"Short description of changes\"")
        print("       python release.py \"Fix corner detection\" --dry-run")
        sys.exit(1)

    description = args[0]
    tag = get_next_tag()

    print(f"\n{'='*60}")
    print(f"RELEASING: {tag}")
    print(f"Description: {description}")
    if dry_run:
        print("MODE: DRY RUN (no tag, no release)")
    print(f"{'='*60}\n")

    # ── Step 1: Preflight checks ──────────────────────────────────────────
    print("[1/7] Preflight checks...")

    # Working tree must be clean
    result = run("git status --porcelain", capture=True)
    if result.stdout.strip():
        print(f"\n  ERROR: Working tree is not clean:")
        print(f"  {result.stdout.strip()}")
        print(f"\n  Commit or stash your changes first.")
        sys.exit(1)
    print("  Working tree: clean")

    # Must be on main
    result = run("git branch --show-current", capture=True)
    branch = result.stdout.strip()
    if branch != "main":
        print(f"\n  ERROR: Not on main (currently on '{branch}')")
        sys.exit(1)
    print(f"  Branch: {branch}")

    # Must be up to date with remote
    run("git fetch origin main", capture=True)
    result = run("git rev-list HEAD..origin/main --count", capture=True)
    behind = int(result.stdout.strip())
    if behind > 0:
        print(f"\n  ERROR: Local is {behind} commit(s) behind origin/main. Pull first.")
        sys.exit(1)
    print("  Up to date with origin")

    # gh CLI must be available
    result = run("gh auth status", capture=True, check=False)
    if result.returncode != 0:
        print("\n  ERROR: gh CLI not authenticated. Run: gh auth login")
        sys.exit(1)
    print("  gh CLI: authenticated")

    # ── Step 2: Run tests ─────────────────────────────────────────────────
    print(f"\n[2/7] Running test suite...")
    result = run("python -m pytest tests/ -q --tb=short", capture=True)
    # Find the summary line
    lines = result.stdout.strip().split("\n")
    summary_line = [l for l in lines if "passed" in l]
    if result.returncode != 0 or not summary_line:
        print(f"\n  TESTS FAILED:")
        print(result.stdout[-500:] if len(result.stdout) > 500 else result.stdout)
        sys.exit(1)
    print(f"  {summary_line[-1].strip()}")

    # ── Step 3: Kill running instance ─────────────────────────────────────
    print(f"\n[3/7] Stopping any running Tenths...")
    run("taskkill /IM Tenths.exe /F", check=False, capture=True)
    print("  Done")

    # ── Step 4: Build ─────────────────────────────────────────────────────
    print(f"\n[4/7] Building installer...")
    result = run("python installer/build.py --full", capture=True)
    if not os.path.exists(INSTALLER_PATH):
        print(f"\n  BUILD FAILED — installer not found at {INSTALLER_PATH}")
        print(result.stdout[-1000:] if len(result.stdout) > 1000 else result.stdout)
        sys.exit(1)

    size_mb = os.path.getsize(INSTALLER_PATH) / 1_000_000
    print(f"  Installer: {size_mb:.1f} MB")

    # ── Step 5: Smoke test ────────────────────────────────────────────────
    print(f"\n[5/7] Smoke test...")
    # The frozen exe is a windowed app that uses AttachConsole to write to the
    # parent terminal. subprocess.PIPE can't capture that. Instead, verify the
    # exe starts and exits cleanly (returncode 0) with the config subcommand.
    result = subprocess.run(
        f'"{EXE_PATH}" --version',
        capture_output=True, text=True, shell=True, cwd=PROJECT_ROOT, timeout=30,
    )
    # --version may also write to the attached console, so just check it didn't crash
    if result.returncode != 0:
        print(f"\n  SMOKE TEST FAILED — exit code {result.returncode}")
        sys.exit(1)
    # Also verify the exe file exists and is reasonably sized
    exe_size = os.path.getsize(EXE_PATH) / 1_000_000
    if exe_size < 5:
        print(f"\n  SMOKE TEST FAILED — exe is only {exe_size:.1f} MB (expected ~10+)")
        sys.exit(1)
    print(f"  Tenths.exe: OK ({exe_size:.0f} MB, exits cleanly)")

    # ── Step 6: Tag and hash ──────────────────────────────────────────────
    print(f"\n[6/7] Tagging {tag}...")
    file_hash = sha256(INSTALLER_PATH)
    print(f"  SHA256: {file_hash}")

    if dry_run:
        print(f"\n  DRY RUN — would tag {tag} and create release")
        print(f"  Done.")
        return

    run(f'git tag -a {tag} -m "{description}"')
    run(f"git push origin {tag}", capture=True)
    print(f"  Tag pushed: {tag}")

    # ── Step 7: Create GitHub release ─────────────────────────────────────
    print(f"\n[7/7] Creating GitHub release...")

    notes = (
        f"## Changes\n\n"
        f"- {description}\n\n"
        f"## Install\n\n"
        f"Download `TenthsSetup.exe` below and run it over your existing install. "
        f"Your reports and settings are preserved.\n\n"
        f"Click **More info** → **Run anyway** on the SmartScreen warning "
        f"(the build is not code-signed yet).\n\n"
        f"## Checksum\n\n"
        f"SHA256: `{file_hash}`\n"
    )

    # Write temp notes file (avoids shell escaping issues)
    notes_file = os.path.join(PROJECT_ROOT, "_release_notes_tmp.md")
    with open(notes_file, "w", encoding="utf-8") as f:
        f.write(notes)

    run(f'gh release create {tag} "{INSTALLER_PATH}" --title "{tag}" --notes-file "{notes_file}"')
    os.remove(notes_file)

    print(f"\n{'='*60}")
    print(f"RELEASED: {tag}")
    print(f"https://github.com/jgarbiso/Tenths/releases/tag/{tag}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
