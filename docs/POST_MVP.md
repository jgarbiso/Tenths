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

## Track Data Integrity — Validate Landmark Data on Load

**Priority:** Next patch. Not a beta blocker, but do it before building anything else on this data.
**Effort:** ~1 hour including tests
**Found:** 2026-08-07, while assessing whether track sections could be derived from bundled data.

Four tracks in `tenths/data/trackLandmarksData.json` carry corrupt corner records, and
`tenths/track_map.py` has **no validation of any kind** — checked for `raise`, `warn`,
`validate` and `log`, none are present. Bad upstream data reaches the report silently.

### What is actually wrong

A corner whose `distanceRoundLapEnd` precedes its `distanceRoundLapStart` produces a
reversed `pct_range`, and `get_turn_name()`'s phase-1 test `low <= pct <= high` can then
never be true — the corner becomes unreachable at every position on the lap.

| Track | Bad record | Effect |
|---|---|---|
| `barcelona gp` | T9 `2800 → 2005 m` | T9 unreachable; range `(61.2, 43.8)` |
| `aragon gp` | T10 `2236 → 473 m` | T10 unreachable; range `(42.3, 8.9)` |
| `aragon moto` | T10 `2236 → 473 m` | T10 unreachable; range `(44.5, 9.4)` |
| `martinsville` | T3 `481 → 474 m` | T3 collapses to a 7 m sliver |

**The failure mode is a wrong name, not a missing one.** Phase 2 of `get_turn_name()`
falls back to the nearest zone centre within tolerance, so the stretch T9 should own gets
labelled with its neighbours. Measured on `barcelona gp`:

```
 42%  ->  'T4'
 45%  ->  'T5'     <- T9 territory
 50%  ->  'T6'     <- T9 territory
 55%  ->  'T7'     <- T9 territory
 58%  ->  'T8'     <- T9 territory
 61%  ->  'T8'     <- T9 territory
 63%  ->  '(63.0%)'
```

A driver is told to work on T7 when the measurement came from T9.

### Two systemic issues behind it

**The fuzzy tolerance is a percentage, so it means wildly different distances.**
`get_turn_name(track_map, pct, tolerance=5.0)` is 5% of a lap:

| Track | 5% tolerance |
|---|---|
| `nurburgring nordschleifetourist` | 946 m |
| `roadamerica full` | 321 m |
| `cota gp` | 271 m |
| `martinsville` | 39 m |
| `limaland` | 21 m |

At the Nordschleife a corner name can be applied to a point 946 m away. This is the
mechanism that converts "no match" into a confidently wrong answer.

**Duplicate names can corrupt the report's internal joins.** At Barcelona both 58% and
61% return `'T8'`. `report.py`'s `buildCorner()` joins corner data on turn name:

```javascript
const zone = (bz || []).find(z => z.turn_name === c.turn_name);
```

`.find()` silently takes the first match, so two braking zones sharing a name would show
one zone's telemetry under two different corners. **Not confirmed on a real session** — no
Barcelona `.ibt` was available to test — but it is the same duplicate-key class of defect
that the independent coaching review found with the T12/T13 throttle values.

### What is NOT wrong

The metres-to-percentage conversion is sound. `_load_from_landmarks()` divides corner
distances by the bundled `approximateTrackLength`, so a disagreement there would offset
every turn on every track. Measured against real telemetry lengths:

| Track | Bundled | Real | Error |
|---|---|---|---|
| `okayama full` | 3655 | 3654.2 | 0.02% |
| `roadamerica full` | 6414 | 6412.9 | 0.02% |
| `cota gp` | 5414 | 5413.3 | 0.01% |
| `coronado` | 5409 | 5409.2 | 0.00% |
| `oran gp` | 2601 | 2601.1 | 0.00% |

Worst-case displacement is 0.02% of a lap. That mechanism needs no change.

Also **benign, despite appearances:** `montreal` and `nurburgring nordschleifetourist` list
corners out of lap order in the JSON, but every range is valid. `get_turn_name()` iterates
all zones, so ordering does not matter. An earlier assessment called these broken; they are
not.

### Why this was not a beta blocker

Turn names are applied at display time. Lap times, braking-zone detection, loss
calculations, apex consistency and every coaching threshold run off `LapDistPct` and brake
pressure, none of which touch the name. The defect corrupts the label, not the
measurement. Four affected tracks out of 457, and beta already ships with much larger
documented gaps — 197 of 457 tracks have no corner names at all, and only corners above
the 50% brake threshold are analysed regardless.

### Required work

1. **Validate at load in `_load_from_landmarks()`.** Drop any corner where
   `end <= start`, or where `end` exceeds the track length. A dropped corner degrades to
   `(43.8%)`, which the report already renders and users have seen. Absent beats wrong.
2. **Log what was dropped**, with track and corner name. `track_map.py` currently has no
   logger; the rest of the package uses `tenths.applog.get_logger`.
3. **Change the tolerance to a distance in metres** so behaviour is consistent from a 427 m
   bullring to the 18.9 km Nordschleife. Converting at the call site needs the track
   length, which `_load_from_landmarks()` already reads.
4. **Guarantee unique turn names within a track** so the JavaScript joins cannot collide —
   suffix duplicates, or fall back to a percentage.

### Required tests

- A fixture with a reversed corner range is rejected, and the surrounding percentages
  return a percentage fallback rather than a neighbour's name.
- A fixture with a corner beyond track length is rejected.
- `barcelona gp`, `aragon gp`, `aragon moto` and `martinsville` each load without an
  unreachable corner. Assert against the production data file, so a future CrewChief update
  that reintroduces the problem fails the suite.
- No two zones in a loaded track share a `full` name.
- Tolerance behaves equivalently in metres across a short oval and a long road course.
- `montreal` and `nordschleifetourist` still load all their corners — they are valid and
  must not be caught by the new validation.

### Separate upstream track

The four bad records are in CrewChief's community-maintained, MIT-licensed landmark file.
Fixing them upstream helps every tool that consumes it. That is a data contribution, not a
code change, and does not remove the need for the validation guard — the file is updated
periodically and a future revision could introduce new bad records with no signal.

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

## Track Map Shadowing — Distinguish Edited from Pristine Skeletons

**Priority:** Medium
**Effort:** ~2 hours

