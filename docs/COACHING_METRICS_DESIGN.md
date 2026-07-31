# Coaching Metrics Design — Tenths

## Philosophy

Tenths turns professional coaching principles into automated, measurable telemetry comparisons. The system answers specific coaching questions with data, not generic charts. Every metric must connect to an actionable coaching sentence.

**Design principle:** Replace before add. The screen gets simpler before it gets richer. A driver should immediately see what changed and what to do next.

---

## 1. Coaching Concepts → Tenths Metrics Mapping

| Coaching Concept | Tenths Metric | What It Measures | Data Required | UI Presentation | Status |
|---|---|---|---|---|---|
| Hard initial brake, then controlled release | **T2Peak** + **Brake Linearity** | Time to reach peak pressure + smoothness of release curve | Brake%, LapDistPct, 60Hz | Brake Release Shape panel (SVG curves) | ✅ Built |
| Consistent braking reference points | **Brake Point Spread** (±m) | Lap-to-lap consistency of where braking begins | Per-lap Brake entry LapDistPct + GPS | Brake Points overlay dots + ±Xm label | ✅ Built |
| Corner-by-corner analysis | **Corner Variance** | Time loss per corner vs theoretical best | Per-lap sector times | Corner Variance table + priority flags | ✅ Built |
| Minimum-speed rotation / apex discipline | **Apex Speed Consistency** | Std dev of min speed at each corner across laps | Per-lap min speed per zone | Number in braking zones table | ✅ Built |
| Carrying too little speed (over-slowing) | **Min Speed Spread** | Outlier-trimmed min-speed band per corner + average vs best-lap deficit | Per-lap min speed per zone | Coaching sentence + avg under Min column | ✅ Built |
| Decisive throttle on exit | **Thr On** + **Thr Lag** | Time from apex to WOT + time spent feathering | Throttle%, Speed, 60Hz | Columns in Braking Zones table | ✅ Built |
| Smooth inputs (no oscillation) | **Input Stability** | Frequency of direction changes in brake/throttle during steady phases | Brake%, Throttle%, diff() | NEW — flag in Notes: "[Oscillating]" | ❌ New |
| Looking ahead / connecting corners | **Inter-Corner Speed** | Speed maintenance between turn exit and next braking point | Speed trace between zones | NEW — shown in speed trace as highlighted sections | ❌ New |
| Early, light, long braking in fast corners | **Brake Duration** + **Peak Brake %** | How long the braking zone is + max pressure applied | Brake%, LapDistPct | NEW — could replace/augment Brk2Shft column | ❌ New |
| Prioritize slow corners with exits | **Exit Priority Score** | Corners ranked by: (time on following straight × speed delta potential) | Track layout + speed trace | Corner Variance table reordered by exit value | ❌ New |

---

## 2. Detailed Metric Definitions

### Apex Speed Consistency (✅ Built)
- **Definition:** Standard deviation of minimum speed (mph) at each corner across clean laps
- **Calculation:** For each corner, collect `min_speed` from every clean lap → `std(min_speeds)` over the outlier-trimmed set
- **Good:** < 2 mph std dev (hitting the same apex speed every lap)
- **Bad:** > 5 mph std dev (inconsistent commitment or line)
- **Visualization:** Small number in the braking zones table: "±1.2 mph"
- **Coaching sentence:** "T5: Your apex speed varies by ±6 mph — find a consistent visual reference for turn-in commitment."
- **Apex location (corrected 2026-07-28):** The search window is centred on the corner's **apex**, located on the best lap, not on the braking zone. Measured on a real 5.4km lap the apex sits 55–273m (mean 119m) *after* the braking-zone centre. See "Corner attribution" below — this metric was materially wrong before that fix.

### Input Stability (NEW)
- **Definition:** Count of sign-changes in `diff(Brake)` or `diff(Throttle)` during a steady phase (mid-corner for brake, exit for throttle)
- **Calculation:** In the mid-corner phase (from turn-in to apex), count how many times brake pressure reverses direction (squeeze-release-squeeze = oscillation). In exit phase, count throttle pumps.
- **Threshold:** > 3 reversals in a single corner phase = "[Oscillating]" flag
- **Visualization:** Flag in Notes column. Could also highlight the affected section on the telemetry chart in a different color.
- **Coaching sentence:** "T8: You pumped the brake 4 times between turn-in and apex. Hold steady pressure and release progressively."

