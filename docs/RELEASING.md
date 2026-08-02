# Releasing a New Beta Build

Quick reference for cutting a new release after changes are merged to main.

---

## Prerequisites

- All changes committed and pushed to `main`
- Suite passing: `python -m pytest tests/ -q`
- `gh` CLI installed and authenticated (`gh auth status`)
- Inno Setup installed (verified: `C:\Program Files (x86)\Inno Setup 6\ISCC.exe`)

---

## The process (5 minutes)

### 1. Kill any running instance

```cmd
taskkill /IM Tenths.exe /F
```

### 2. Build

```cmd
cd c:\Users\justi\Documents\Sim\Tenths
python installer/build.py --full
```

This produces:
- `dist\Tenths\Tenths.exe` (portable folder, ~85 MB)
- `installer\Output\TenthsSetup.exe` (installer, ~30 MB)

### 3. Smoke test

Run the new build briefly to confirm it starts:

```cmd
dist\Tenths\Tenths.exe config
```

Should print paths without error. Optionally start the tray and confirm it appears.

### 4. Tag

Pick the next beta number (check `git tag --list "v0.9.0-beta.*"` for the latest):

```cmd
git tag -a v0.9.0-beta.N -m "Short description of what changed"
git push origin v0.9.0-beta.N
```

### 5. Get the checksum

```powershell
(Get-FileHash installer\Output\TenthsSetup.exe -Algorithm SHA256).Hash
```

### 6. Create the GitHub release

```cmd
gh release create v0.9.0-beta.N installer\Output\TenthsSetup.exe --title "v0.9.0-beta.N" --notes "## Changes\n\n- Thing that changed\n- Other thing\n\n## Checksum\n\nSHA256: PASTE_HASH_HERE"
```

Or for longer notes, write a file and use `--notes-file`:

```cmd
gh release create v0.9.0-beta.N installer\Output\TenthsSetup.exe --title "v0.9.0-beta.N" --notes-file release_notes.md
```

### 7. Done

Testers go to https://github.com/jgarbiso/Tenths/releases, download the latest `TenthsSetup.exe`, and install over the top of their existing install.

---

## One-liner (when you're in a hurry)

```cmd
taskkill /IM Tenths.exe /F & python installer/build.py --full & dist\Tenths\Tenths.exe config
```

If the config prints cleanly, tag and release.

---

## Version numbering

| Phase | Tag format | Example | When to bump |
|---|---|---|---|
| Beta | `v0.9.0-beta.N` | `v0.9.0-beta.3` | Every time you ship to testers |
| Release candidate | `v0.9.0-rc.N` | `v0.9.0-rc.1` | When all NO-GO blockers are closed |
| Public release | `v0.9.0` | `v0.9.0` | First public non-beta |
| Patches | `v0.9.1` | `v0.9.1` | Bug fixes after release |

The version in `pyproject.toml` / `config.py` / `__init__.py` stays `0.9.0` throughout beta. It bumps when you cut the first non-beta release.

---

## What testers need to know

Tell them: "New build is up — go to Releases, download the installer, run it over the top of the old one. Your reports and settings survive."

They don't need to uninstall first. The installer uses `Flags: ignoreversion` which overwrites cleanly.

---

## If something goes wrong

- **Build fails:** Read the error. Common cause: a Python syntax error in report.py's JS string (compileall won't catch it, but the test suite will).
- **Installer won't overwrite:** Tenths.exe is still running. Kill it first.
- **Tag already exists:** You can't reuse a tag. If you need to redo: `git tag -d v0.9.0-beta.N && git push --delete origin v0.9.0-beta.N`, then re-tag.
- **Release needs updating:** `gh release edit v0.9.0-beta.N --notes "new notes"` or upload a replacement asset with `gh release upload v0.9.0-beta.N installer\Output\TenthsSetup.exe --clobber`.