RR-023 put user-generated track maps ahead of bundled maps in the read order, so a user's edits always win. The trade-off: a *pristine* auto-generated skeleton (generic "Turn 1, Turn 2" names) also wins, and would keep winning even if a later release ships a properly curated map for that track or fixes the fuzzy-matching bug (TM1) that caused the skeleton to be generated in the first place.

Generated files carry a marker: `<!-- Auto-generated by Tenths. Edit turn names manually. -->`. The fix is to treat a map that still has the marker *and* still has only generic turn names as lower priority than a bundled map, while a map whose names have been edited keeps winning. Resolves TM3 properly.

Workaround until then: `tenths config` prints the track-maps directory; a user can delete a stale skeleton.

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

## Brake Point Spread Outliers at Near-Flat Corners

**Priority:** Low — investigate if beta feedback flags odd brake-reference advice
**Effort:** Half a day to diagnose

Found during the metric review of COTA practice (`ferrari296gt3_cota gp 2026-08-03 17-45-44`). Per-zone `spread_meters` across the six braking zones:

| Zone | Turn | Spread |
|---|---|---|
| 10.5% | T1 | 17.5 m |
| 44.6% | T11 | 13.9 m |
| 66.4% | T12 | 22.9 m |
| 77.4% | T15 | 8.5 m |
| **90.4%** | **T19** | **128.5 m** |
| 95.9% | T20 | 7.3 m |

T19 is an order of magnitude above every other zone, and it produced the coaching line "T19: Brake reference drifting ±129m — pick a fixed board marker". The attribution is correct — the value really is on the T19 zone, verified against `zone_pct` — so this is not a join bug.

The likely cause is that T19 is near-flat for a GT3: on some laps the driver brushes the brake and on others does not, so "first brake application in the zone" lands in completely different places lap to lap and the spread measures two different behaviours rather than one drifting reference. If so, the advice is misleading — the fix is not a fixed board marker.

Worth checking: whether `spread_meters` should be suppressed, or computed differently, when the zone's peak brake pressure is low or the brake application is intermittent across laps. Note the diagnosis threshold is a flat `spread_meters > 15`, another absolute limit that does not scale with zone length or entry speed — the same class of issue RR-021 and RR-022 addressed elsewhere.

Unrelated to the unit refactor; `spread_meters` is metres in both unit systems.

---

## Track Sections — Cover the Whole Lap, Not Just the Braking Zones

**Priority:** High. This is the structural fix for the biggest coaching gap.
**Effort:** 1–2 days, plus a decision on the fallback
**Blocked by:** Track Data Integrity above. Do not build on unvalidated landmark data.

Only corners above the 50% brake threshold produce a braking zone, so at COTA six of
twenty turns are analysed and roughly half the lap is invisible to the coaching. An
independent coaching review put it plainly: the tool confidently ranks the least important
third of the circuit while the esses, where COTA lap time is classically won, produce no
data at all. Sections that cover 100% of the lap are the fix.

### What "sector" means, and why we should avoid the word

Three different things get called sectors, and they do not agree:

| | Available? | Verified how |
|---|---|---|
| **iRacing timing sectors** (S1/S2/S3 in the F-bar and on results pages) | Live SDK only, via `SplitTimeInfo` | Absent from `/data/track/get` — 60 fields, none of them sectors. Absent from the `.ibt` file: no sector channels, no `SplitTimeInfo` section in the header. |
| **Real-life circuit sectors** (broadcast timing splits) | Would need its own dataset | Not investigated. Whether iRacing's sectors match real-life sectors is **unconfirmed**. |
| **Landmark-derived sections** | Bundled data we already ship | Corner positions in metres, per track |

Anything we derive is a fourth thing and will reconcile with none of the above. Calling it
"Sector 1" when it does not match the driver's F-bar is a self-inflicted credibility bug.
**Name sections after the track**, which is also better coaching:

```
The Esses (T2-T9)        18.4s   0.62s off your best
Back Straight (T11-T12)  21.1s   0.08s off
Stadium (T13-T18)        19.8s   0.48s off
```

This also fixes the mislabelling the review caught, where a 19.76 s loss window spanning
T13 to T18 — 15% of the lap — was attributed to "T13 throttle application".

### The data supports it, but not universally

Measured across the 457 iRacing tracks keyed in `trackLandmarksData.json`:

| | Count | Share |
|---|---|---|
| Usable — 4 or more corners and a track length | **257** | 56% |
| No corner landmarks at all | **197** | 43% |
| Fewer than 4 corners | 3 | `pocono 2016`, `monza junior`, `pocono oval` |
| Landmarks but no track length | 0 | — |

Corner gaps identify natural boundaries cleanly. At COTA the 1070 m gap between T11's exit
(2600 m) and T12's entry (3670 m) is unmistakably the back straight.

**Owner's own tracks: 16 of 23 would work.** Missing: `barber_2026`,
`daytona_rallycross_short`, `fuji_nochicane`, `navarra_speedlong`, `okayama`,
`summit_summit_raceway`. Note `okayama` has no corners while `okayama_full` has 11, so part
of the gap is slug matching rather than absent data.

### The open decision: what to do about the other 43%

The gap is not random — it is whole venues. A driver who mostly runs Barber or Summit would
never see the feature.

- **Derive from the driver's own telemetry.** Braking-zone detection and the GPS trace
  already exist, so sections can be inferred from where the car actually brakes and turns.
  Works on every track including ones iRacing adds tomorrow. Costs the naming: you get
  "Section 2 (28–45%)" rather than "the esses".
- **Show nothing.** Honest, leaves the coaching gap open on 43% of tracks.
- **Contribute the missing data upstream.** Permanent fix for every CrewChief consumer, but
  an ongoing data project rather than a code change.

The computation is identical either way — convert positions to `LapDistPct`, time between
boundaries. Landmark data only supplies better names when present. That argues for the
telemetry-derived fallback with landmark naming layered on top when available.

**Unresolved requirements question:** is a section without a real name still worth showing?
That determines whether this ships for 56% of tracks or all of them.

### Deliberately out of scope for a first pass

Matching iRacing's official sector boundaries. It requires reading `SplitTimeInfo` from the
live SDK during a session, which breaks the offline, self-contained guarantee — a feature
that only works after you have driven a track once is a poor fit. If it is ever added it
should be a *separate* "Sector Times" panel that genuinely reconciles with the F-bar, shown
alongside coaching sections rather than replacing them.

---

## Self-Calibrating Thresholds — RPM and Shifting Diagnostics

