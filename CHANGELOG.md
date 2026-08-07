# Changelog

All notable changes to Tenths are recorded here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and
versioning follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

While Tenths is in beta the internal version stays `0.9.0`; the tag suffix
(`v0.9.0-beta.N`) distinguishes builds. Normal semver resumes at `1.0.0`.

## [Unreleased]

Nothing yet.

## [v0.9.0-beta.3] — 2026-08-07

### Added

- **Imperial/metric unit toggle.** Reports, session notes, generated track maps
  and CLI output can render in km/h and °C instead of mph and °F. Switch it from
  the tray with the new **Metric Units (km/h)** item, which takes effect on your
  next session without restarting Tenths. Also available as
  `tenths config --units metric`, the `units` key in `settings.json`, or the
  `TENTHS_UNITS` environment variable.
- `CHANGELOG.md`, this file.

### Changed

- **The analysis pipeline now stores SI throughout** (m/s, °C, metres) and
  converts once at the boundary that renders a value. Previously conversions were
  scattered inline through the analyzer, which made a unit toggle impossible
  without touching every calculation. Imperial output is unchanged.
- Speeds are no longer rounded inside the analyzer. Rounding to one decimal in
  m/s is 2.24× coarser than in mph, which was enough to shift the calibrated
  coaching thresholds by 2–5% and silently change which corners get flagged.
  Rounding now happens only where a value is displayed.
- `session_summary.json` is unchanged and stays in mph regardless of the toggle.
  It is a machine contract read by the session index and the progression logic, so
  its shape must not depend on a display preference. Schema stays `1.0.0`.
- Seven absolute mph thresholds that were inline literals in the analyzer are now
  named SI constants, including the one gating whether throttle-exit metrics are
  computed at all.

### Fixed

- `tenths incident` no longer prints mph unconditionally, and its sudden-drop and
  stopped-car thresholds convert with the display unit instead of silently
  becoming 30 km/h and 5 km/h.
- Generated track maps write their speed labels from the active unit rather than
  hardcoding `mph`.
- `release.py` refused to publish when local was *behind* `origin/main` but not
  when it was *ahead*. It would have tagged and released an installer built from
  unpushed commits, so testers could download a build whose source was not in the
  repository while `main` sat behind its own latest release.
- `tenths.units`, `tenths.jsonio` and `tenths.index_generator` were missing from
  the PyInstaller `hiddenimports` list. Static analysis bundled them anyway, so no
  build was broken, but the list is meant to be exhaustive for first-party
  modules.

### Documentation

- `tenths/units.py` is now the single authoritative units contract — the rule, the
  four display boundaries, what deliberately is not one, and the traps. Other
  sites point at it rather than restating it.
- `docs/OUTSTANDING_ISSUES.md` is marked **HISTORICAL — DO NOT EXECUTE**. It read
  as a live build sheet for nine open issues; eight are resolved and the ninth is
  deferred, and it quoted a stale test count, bundle size and constant names.
- Development standards now target an AI maintainer rather than a human team:
  invariants encoded as tests instead of comments, one authoritative location per
  contract, and superseded documents marked loudly at the top.
- Recorded an unrelated finding for later: T19 at COTA reports a 128.5 m
  brake-point spread against 7–23 m elsewhere. The attribution is correct, but the
  corner is near-flat for a GT3, so the measurement likely mixes braking and
  non-braking laps and the resulting advice is misleading.

## [v0.9.0-beta.2] — 2026-08-02

### Added

- **Browse Sessions** in the tray menu, opening the master session index.
- `docs/RELEASING.md`, a quick reference for cutting a beta build.

### Fixed

- `index.html` was not fully offline. It now embeds its fonts as base64
  `@font-face` declarations like the session report does, so it makes no external
  requests.

## [v0.9.0-beta.1] — 2026-08-02

First beta, closing 22 of the 23 issues raised in the pre-release review
(`docs/RELEASE_REMEDIATION_PLAN.md`). Highlights from that work:

### Added

- Windows installer, system tray app, and a file watcher that processes sessions
  automatically, including any recorded while Tenths was not running.
- HTML session report with a Summary and Detailed view, track map, telemetry
  traces, lap comparison and per-corner coaching.
- Session notes in markdown, a machine-readable `session_summary.json`, and a
  master session index.
- Race result parsing for finishing position and iRating change.
- `tenths config` for resolved paths and settings, retry-and-notify on failure,
  and a rotating log.
- `release.py`, automating the release pipeline end to end.

### Fixed

- Coaching thresholds now scale with corner speed instead of using fixed mph
  bands, validated across 8 sessions, 4 car models and 2.3–6.4 km tracks.
- The over-braking diagnosis could never fire; retuned so it flags genuinely
  over-slowed corners.
- The session report is fully offline — Leaflet, Chart.js and all fonts are
  inlined, so it makes no external requests.
- Generated track maps are written to `%LOCALAPPDATA%` instead of the install
  directory, where an upgrade or uninstall destroyed them.
- False personal bests caused by NumPy values serializing incorrectly.
- Progression tracking across nested dates and multiple same-day sessions.
- Manual processing produces a complete artifact set per session and archives only
  after success.

### Notes

- Builds are unsigned. Windows SmartScreen will warn on first run; code signing is
  tracked in `docs/POST_MVP.md`.
- Landmark data is MIT-licensed from CrewChief. See `THIRD_PARTY_NOTICES.md`.

[Unreleased]: https://github.com/jgarbiso/Tenths/compare/v0.9.0-beta.3...HEAD
[v0.9.0-beta.3]: https://github.com/jgarbiso/Tenths/compare/v0.9.0-beta.2...v0.9.0-beta.3
[v0.9.0-beta.2]: https://github.com/jgarbiso/Tenths/compare/v0.9.0-beta.1...v0.9.0-beta.2
[v0.9.0-beta.1]: https://github.com/jgarbiso/Tenths/releases/tag/v0.9.0-beta.1