### Inter-Corner Speed (NEW)
- **Definition:** Average speed between one corner's exit (throttle > 90%) and the next corner's brake entry (brake > 15%)
- **Calculation:** For each pair of adjacent braking zones, compute mean speed in the gap between them
- **Good:** Speed rises monotonically (smooth acceleration, no hesitation)
- **Bad:** Speed plateaus or dips (lifted unnecessarily, didn't fully commit)
- **Visualization:** Could be shown as colored bands on the speed trace between braking zones
- **Coaching sentence:** "Between T5 exit and T8 entry: you lifted at 72% distance — staying flat would carry 3 mph more into T8."

### Brake Duration (NEW)
- **Definition:** Time (seconds) from brake application (>15%) to brake release (<5%) for each zone
- **Calculation:** `(release_idx - entry_idx) / sample_rate`
- **Context:** Fast corners with early/light/long braking will show longer durations at lower peak pressure. Slow corners show short, hard braking.
- **Visualization:** Replace or augment `Brk2Shft` column with `Brk Dur` for context
- **Coaching sentence:** "T3: Your braking lasts only 0.8s at 95% peak — try braking 0.3s earlier at 75% peak for a smoother entry and better rotation."

### Min Speed Spread (✅ BUILT — 2026-07-28)
- **Definition:** Per-corner comparison of minimum speed on each lap vs the best lap's minimum speed at the same corner
- **Problem it solves:** Driver sees "0.33s variance at T5" but doesn't know WHY. The current report shows entry/min speed for the best lap only — it can't show that on average laps, you're braking 20mph deeper than necessary.
- **Calculation:**
  - For each braking zone, collect `min_speed_mph` from every valid lap
  - Compute: `best_lap_min`, `average_min`, `worst_min`, `std_dev`
  - Over-braking delta: `average_min - best_lap_min` (negative = braking too deep on average)
- **Thresholds:**
  - Spread > 10mph across laps = HIGH priority inconsistency
  - Average min speed > 8mph below best-lap min speed = over-braking diagnosis
- **Visualization:** In Summary View coaching sentence + in Detailed braking zones table as "Min: 106 (avg 85, ±15)"
- **Coaching sentence examples:**
  - "T5: Min speed varies 77-106mph — you carried 106 on your best lap. Trust the car and brake lighter."
  - "T5: Over-braking by ~20mph on average — your best lap proves you can carry more speed. Pick a fixed brake marker and commit."
- **Data required:** Per-lap min speed per braking zone (already computed in analyzer, just not exposed per-lap in the report DATA blob)
- **Why this matters:** This is the #1 insight gap found in real racing (Road Atlanta Jul 22). The driver was consistent (low corner variance in time) but 1s off pace because they were over-slowing every corner by a small amount. The current system can't diagnose "you're braking too much" — only "you're inconsistent."
- **As-built behavior (deviations from the original sketch above):**
  - Implemented inside `analyzer._extract_apex_consistency()`, which already collected per-lap min speeds — no second pass over the telemetry.
  - **Sign convention:** `over_braking_mph` is stored as a POSITIVE magnitude (`best_lap_min - average_min`). Positive means the average lap gives up that many mph versus the best lap. Negative means the best lap was the slowest through the corner, so over-slowing is not indicated. The original note described the inverse sign.
  - **Incident laps excluded.** Aggregates use the same clean-lap rule as corner variance (laps within 110% of best lap time) via `_clean_lap_numbers()`, so the metric agrees with the time-loss figures shown beside it. `per_lap_apex` still lists every valid lap.
  - **Outlier-trimmed band.** A raw max-minus-min range proved unusable on real data: one off-track moment reported ~30mph spread for repeatable corners, firing 6 of 7 zones at Mid-Ohio. The band now removes Tukey-fence (1.5 × IQR) outliers once at least 5 clean laps exist, which reduced that session to 2 genuine zones. Below 5 laps it falls back to the true range.
  - **Fields:** `min_speed_best_mph`, `min_speed_worst_mph` (true slowest clean lap, kept for context), `min_speed_typical_low_mph` / `min_speed_typical_high_mph` (the band), `min_speed_spread_mph` (band width), `over_braking_mph`.
  - The Summary View sentence renders the band bounds, so the displayed range can never disagree with the reported spread.
  - Exposed in the report DATA blob and in `session_summary.json` as additive fields (schema stays `1.0.0`; missing in older files reads as `null`).
  - Focus cards and Next Race Focus now share one `buildCorner()` helper, so diagnoses cannot drift between them.
- **Thresholds in production:** `over_braking_mph > 8` and `min_speed_spread_mph > 10`.
- **Open tuning question:** thresholds are unvalidated across tracks and car classes. The absolute mph spread threshold is a known weakness on fast corners — see "Corner attribution and time-loss accuracy" above. Review alongside the unresolved Focus Card threshold decision (RR-016 in `RELEASE_REMEDIATION_PLAN.md`).
- **Correction applied 2026-07-28:** the first implementation centred the apex search on the braking zone and trimmed the band but not the mean. Both produced a false over-slowing diagnosis on real data. Fixed the same night; see section 2a.
- **Original implementation notes:**
  - Summary View coaching sentence threshold: `min_speed_spread > 10mph`
  - Priority: should rank ABOVE brake linearity in the coaching priority order when triggered, because over-braking is a more fundamental issue than release shape

### Exit Priority Score (NEW)
- **Definition:** Rank corners by coaching value: `straight_length_after × (max_speed_on_straight - current_exit_speed)`
- **Calculation:** For each zone, measure the distance to the next braking zone (straight length) and the speed differential between your exit and theoretical max speed on that straight
- **Purpose:** Answers "which corner should I focus on?" — slow corners before long straights matter most
- **Visualization:** Corner Variance table sorted by exit priority instead of raw time loss
- **Coaching sentence:** "T14 feeds the longest straight — gaining 2 mph at exit here is worth 0.3s on the lap."

---

## 2a. Corner attribution and time-loss accuracy

Audited 2026-07-28 against the Ferrari 296 GT3 race at Qualcomm Circuit (5409m, 9 valid laps) after a reported figure did not survive scrutiny. Read this before changing any speed-based metric.

### Time loss is validated

| Check | Result |
|---|---|
| Tenths best lap vs official iRacing result CSV | 2:08.326 vs 2:08.325 — **1 ms** |
| Sector time by sample-count vs by interpolating `LapCurrentLapTime` | max error **0.011s** |

`corner_variance` loss is `mean(sector_time) - min(sector_time)` across clean laps: recoverable time versus the driver's own best pass through that sector. Time loss was never the defect — **attribution** was.

### Corner windows

- **Zone splitting** (`_zone_ids` / `_zone_gap_pct`): consecutive braking samples become separate zones when the gap between them exceeds `ZONE_GAP_METERS` (120m), converted to a lap percentage and clamped to 1–10%. The original fixed 5% is 270m on a 5409m lap, which **merged T2 and T3 into one 384m "corner"** and reported their combined time as T2. Verified A/B on real sessions: Qualcomm went 6 zones to 7 with T2 and T3 correctly separated, and Winton (2945m) was unchanged at 5 zones. This also removed the duplicate turn labels previously seen (A3).
- **Sector windows** (`_corner_sectors`): `centre-3%` to `centre+8%`, clamped to the midpoint between adjacent corner centres. Before clamping, 4 of 8 sectors overlapped on this circuit, so summed per-corner losses double-counted track.
- **Apex windows** (`_apex_reference_pcts` + `_apex_window`): the apex is located on the best lap by searching from 60m before to 300m after the braking-zone centre (never past the next corner), then all laps are sampled ±100m around that fixed apex position, clamped to neighbour midpoints.
- **Why the apex must be located, not assumed:** a window centred on the braking zone catches the car at entry speed on some laps and at the apex on others. That manufactures variance which is not driver error. It produced a false "8.5 mph over-slowing at T6" where the flagged lap was actually the *fastest* through that corner.
- **Why percentage-only windows fail:** the original `centre-5%/+8%` spans ~703m on a 5.4km lap. Windows must be bounded in metres and converted using track length.

### Outlier handling

Aggregates use clean laps only (within 110% of best lap time, matching corner variance) and then a Tukey 1.5×IQR trim. **Average, std and band must all use the same trimmed set** — the original implementation trimmed the band but not the mean, so a value already rejected as an outlier still inflated the reported deficit.

`min_speed_worst_mph` deliberately reports the true slowest clean lap so trimming never hides data.

### Known remaining weakness

Spread on fast corners is still noisy: T13 reported 14.9 mph spread at an 85.9 mph average, and 5 of 8 corners tripped the 10 mph threshold. A fixed mph threshold does not scale with corner speed and is probably wrong for fast corners. **Open question:** make the spread threshold proportional to corner speed (e.g. a percentage of apex speed) rather than absolute. Not yet validated across tracks or car classes — treat spread-based coaching with caution until this is resolved.

### Rules for future speed-based metrics

0. **Any threshold describing a distance must be expressed in metres** and converted using track length. Three separate defects (apex window, sector overlap, zone splitting) were all the same root cause: a percentage constant tuned on a medium-length circuit behaving completely differently on a 5.4km lap.
1. Bound windows in metres, converted via track length — never raw percentages.
2. Centre on the phenomenon being measured (apex for min speed), not a proxy.
3. Clamp to neighbouring corners so two corners never share samples.
4. Apply identical lap filtering and outlier trimming to every statistic in the same result.
5. Validate against an independent source (official result CSV, or a second timing method) before trusting a number.
6. Sanity-check on a real multi-lap session: if most corners trigger, the threshold or the window is wrong.

---

## 3. Feature Enhancement Recommendations

### MVP (Already Built or Minimal Work)

| # | Feature | Status |
|---|---------|--------|
| 1 | Brake Release Shape panel with linearity scoring | ✅ Built |
| 2 | Brake Point dots + spread metric (±m) | ✅ Built |
| 3 | Lap comparison overlay (solid vs dashed) | ✅ Built |
| 4 | Speed delta panel (green/red shading) | ✅ Built |
| 5 | Thr On + Thr Lag exit commitment metrics | ✅ Built |

### Next Iteration (Build Soon)

| # | Feature | Status |
|---|---------|--------|
| 6 | Apex Speed Consistency (±mph in table) | ✅ Built |
| 7 | Input Stability flag ("[Oscillating]" in Notes) | ✅ Built |
| 8 | Brake Duration column | ✅ Built |
| 9 | Corner ranking by exit value | ✅ Built |
| 10 | Before/After progression view | Backend done (Task 1.5), frontend in Phase 2 |

### Future

| # | Feature | What It Does |
|---|---------|-------------|
| 11 | Inter-corner speed bands | Highlight lift zones between corners on speed trace |
| 12 | Reference-point drift detection | Alert when braking point migrates >10m over a stint |
| 13 | Brake-shape similarity score | Compare your release curve to a "textbook" progressive release |
| 14 | Corner-connection scoring | Measure how smoothly you link successive corners |
| 15 | Coaching sentence generator | ✅ Built — auto-generates plain-English per corner in Summary View |
| 16 | Min Speed Spread diagnosis | ✅ Built — detects over-slowing by comparing per-lap min speed to best-lap min speed |

---

## 4. Overlap & Differentiation

| Existing Tool | What It Does | How Tenths Differentiates |
|---|---|---|
| MoTeC i2 / Atlas | Manual telemetry overlays and chart analysis | Tenths is **automated** — no manual channel setup, no expertise needed |
| VRS (Virtual Racing School) | Reference lap comparison with pro drivers | Tenths compares **you to yourself** — your best vs your average, session over session |
| iRacing built-in delta | Real-time delta bar during driving | Tenths provides **post-session coaching** with specific technique diagnosis |
| Garage 61 | Basic telemetry viewer | Tenths goes beyond viewing to **prescriptive coaching** — tells you what to fix |

**Tenths' unique position:** It's the only tool that automatically translates raw telemetry into coaching-style feedback without requiring the driver to understand telemetry analysis. "Your brake release at T5 is stepped (0.41) — work on progressive release" is coaching. A line chart is just data.

---

## 5. Implementation Priority

**Principle: Replace before add.**

Before adding new panels or sections, evaluate whether a new metric should:
- Replace an existing less-useful column (e.g., `Brk2Shft` → `Brk Dur` if duration is more actionable)
- Add a flag to existing Notes column (e.g., "[Oscillating]")
- Enhance an existing visualization (e.g., color the speed trace between corners)

Only add a NEW section/panel when the information requires its own spatial context (like Brake Release Shape needed curves, not just numbers).

**Next 3 to build (in order):**
1. Apex Speed Consistency (±mph in table) — small, high coaching value
2. Input Stability detection (flag in Notes) — catches a common beginner mistake
3. Corner ranking by exit value — reframes the Corner Variance table with coaching logic

---

## 6. Data Model Implications

**No schema changes needed for:**
- Apex Speed Consistency (derived from existing per-lap braking zone data)
- Input Stability (derived from existing Brake/Throttle channels)
- Brake Duration (derived from existing braking zone detection)

**Schema changes needed for (future):**
- Exit Priority Score (needs distance-to-next-zone calculation, stored per zone)
- Inter-Corner Speed (needs gap analysis between zones, stored per pair)
- Reference-Point Drift (needs per-lap brake points across stints, already in `per_lap_brake_points`)

The current `session_summary.json` schema can absorb these as additive fields without a breaking migration — new metrics get added as `null` in old files, populated in new ones.