**Priority:** Next patch — fires wrongly today on every car whose redline isn't ~7000.
**Effort:** ~2 hours including tests
**Found:** 2026-08-07, while auditing the car-class system.

### The live defect

The Generic profile's RPM thresholds are **absolute numbers**, not relative to the car:

```python
# analyzer.py, braking_analysis()
if max_ds_rpm > 7000:                          # "Aggressive Shift"
    notes.append("Aggressive Shift")
if apex_rpm < 3500:                            # "Lugging"
    notes.append("Lugging")
```

What those mean depends entirely on the car being driven:

| Car | Redline | 7000 rpm is | Effect |
|---|---|---|---|
| `bmwm2g87` | 7000 | 100% of redline | never fires |
| `ferrari296gt3` | 8000 | 88% | fires on 4 of 6 COTA zones |
| `porsche992rgt3` | 9500 | 74% | fires on everything |

On the Ferrari 296 GT3, downshifting to 7100 rpm with an 8000 rpm redline is ordinary
driving. The report tells the driver "Aggressive Shift" at four corners every session.
Same for GT4: `> 7500 rpm` means redline-plus on a BMW M4 GT4 (7200 rpm), so it can only
fire under error conditions rather than being a graduated warning.

This is the same root cause as RR-021 (speed thresholds), RR-022 (over-braking), and the
`spread_meters > 15` brake-point issue: **absolute limits that should be fractions**.

### The fix needs zero new telemetry

Every `.ibt` already carries:

```
driver_car_redline     8000.0
driver_car_idle_rpm    2950.0
driver_gearbox_type    'Sequential'
```

So `max_ds_rpm > 7000` becomes something like `max_ds_rpm > 0.88 × redline`, and lugging
becomes a fraction of the idle→redline band rather than a constant. The existing 30 files
across six distinct cars (redlines 7000–9500) are enough to validate it immediately.

### Proposed thresholds (needs validation, not a decision)

| Rule | Current | Proposed |
|---|---|---|
| Aggressive Shift | `> 7000` (Generic) / `> 7500` (GT4) | `> 0.90 × redline` |
| Over-rev Risk | `> 7500` (GT4 only) | `> 0.97 × redline` |
| Lugging | `< 3500` (Generic) / `< 4000` (GT4) | `< idle + 0.15 × (redline - idle)` |
| Early Shift | `< 0.2 s` / `< 0.15 s` | unchanged (time-based, not RPM) |

Validation: re-run the existing 30 `.ibt` files with both old and new thresholds. The
Ferrari should stop firing "Aggressive Shift" on normal downshifts; the M2 (which sits at
its own redline) should continue to fire. If the Porsche stops firing on everything, the
fraction is correctly calibrated.

### Impact on the profile system

Once RPM is self-calibrating, the remaining GT4-only rules are:

- Lazy Initial Brake (`t2peak > 0.4 s`) — probably belongs in Generic too
- Late Brake Squeeze (ABS in 2nd half of zone) — probably belongs in Generic too
- Over-slowing — already speed-relative

The case for GT4 as a separate profile weakens considerably. Whether to keep it or fold
everything into one self-calibrating profile is a design call for after validation.

---

## Car Class Detection — Reliability Fixes

**Priority:** Next patch — same timeline as the RPM fix since they share the same module.
**Effort:** ~1 hour
**Found:** 2026-08-07

### Three defects in the existing detection

