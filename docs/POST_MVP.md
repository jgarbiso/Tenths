# Post-MVP Roadmap

Items that are not required for beta distribution but should be addressed before or during public release.

---

## Code Signing (RR-011)

**Priority:** Before public release
**Effort:** ~1 hour + ~$70/year certificate cost

Windows SmartScreen shows an "unrecognized app" warning for unsigned executables. Beta testers click through it (documented in BETA_TESTING.md), but public distribution needs a signature for trust.

**Steps:**
1. Purchase a code-signing certificate (Certum Open Source ~$70/year, or SSL.com ~$90/year)
2. Add `signtool sign` to `installer/build.py` as an optional `--sign` step
3. Sign both `dist\Tenths\Tenths.exe` and `installer\Output\TenthsSetup.exe`
4. After ~50-100 downloads, SmartScreen reputation builds and the warning disappears entirely

**Note:** EV certificates ($300+/year) skip the reputation phase but are overkill for a free tool.

---

## Documentation Final Pass (RR-017)

**Priority:** Before public release
**Effort:** 30 minutes

One read-through of README.md and docs/GETTING_STARTED.md to confirm every claim matches the shipped application. Most stale claims were fixed during development; this is a final sweep.

---

## Per-Session Manual Processing — Rename Notes Function

**Priority:** Low (cosmetic)
**Effort:** 5 minutes

`generate_day_notes()` in `process.py` is now called with a single session, not a day. The function works correctly but the name is misleading. Rename to `generate_session_notes()` next time someone touches the notes generator.

---

## Standalone Race Results (P3 from TECH_DEBT.md)

**Priority:** High — after MVP
**Effort:** ~half day

A command like `tenths results "path/to/eventresult.json"` that creates a minimal session entry (car/track/date from result metadata) with race_result populated but no telemetry fields. Appears in the index and contributes to iRating tracking. Solves the case where telemetry wasn't recorded but the race result exists.

---

## Over-Braking Threshold Monitoring (RR-022 follow-up)

**Priority:** Monitor during beta
**Effort:** None until feedback arrives

The retuned 7%/1.5 mph threshold fires on genuinely over-slowed corners in testing. Watch beta feedback: if it never fires for a user across many sessions, the threshold may still be too high. If it fires on most corners, it's too sensitive. Revisit if either pattern emerges.

---

## Class-Specific Physics Profiles

**Priority:** After beta feedback
**Effort:** Multi-session validation per class

Currently only GT4 has validated coaching thresholds. GT3, prototypes, formula cars, and stock cars all use the Generic profile. Adding a class means validating braking shape targets, shift timing, and trail-braking rules against real sessions in that class.

---

## Reprocess Command

**Priority:** Medium
**Effort:** ~2 hours

`tenths reprocess [date]` or `tenths reprocess --today` — scans the archive for files matching a date and re-runs the full pipeline. Useful when: track map was updated, code changed coaching logic, or reports need regeneration after a bug fix.

---

## Bundle Size Reduction

**Priority:** Low
**Effort:** Investigation

The bundle is 80.9 MB (mostly numpy + pandas + PIL, all genuinely used). The only path to significant reduction is replacing pandas DataFrames with raw numpy arrays in `analyzer.py`, which is a major rewrite. Not worth it unless the installer size becomes a distribution concern.
