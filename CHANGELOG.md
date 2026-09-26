# Changelog

All notable changes to Tenths are recorded here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and
versioning follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

While Tenths is in beta the internal version stays `0.9.0`; the tag suffix
(`v0.9.0-beta.N`) distinguishes builds. Normal semver resumes at `1.0.0`.

## [Unreleased]

### Added

- **Setup notebook.** Each processed session is added to
  `setup_notebook/<car>/<track>.md` beside your telemetry: the setup as driven,
  what changed since the previous session, pace, a balance profile (steering
  needed per unit of rotation, and countersteer events, by corner speed and
  phase), tyre temperatures inner/middle/outer, hot pressures, pit-in carcass
  temps and tread used, and ride height. It is written for an AI agent to read and
  recommend a Fastest, Balanced or Stable setup from; `ENGINEER.md` in the folder
  holds the agent's instructions. New commands: `tenths notebook`,
  `tenths notebook rebuild [car]`, `tenths notebook limits <car>`, and
  `tenths config --setup-notebook on|off`. A notebook failure never stops a
  session from being processed.
- The notebook compares balance **at equal lateral g**, reports how hard the car
  was driven, and shows a **noise floor** from sessions run on the same setup, so
  a faster driver is not mistaken for a car with more understeer. Balance is
  measured only once tyre pressures have settled, every countersteer moment of
  0.25 s or longer is listed with its corner (including crash laps), and a
  falling lap-time trend is flagged as the driver still improving. Setup values
  are shown in your display units and snapped to the garage's step using an
  optional per-car `limits.json`.
- Each notebook session links to its session report and carries that report's
  per-corner figures (entry and apex speed, minimum-speed spread, time lost,
  trail-braking diagnosis) with changes against the comparison session. A crash
  stint too short to measure is listed but never used as the comparison base.
- `car_notes.md` per car holds lessons that carry across tracks; each track's
  `.notes.md` holds its experiment log. `ENGINEER.md` tells the agent to read and
  maintain both.
- The notebook takes lap times and lap validity from the analyzer's corrected
  lap timing (see Fixed), so a session such as Road America 2026-09-15 21:49,
  which previously had "no valid laps", is recorded.
- In-car settings (brake bias, TC, ABS, throttle map) are taken from live
  telemetry. The garage snapshot in the `.ibt` header can differ from what was
  driven — at Road Atlanta it recorded TC 1 / ABS 4 / 53.0% bias for a session run
  entirely on TC 4 / ABS 3 / 51.5%.

### Changed

- **The Summary map is larger and its corner labels no longer collide.** The
  canvas was a fixed 280×280 square, so a wide circuit drew small with most of the
  height unused. It now sizes itself from the track's real proportions inside a
  wider column. Labels were drawn at a fixed offset above their marker, which put
  T12 and T13 at COTA — 4.9% of a lap apart — directly on top of each other. They
  are now placed as a set, separated where they would overlap, clamped inside the
  canvas, joined to their marker by a leader line, and drawn on an opaque chip so
  the track outline no longer runs through the text.
- Focus corners carry a priority number, repeated inside the matching map marker,
  so two nearby corners can be told apart without tracing the outline. The number
  is read back from the rendered cards rather than from analysis order, because
  the Next Race Focus applies its own selection rules and is not always the
  highest-loss corner.
- **The Detailed track map now labels all known corners**, not just detected
  braking zones. Corners from the bundled landmark database that did not trigger
  zone detection are shown as passive grey labels, so the driver can orient
  themselves on the full circuit. At Mid-Ohio this adds 9 corner names (T1, T3,
  T5 Madness, T6 Esses, T7 Thunder Valley, T10, T11, T10 Carousel, T13) where
  previously only the 2–3 heavy-braking corners were labelled. Labels within 5%
  of an existing braking-zone label are suppressed to avoid duplicates.

### Fixed

- **Every lap was analysed with the previous lap's time.** iRacing writes a lap's
  time into `LapLastLapTime` about 1-2 seconds after the lap counter ticks over,
  and Tenths read it on the lap's final sample, one lap too early. The fastest
  time was right but was attached to the following lap, so the braking, trail
  braking, tyre, exit and apex coaching all came from the wrong lap. At Road
  Atlanta that was the 92.1 s lap, not the 82.1 s best. Lap times now come from
  one helper that waits for the new value, and the first timed lap of a stint is
  no longer dropped as untimed. Existing reports are not rewritten; a session
  shows the corrected best lap once it is processed again.
- **Tyre inner/outer temperatures were swapped on the left-side tyres (LF, LR).**
  iRacing's L/M/R channels are the left, middle and right edges seen from behind
  the car, so on a left tyre the left edge is the *outer* one — iRacing's garage
  labels left tyres "O M I" and right tyres "I M O". Tenths read the left edge as
  inner on all four tyres, so `session_summary.json`, the session report and the
  session notes showed LF and LR inner/outer the wrong way round, and any camber
  or pressure conclusion drawn from them was backwards. The mapping now lives in
  one place (`tenths/tyres.py`). Right-side tyres and the per-tyre average were
  always correct. The summary schema is unchanged (same keys, same units), so
  there is no schema version bump or migration; sessions processed before this
  fix keep the swapped LF/LR values until they are re-analyzed.
- The Summary map scaled longitude and latitude identically, stretching every
  circuit horizontally — about 16% at COTA — so its shape disagreed with the
  Leaflet map on the Detailed tab. Longitude is now scaled by `cos(latitude)`.

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