**1. The GT4 slug list is incomplete.** Five slugs cover perhaps half the GT4 cars on
iRacing. Eight known GT4 cars are not in the list: `mclaren570sgt4`,
`astonmartinvantagegt4`, `audir8gt4`, `camarogt4`, `mustanggt4`, `supragt4`,
`toyotagr86`, and `amgt4` (our `amg_gt4` wouldn't match the common `amgt4` slug either).

They are saved by the `"gt4" in class_short.lower()` check — but only when iRacing reports
a class name. When it reports a slug instead (see below), they get Generic silently.

**2. iRacing's `CarClassShortName` is unreliable.** Observed in production summaries:

```
porsche992rgt3   class_short = 'porsche992rgt3'   ← raw slug, not a class
porsche992rgt3   class_short = 'Touring'          ← wrong class entirely
ferrari296gt3    class_short = 'GT3 Class'        ← correct
ferrari296gt3    class_short = 'ferrari296gt3'    ← slug again, different session
```

A GT3 reported as `"Touring"` won't match `"gt3"`. Any future GT3 profile keyed purely on
the class string would miss that car in some sessions.

**3. A Test session sometimes sends `car_class_id = 0` and the slug as the class name.**
Session 2026-08-07 12-42-20 arrived with `car_class_short = 'ferrari296gt3'`, which is why
the report shows "Generic" as the car class — it's the slug, `_is_human_readable_class`
returned False, and `display_car_class()` fell through.

### Required fix

Cross-check slug and class string. Priority order:

1. `car_class_short` matches a known class name (case-insensitive, e.g. "GT4 Class") → use that
2. The *slug* matches the GT4 slug list → use GT4 regardless of what class_short says
3. Otherwise → Generic, and display whatever iRacing called it if it's human-readable

The slug check ensures detection works even when iRacing sends garbage in `class_short`,
which it demonstrably does.

### The `GT4_CARS` slug list should also be extended

Use `"gt4" in slug` as a catch-all alongside the explicit list, since every GT4 car's slug
contains the substring. The explicit list then only matters for cars whose slug doesn't
(none currently known, but defensive).

---

## Class-Specific Physics Profiles — Rearchitected

**Priority:** After the self-calibrating thresholds are validated
**Effort:** Potentially zero if self-calibration covers everything meaningful
**Previous framing:** "Multi-session validation per class." That framing was wrong.

### Why fewer profiles is better than more

The instinct is "add GT3, then LMP2, then Cup." That path requires:
- Access to every car class (costs real money, or iRacing AI workarounds)
- Multi-session validation per class (the GT4 rules came from dedicated testing)
- Ongoing maintenance as cars are added each season

Meanwhile, **most of what the profile actually gates is already expressible relative to
values the car reports about itself** — redline, idle RPM, the driver's own session
distribution. Making the thresholds self-calibrating removes the need for class-specific
overrides on most diagnoses, and means the 200+ iRacing cars nobody will ever hand-tune get
sensible coaching instead of Generic.

### What is genuinely class-specific (short list)

After self-calibrating RPM, the remaining differences are aero and suspension:

- **Braking shape.** High-downforce cars (GT3, LMP) want the brake spiked immediately
  because grip decays as speed falls. Low-downforce cars (touring, GT4 to some extent) want
  a progressive build. The measure is `t2peak` (time to peak brake) — currently gated on
  GT4 with a 0.4 s target. Whether that target applies to GT3 is unvalidated.
- **Trail braking tolerance.** A stiff GT3 rotates on trail brake; a softer touring car may
  not. Currently GT4 flags `Over-slowing (Trust GT4 Grip)` when apex brake > 15 — implying
  the car has enough mechanical grip to roll off the brake earlier. Whether GT3 should say
  the same thing at the same threshold is unconfirmed.

Both of these need real validation against real sessions. An AI race produces a clean
`.ibt` without needing to be fast in the car — useful for expanding coverage beyond what
the owner drives, if it ever proves necessary.

### What to do about this NOW

Nothing, beyond the RPM fix. The framing "GT3 is missing" makes it sound like a gap. The
honest reality is that Generic + self-calibrating thresholds is probably sufficient for beta
and possibly for v1.0, and that adding profiles without validation would just be
confidently wrong in a new way. **Wait for beta feedback** that says "your coaching is wrong
on my car, here is what it should say" before designing a class system.

### Also: the notes table hides data from Generic users

GT4 sessions display: `T2Peak | Coast | TIn Brk | ApxBrk`
Generic sessions display: `Brk2Shft | MaxDS RPM | Apex RPM`

Both sets of data exist for all cars. The independent coaching reviewer flagged
`apex_brake_pct = 0.0` across every COTA zone as clinically significant — the driver's
brake is fully released at the apex, which matters for rotation and implies trailable brake
is being wasted. But the Generic table doesn't show it, so the insight is invisible. At
minimum, a unified table that shows all columns regardless of profile would surface this
without needing per-class coaching rules to interpret it.

---

## End-of-Session Tire Wear Report

**Priority:** Medium — valuable for race sessions, low effort
**Effort:** ~half day

Show how well the driver managed their tires over the session. Answers: did I flat-spot?
Did I abuse one corner of the car? Is my wear even across the tread? How much life is left?

### Data available

The `.ibt` carries 12 wear channels at 60 Hz:

```
LFwearL, LFwearM, LFwearR    (left-front: left/middle/right tread)
RFwearL, RFwearM, RFwearR
LRwearL, LRwearM, LRwearR
RRwearL, RRwearM, RRwearR
```

Values are 0.0–1.0 where 1.0 is new rubber. Reading the final sample of the last valid lap
gives end-of-session remaining life. Reading first-lap vs last-lap shows the total wear
accumulated during the session.

### What to show

**Summary level:**
- Overall wear percentage per corner (average of L/M/R)
- Highlight any corner below 50% remaining or significantly worse than the others
- Flag flat-spotting: large L/M/R imbalance within a single corner (e.g., LF left tread at
  0.4 while middle is 0.7 → localized wear from a lockup)

**Detailed level:**
- Per-corner breakdown: L / M / R remaining
- Wear rate per lap (total wear / valid laps) — tells you whether the tires would have
  lasted a longer stint
- Wear delta across corners: "RF wore 2× faster than LR" → alignment issue or driving
  imbalance
- Wear curve across the session (first lap → last lap) — shows whether wear was linear
  (steady driving) or accelerating (degradation spiral)

**Coaching sentence (Summary Focus Card level):**
- "Right-front wore 40% faster than the average corner — check entry aggression into
  right-handers"
- "Left-front flat spot detected (0.31 vs 0.68 tread) — likely a lockup at T1"
- "Even wear across all four corners — good tire management"

### Session type context

Most useful for races (longer stints, tire conservation matters). For short practice
sessions, end-of-session wear is less meaningful — but a flat-spot is always worth flagging.
Gate the coaching messages on session length: full wear analysis for races and long tests
(>10 laps), flat-spot detection always.

### Display

- Session notes: new "Tire Wear" section with a 4-corner table
- HTML report: a tire wear card on the Detailed tab, similar to the existing Tire Temps
  card but showing remaining % instead of temperature
- Summary: only surfaces if something is notable (flat spot, one corner significantly worse)

### Also available but lower priority

`TireSetsUsed`, `TireSetsAvailable`, `PlayerTireCompound` — for multi-stint races, knowing
which tire set you're on and how many remain. Useful later for race strategy features but
not needed for the MVP tire-wear display.

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

---

## Lap Comparison Visual Identifier

**Priority:** High — before wider beta
**Effort:** ~1 hour

When comparing two laps in the Detailed view (via the Compare button), the traces overlap but there is no persistent legend indicating which lap is solid and which is dashed. The lap selectors show the lap numbers with a blue left-border on the comparison dropdown, but once your eyes are on the chart there's no inline label or color key saying "solid = Lap 11 (best), dashed = Lap 3."

**What's needed:**
- A small persistent label or color-coded legend near the telemetry chart header: e.g., "━ Lap 11 (2:13.5)  ┈ Lap 3 (2:19.8)" using the same solid/dashed styling as the traces
- Should update dynamically when either lap selector changes
- The speed delta panel (green/red shading) also needs context — which direction is "faster"? Currently it shows the delta but doesn't label which lap is the reference

**Current behavior:** The compare delta badge in the top-right says something like "−4.3s" which tells you the comparison lap is slower, but you have to remember which dropdown is which. In the heat of reviewing telemetry this is easy to lose track of.

**Reference:** The telemetry header row already has `crosshair-info` for hover data. The lap identity labels could sit next to the legend dots (Throttle/Brake/Speed/Steering) or replace the Compare button area once comparison is active.

---

## Findings from the Independent Coaching Review (2026-08-07)

A sim-racing coach reviewed a real COTA session
(`ferrari296gt3_cota gp 2026-08-07 12-42-20`, best 2:11.585, 16 valid laps) against the raw
telemetry and assessed whether the tool's top-three priorities were where the driver should
actually be spending practice time.

Methodology note worth preserving: the review was run **clean-room**. It was given the
files, the session context and the raw numbers, but no hypotheses. A separate list of
pre-existing suspicions was withheld until afterwards, then compared. The two agreed on
every major point, which is far stronger evidence than a review told what to look for.
`cota_coaching_review_prompt.md` and `..._followup.md` in the parent repo preserve both
prompts.

### Verdict on the tool's own three priorities

| Rank | Turn | Loss | Verdict |
|---|---|---|---|
| 1 | T12 | 0.713 s | **Real.** Genuinely the most inconsistent corner. But "brake lighter" is the wrong advice — 59 ABS hits means the driver is already at the limit. The problem is repeatability, not pressure. |
| 2 | T13 | 0.481 s | **Artefact.** The variance window is 19.76 s, 15% of the lap, spanning T13 through T18. The "1.37 s throttle delay after apex" is measuring the approach to the *next* corner. |
| 3 | T3 | 0.478 s | **Real loss, inverted advice.** "Commit to the higher speed you already proved" points at a 91 mph outlier; the actual best lap used 75 mph through there. The outlier probably wrecked the rest of the esses. |

### Wrong numbers

- **T12 and T13 report identical throttle metrics** — `thr_on` 1.57 and `thr_lag` 1.37 on
  both, to the digit. Two different corners cannot produce byte-identical values. The
  rank-2 recommendation rests entirely on that number. Suspected zone-boundary bleed in
  `_extract_exit_metrics`; needs confirming against the raw `.ibt`.
- **`min_speed_mph` and `apex_avg_mph` disagree by 21–47 mph on every zone.** T12 reports a
  zone minimum of 85.1 mph and an apex average of 37.8. The Detailed table shows one, the
  coaching sentence quotes the other, and a coach cannot reconcile them. They measure
  different windows; at minimum the naming has to say so.
- **A 3:36.025 lap sits inside the 16 "valid laps"** — 164% of the best. Whether it reaches
  the corner-variance averages is unconfirmed. If it does, every loss figure and the whole
  ranking is contaminated.

### Right numbers, wrong emphasis

- **Loss windows are not corners and are not comparable.** They range from 5.7% of the lap
  (T12) to 15.0% (T13). Ranking corners by loss is not meaningful when the windows differ
  threefold in length. Either narrow them per turn or label them honestly as sections — see
  Track Sections above.
- **Ranking ignores repeatability.** T20 shows 0.390 s loss with 0.490 s std dev — one bad
  lap inflating an average. T1 shows 0.352 s with 0.188 s std dev — consistent, repeatable,
  and a far more reliable improvement target. The report ranks the first higher.
- **"Total recoverable" is presented as achievable.** 2.641 s assumes assembling the best
  T1, T3, T11, T12, T13 and T20 onto one lap, but some of those bests come from aggressive
  laps that were fast in one corner and slow in the next. A realistic figure is 40–50% of
  the stated total. Suggested reframe: show the assembled-best lap and the consistency gap
  explicitly.
- **The ABS trade-off is listed but never interpreted.** The best lap used 515 ABS samples
  (8.6 s of ABS); the cleanest lap used 222 and was **2.5 s slower**. That single comparison
  is the clearest statement of the driver's actual problem — speed currently requires
  overdriving — and the report leaves the reader to spot it.
- **No blind-zone warning.** The report ranks six corners without ever saying that fourteen
  were not analysed. A reader reasonably assumes the top-three list is exhaustive.

### Cross-session regression detection (new feature request)

`thr_on` at T11 was 0.85 s in the PB session and 1.73 s in this one — the driver lost
almost a second of throttle commitment at the corner leading onto the longest straight on
the circuit, over four days, and nothing surfaced it. Progression tracking currently
compares lap times and ABS counts only.

Worth flagging per-corner metrics that have moved materially since the best session:
*"T11 throttle application has slowed by 0.88 s since your best session. You used to commit
earlier here — what changed?"*

### Plateau diagnosis (new feature request)

Four sessions inside a 0.6 s band: 2:11.446, 2:11.007, 2:11.212, 2:11.585. The coach's read
was a **consistency ceiling**, not a pace ceiling — best corners assembled come to roughly
2:10.2 against an actual best of 2:11.6. The evidence was already in the data; the report
did not draw the conclusion.

This overlaps the Theoretical Best item in Batch 1 below, and gives it a sharper purpose:
the number matters less than the sentence it enables — *you already have the speed, you are
not delivering it on one lap.*

---

## Enhanced Coaching Features (Post-MVP Feature Pass)

Identified from a coaching review of the COTA practice session (2026-08-03) using professional racing methodology as a reference framework. All features use generic coaching language. Internal development references ARA methodology for prioritization and message quality, but the user-facing output remains neutral and data-driven.

### Batch 1 — High Value, Low Effort (data already exists)

#### Turn-in Brake Ratio

**Priority:** Highest in Batch 1. Directly diagnoses the #1 technique issue identified by
the independent coaching review (progressive brake release into trail braking) and is
computationally simple — a lookup of two values at 60 Hz.
**Full spec:** `SimCoach/turnin_brake_ratio_feature.md`

The existing report showed T12 had 59 ABS hits and said "brake lighter." The coaching
reviewer said the fix is "release earlier" — the driver's peak pressure is fine, but they
carry it too deep into the corner. This metric makes that visible and actionable.

**The metric:**

```
turn_in_ratio = brake_at_turn_in / peak_brake_in_zone
```

Where `brake_at_turn_in` is the brake pressure at the first sample where the driver begins
adding steering. Computed per lap, not just best lap, so the comparison "your best lap was
28%, your average is 71%" works.

**What it connects:** `high ratio → fronts saturated → ABS → understeer → low apex speed →
over-braking`. This is the causal chain the existing metrics each measure a piece of but
never assemble. The turn-in ratio is the single number at the top of the chain.

**What exists today:** `turnin_brake_pct` is already computed for the best lap in every
braking zone. This extends it to per-lap, expresses it as a ratio against peak, compares
against best-lap baseline, and surfaces it with coaching.

**Two open questions before implementation:**

1. **Turn-in detection method.** The spec proposes "10% of peak steering angle in the
   zone" — which auto-adapts to corner speed. The alternative is steering *rate of change*
   exceeding a threshold (detects the event rather than a position). The rate approach is
   probably more robust but noisier. Needs a prototype on 2–3 corners of different speeds
   before committing. A wrong turn-in detection makes the ratio meaningless.

2. **Absolute thresholds need validation.** The spec states `< 0.35 = Good` based on one
   session. The RR-021/RR-022 saga demonstrated the cost of shipping calibrated thresholds
   from a single session. **Ship with the comparison logic only** — "your best was X, your
   average is Y" — and leave the fixed green/amber/red bands out of user-facing output
   until validated across more sessions and car classes. The comparison message is actionable
   without knowing whether 35% or 45% is the universal "good" line.

**Where it shows up:** session notes (new table), Detailed braking zones (new column),
Summary Focus Cards when ratio > 0.65, and the brake-release curve visualisation gains a
vertical "turn-in" marker.

#### Throttle Hesitation on Summary

Surface `thr_lag` on the Summary page when it exceeds 1.0s at any corner. Currently buried in the Detailed braking table. A 1.5s throttle lag before a long straight is arguably the single biggest recoverable item per corner.

- Display: coaching sentence on a Focus Card — "T1: 1.57s throttle hesitation — commit to throttle at the apex and let the car carry you to the outside."
- Priority weighting: `thr_lag × straight_length_after_corner` estimates the time cost.
- Data: `thr_lag` and `thr_on` are already computed per zone.

#### Theoretical Best (Assembled Lap)

Sum of best per-corner sector times across all laps. Shows the speed the driver has *already demonstrated* but not on one lap.

- Display on Summary: "Theoretical Best: 2:10.1 | Actual Best: 2:13.5 | Consistency Gap: 3.4s"
- Coaching message: "You already have the speed — focus on repeating what you proved, not finding new pace."
- Data: corner_variance already has per-corner best times. Just sum them.
- This reframes "you're slow" as "you're inconsistent" — which is actionable.

#### ABS Hotspot on Summary

Surface ABS activations when a zone exceeds a threshold (e.g., >30 hits).

- Display: "T15: 62 ABS hits — you're past the brake limit. Find the pressure just below lock-up and maintain it."
- If ABS trend is improving across the session, acknowledge it: "ABS improving — you're calibrating."
- Data: `abs_hits` per zone, `abs_trend` already computed.

#### Session Progression Indicator

Show whether the driver was still improving at session end or plateaued.

- Compare mean lap time of first half vs second half.
- If best lap came in last 25%: "Still finding time — consider extending next session."
- If best lap came early and times worsened: "Peak was early — possible fatigue."
- If times are flat for 5+ laps: "Plateau — you need new input, not more laps."
- Data: lap times are already available.

### Batch 2 — Medium Effort, High Value (needs new computation)

#### Sector-Level Time Breakdown

Divide the track into 3 sectors and show which part costs the most time.

- Display: `S1: +1.2s | S2: +0.8s | S3: +0.7s` (gap vs theoretical per sector)
- Immediately tells the driver where to focus without reading every corner.
- Computation: accumulate sample time per sector per lap using `LapDistPct` boundaries.

#### Exit Priority Weighting

Weight corner importance by the straight length that follows.

- Computation: distance from zone exit to next zone entry (partially done in HTML with `exitWeight`).
- Display in notes: add a "Straight After" column to the corner variance table.
- A 0.3s loss before an 1100m straight costs more than 0.3s before a 200m straight.

#### Untracked Section Warning

Flag large gaps in the track where no braking zone was detected but time is likely being lost.

- If >20% of track has no braking zone, display: "Turns 2-10 (34% of track) — no heavy braking detected. Test your grip: try turning more mid-corner."
- Calculation: sum of zone influence ranges vs track length.
- Connects to the known limitation that only >50% brake corners are detected.

#### Driver Level Detection

Estimate how far off pace the driver is to tailor message complexity.

- `gap_per_km = gap_to_reference / track_length_km`
- >1.0s/km: focus on consistency, simple messages ("throttle at the apex")
- 0.5–1.0s/km: balance and speed, intermediate messages
- <0.5s/km: precision, advanced messages
- Requires a reference pace per car/track (could be the driver's own PB from progression, or a static reference)

### Batch 3 — Notes Enhancements (trivial effort, data exists)

#### Throttle Application Table in Session Notes

Add per-zone `thr_on` and `thr_lag` to the markdown output. Data exists, just needs a table row.

#### Min Speed Variance Table in Session Notes

Add best/worst/avg/spread/over-braking per zone. Data exists in `apex_consistency`, just needs formatting.

#### Focus for Next Session (Plain-English Actions)

Replace the current generic "Targets for Next Session" with coaching-style actions that reference what the driver should *do*, not just what number to hit.

Current: "Best lap under 2:13.0"
Better: "T1 Exit — commit to throttle at the apex (thr_lag: 1.57s). T12 Entry — same reference, lighter peak pressure (over-slowing 4.4mph vs your best)."

### Internal Reference (not user-facing)

The Almeida Racing Academy methodology is documented in `SimCoach/CONTEXT.md` and used internally as a quality reference for coaching message generation. Key principles used for prioritization:

- "Entry is cause, exit is consequence" — trace exit problems back to entry
- "Consistency before speed" — Level 1 priority
- "Speed and rotation are inversely proportional" — inform over-braking messages
- "Fast application, maintained pressure" — inform T2Peak/brake shape coaching
- "1% brake feeling" — inform trail braking prompts
- "If you can cause it, you can prevent it" — inform drill suggestions (future)

This methodology is NOT exposed to users as "ARA" or any branded framework. It influences how we write messages and prioritize what to surface — the output stays generic and data-driven.

---

## Race Readiness Assessment (Standalone Feature)

**Priority:** After enhanced coaching features (Batches 1-3 above)
**Effort:** ~1-2 days for MVP
**Full spec:** `SimCoach/race_readiness_feature.md`

### What it does

User drops an iRacing race result JSON (exported from the iRacing website) and Tenths produces a field analysis showing where their pace would land them, what lap time is needed for specific positions, and how incidents affect outcomes in their split.

### Why it matters

Answers the question every driver asks before clicking "Race": *Am I ready? Where will I finish? What should I focus on?* No existing tool provides this from a single exported result file.

### MVP scope

- Input: single `eventresult-*.json` file (iRacing website export)
- Output: standalone Race Readiness report
- No practice session required (pure field assessment)
- If a matching practice session exists (same track/car class), overlay the user's pace as "You Are Here"

### Key outputs

1. **Field stats** — SOF, entries, race length, event best/avg lap
2. **Position target table** — Top 3 / Top 5 / Top 10 requirements: avg lap needed, best lap typical, max incidents tolerated, consistency spread (avg-best gap)
3. **Field tier detection** — auto-cluster the field into performance tiers based on natural gaps in average lap time, with a coaching description of each tier's profile
4. **Coaching insight** — one plain-English message about what decides results in this split (e.g., "Incidents decide more than speed" or "The top 4 are in their own race — focus on winning the Tier 2 battle")
5. **User assessment** (when practice session linked) — estimated qualifying and race finish position, gap to target positions, primary risk factor, pre-race brief

### Technical notes

- `tenths/results.py` already parses both CSV and JSON race results — the data extraction exists
- New computation module needed for tier detection, position targets, and coaching insight generation
- Practice session matching requires resolving track name across JSON metadata and `.ibt` filename slugs — same class of problem as `find_race_result()` but in reverse
- The result JSON is typically downloaded *after* the race (post-hoc analysis for next week), not in real-time before racing. Frame accordingly.
- Edge cases documented in full spec: partial results, small fields, multi-class, no qualifying, user's own result as calibration

### Post-MVP extensions

- Multi-race ingestion (3+ JSONs) for statistical confidence
- iRating-based split prediction
- Qualifying strategy recommendations
- Incident budget calculator
- Historical position trends across race weeks

### Reference

Designed from real data: Ferrari 296 GT3 @ COTA GP practice (2:13.502 best) vs GT3 Regional Tour Split 3 (SOF 1071, 15 drivers). Finding: user's pace projects to P7-P9, with top-10 achievable purely through clean driving (the split was incident-dominated).

---

## Unit System Toggle (Imperial / Metric)

**Priority:** High — before wider international beta
**Effort:** 1–2 days. The original "half day" estimate was wrong. Measured surface: **293 `mph` references across 8 modules plus 249 across 10 test files** — `report.py` 133, `analyzer.py` 74, `summary.py` 32, `track_map_generator.py` 15, `process.py` 14, `incidents.py` 13. `index_generator.py` displays no speeds and is not involved.
**Status:** implemented. `tenths/units.py`, `config.UNITS` / `config.is_metric()`, `tenths config --units`, the analyzer emitting SI, and label plumbing at all four display boundaries (report, notes, generated track maps, `tenths incident`) are all in place. The follow-ups listed at the end of this section remain open.

Currently all user-facing speeds are MPH and temperatures are °F (hardcoded US units per the original steering file). International drivers expect KPH/°C. iRacing itself supports both unit systems, and the sim racing community outside the US overwhelmingly uses metric.

### What needs to toggle

| Unit type | Imperial (current) | Metric |
|---|---|---|
| Speed | MPH | KPH |
| Temperature | °F | °C |
| Distance (short) | ft | m |
| Track length | mi | km |

Lap times, percentages, and brake pressures stay the same regardless of unit system.

### Where units appear

- **HTML report** — Summary hero numbers, Focus Card speed context, Detailed braking zones table (entry/min speed), corner variance, telemetry chart Y-axes, brake release annotations
- **Session notes (markdown)** — braking zones table, tire temps, lap table max speed
- **Generated track maps (markdown)** — `track_map_generator.py` bakes braking-zone entry and minimum speeds into the `.md` files it writes
- **CLI output** — `tenths analyze` and `tenths incident` both print speeds; `tenths config` reports the active setting
- **Session summary (JSON)** — stays mph deliberately, see the design decision below
- **Index page** — displays no speed data, not involved

### Implementation approach

1. Add `units` to `settings.json` (values: `"imperial"` or `"metric"`, default `"imperial"` for backward compatibility)
2. Add `tenths config --units metric` / `tenths config --units imperial` CLI command
3. Create a small `tenths/units.py` module with conversion helpers:
   ```python
   def speed_label(settings): return "km/h" if metric else "mph"
   def to_display_speed(mps, settings): return mps * 3.6 if metric else mps * 2.237
   def to_display_temp(celsius, settings): return celsius if metric else celsius * 9/5 + 32
   ```
4. All display code calls through these helpers rather than hardcoding `* 2.237`
5. The HTML report reads the unit preference at generation time and renders accordingly — reports are static after generation, so a unit change requires regenerating

### Design decision: per-report or global?

**Global (recommended for MVP).** The setting lives in `settings.json` and applies to all future reports. Old reports stay in whatever unit they were generated with. A per-report toggle in the HTML would require client-side conversion logic in JavaScript — doable but adds complexity.

### Design decision: the tray owns the user-facing switch

The CLI (`tenths config --units metric`) is not a usable path for the audience this feature exists for. The installer places Tenths in `%LOCALAPPDATA%\Tenths` without adding it to `PATH`, so an installed tester has no `tenths` command — they would have to type the full exe path and then restart the app.

The switch is therefore a checkable **"Metric Units (km/h)"** item in the tray, matching the existing `Pause Processing` and `Start with Windows` pattern. It persists via `save_settings()` and then assigns `config.UNITS` in the running process, so the next processed session uses it with no restart. That works because every display boundary calls `config.is_metric()` at format time, and it is the reason they must continue to.

This makes the tray the only sanctioned runtime writer of `config.UNITS`; the invariant is recorded in the `tenths/units.py` contract. Persisting happens *before* the in-process assignment, so a settings file that cannot be written leaves both halves unchanged and the menu tick can never disagree with disk.

Still deliberately not solved: switching units does not retroactively change reports already on disk. They are static HTML. A client-side toggle inside the report would fix that but needs the payload to carry SI and the JavaScript to convert, which is a materially larger change than this one.

### Design decision: store SI internally

**Store SI (m/s, °C) throughout the pipeline. Convert only at display time.** This makes stored data unit-agnostic and removes the conversion-on-read problem: if a user switches units after accumulating sessions, progression comparisons against earlier best-lap speeds still work because nothing stored ever changed unit.

The `* 2.237` conversions currently scattered through `analyzer.py` move to display-layer code only.

### Design decision: ships as one commit

The analyzer emitting m/s while the display layer still prints "mph" is not a partial feature, it is a shipped bug — a 117 mph corner would render as "52 mph". `main` is public with a live beta and `release.py` builds straight from `main`, so there is no safe intermediate commit. The whole refactor lands together or not at all.

### Design decision: the JSON summary stays in mph for now

`session_summary.json` keeps its `*_mph` keys and mph values regardless of the user's display setting, and `CURRENT_SCHEMA_VERSION` stays `1.0.0`.

The summary is a machine-readable contract read by `index_generator.py` and the progression logic, so its shape must not depend on a display preference — a metric user must not get km/h under `*_mph` keys. Since the file content does not change, there is nothing to version. An earlier draft of this plan called for a `1.1.0` bump with a `units` field; that was wrong on both points.

Renaming the summary keys to SI (`entry_speed_mph` → `entry_speed_mps`) is the correct end state but it is a separate change: it is invisible to users, and it needs a real migration for existing archived files. Tracked as a follow-up below.

### Precision risk (measured, not hypothetical)

Speeds are currently stored via `round(value, 1)`. That is 0.1 mph granularity today but 0.1 m/s after the refactor — 2.24× coarser. Measured effect of rounding a calibrated threshold to 1 decimal in m/s and converting back:

| Calibrated mph | m/s exact | rounded to 0.1 | back to mph | error |
|---|---|---|---|---|
| 1.5 (over-braking floor) | 0.6706 | 0.7 | 1.566 | +4.4% |
| 2.0 (apex-std floor) | 0.8941 | 0.9 | 2.013 | +0.7% |
| 6.0 (spread floor) | 2.6822 | 2.7 | 6.040 | +0.7% |

RR-021 and RR-022 were calibrated so those rules fire on a known set of corners. A 2–5% threshold shift can silently flip borderline corners and change coaching output. **Mitigation: do not round speeds in the analyzer at all** — store the full float, round only in the display format string. At 4 decimals the worst error across the same cases is +0.006%.

The three fractional limits (`SPREAD_LIMIT_FRACTION` etc.) are percentages of the corner's own apex speed and so are unit-agnostic — leave them alone. Only the absolute floors convert, and they should be written as `mph_to_mps(6.0)` rather than a transcribed decimal so the calibration provenance stays visible.

### Regression guard

The specific historical validation counts ("9 of 41 corners", "1 of 9 at Coronado") **cannot be reproduced** — the 8 archived `.ibt` files those numbers came from no longer exist on the dev machine. Do not chase them; the risk is retuning a threshold to hit a remembered number.

Use invariance instead: baseline every corner's three metrics, three computed limits, and three flag decisions across all currently available sessions before the change, then assert after the change that **every flag decision is identical** and every mph-equivalent value matches within 0.05 mph.

**Result (2026-08-05).** 27 `.ibt` files were available; 13 analysable, giving 78 corners. Flag decisions, coaching notes, exit-metric availability and corner counts were all identical, with **zero** metric drift. Imperial output turned out to be **byte-identical** — `session_report.html`, `session_notes.md`, `session_summary.json` and the generated track map all matched by SHA256.

Two extra invariants were added to the harness after scoping found gaps in the original plan:

- **Coaching notes.** Seven absolute mph gates sat inline in the analyzer behind the note logic — `min_spd > 20` ("Over-slowing"), `min_spd > 40` ("Lugging", ×4), and `apex_speed < 30` (which gates whether `thr_on`/`thr_lag` are computed at all). None were covered by the three flag decisions. Left unconverted they would have silently disabled "Lugging" (40 m/s = 89 mph) and blanked exit metrics on most corners. They are now named SI constants and asserted in `tests/test_units.py`.
- **Exit-metric availability.** `thr_on`/`thr_lag` presence is recorded per corner, which is what pins the `apex_speed < 30` gate.

Byte-identity was only reachable by **keeping the factor at 2.237** rather than adopting the exact 2.23694 — see the follow-up below.

**Independent re-verification (2026-08-07), and one correction.** The comparison was re-run from a `git worktree` at the pre-refactor commit across the 13 analysable sessions. Imperial output is *effectively* but not literally byte-identical: 10 of 13 sessions match by SHA256, and the 3 that differ do so in a single field, `tire_temps.<corner>.avg`, by ±2.8e-14 °F. `to_display_units()` converts each corner then averages, where the analyzer previously averaged then converted; the code comment claiming that ordering is bit-identical is wrong. The magnitude cannot change a rendered digit, so no output moved, but the claim should not be repeated as exact.

The same comparison independently confirms the flag-decision invariance: the report's `DATA` payload carries all three metrics and all three computed per-corner limits, and none of them differed on any session.

**Label plumbing verified separately (2026-08-07).** Because the label fix rewrites the JS template, raw HTML hashes necessarily move. Verification therefore compared *semantic* content: the `DATA` payload canonicalised with the new `units` key removed, and the template with the unit indirection substituted back to its imperial literal. Both match the pre-refactor tree on all 13 sessions, and notes and generated track maps match by SHA256, which proves the template edits are label plumbing and nothing else. Metric mode was then rendered end to end (`221 km/h` where imperial shows `137 mph`, tire-temp heading following the toggle) and every script block in the generated report was syntax-checked with `node --check` in both modes.

### Follow-ups deliberately excluded from the refactor

- **Correct the mph conversion factor.** `units.MPS_TO_MPH` is pinned to `2.237`, the value the analyzer used inline, because adopting the exact `2.2369362920544` shifts every displayed speed by ~2.7e-5 relative. Measured on the Winton fixture that moved 1247 values in the DATA blob by ~0.003 mph and pushed one corner's `spread_limit` across a 1dp rounding boundary (9.2 → 9.1 mph) — no flag decision changed, but the report was no longer byte-identical. Pinning it kept this refactor provably behaviour-preserving. Correcting the constant is a one-line change that should ship on its own so any output movement is attributable to it. Guarded by `TestConversionFactorIsPinned` in `tests/test_units.py`.
- **Rename summary keys to SI** (`*_mph` → `*_mps`) with a schema bump and a migration for existing archived files.
- **Apex-std colouring is still an absolute threshold.** `report.py` colours the apex-std cell against fixed bands (5 and 2 mph) rather than the per-corner computed `apex_std_limit_mph`. This is the same absolute-threshold defect RR-021 fixed for the spread rule and RR-022 fixed for over-braking; it survived in the colouring path. The *unit* half is now handled — the bands come from `_units_payload()` as `U.apex_std_bad` / `U.apex_std_warn`, so they scale with the display unit instead of meaning 3.1 mph in metric. Making them speed-relative is the part still outstanding, and it needs its own validation because it changes which cells light up.
- **Stale unit labels in generated track maps.** `track_map_generator.py` bakes speeds and their label into the `.md` files it writes to `%LOCALAPPDATA%\Tenths\tracks`. A map generated in imperial keeps imperial labels after a switch to metric. Because the label is written alongside the value the file is never wrong, only inconsistent with the current setting. Regenerating on unit change is not worth building yet.
