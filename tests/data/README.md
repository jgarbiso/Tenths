# Test telemetry fixtures

Real iRacing sessions, trimmed and anonymised so they can be committed. Integration
tests use these when the full sessions are not present on the machine, which means
the `.ibt` parsing and analysis pipeline is covered on any checkout, including CI.

| Fixture | Source session | Laps kept | Size |
|---|---|---|---|
| `bmwm2csr_winton national 2026-06-06 22-26-36.ibt` | BMW M2 CS Racing, Winton National, race | 2–6 | ~5.9 MB |
| `bmwm4evogt4_midohio full 2026-06-02 20-48-57.ibt` | BMW M4 GT4 EVO, Mid-Ohio Full, practice | 3–7 | ~6.1 MB |

## What was changed

Telemetry samples are copied through **unmodified**, so these are genuinely real
data for the laps they retain. Lap times were verified identical to the original
files. Two things were changed:

1. **Identities removed.** An `.ibt` embeds the full driver list for the session:
   real names, iRacing customer IDs, abbreviations, initials and team names. The
   Winton race listed 12 people. Every identity is replaced with `Test Driver` /
   `UserID 0`, including the recording driver's. `QualifyResultsInfo`, `CameraInfo`,
   `RadioInfo`, `SplitTimeInfo` and `CarSetup` are dropped entirely — the analyser
   does not read them and they can carry further personal or setup detail.

2. **Size reduced.** Full sessions are 52 MB and 170 MB, mostly channels the
   analyser never reads (283 channels, ~1100 bytes per sample). Only the ~52
   channels the analyser uses are kept, and only a few laps, giving roughly a
   9–28x reduction.

## Regenerating

```cmd
python tools/make_test_fixture.py "<source.ibt>" "tests/data/<name>.ibt" --laps 5
```

The tool refuses to write if any identity survives its own audit. To check an
existing file:

```cmd
python tools/make_test_fixture.py "<file.ibt>" --inspect
```

`tests/test_fixture_privacy.py` enforces all of this on every test run, so an
unscrubbed fixture fails the suite before it can be published.

> `.gitignore` excludes `*.ibt`. These files are allowed by an explicit
> `!tests/data/*.ibt` exception — if a new fixture appears to vanish, that is why.
