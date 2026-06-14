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
| Minimum-speed rotation / apex discipline | **Apex Speed Consistency** | Std dev of min speed at each corner across laps | Per-lap min speed per zone | NEW — number in braking zones table | ❌ New |
| Decisive throttle on exit | **Thr On** + **Thr Lag** | Time from apex to WOT + time spent feathering | Throttle%, Speed, 60Hz | Columns in Braking Zones table | ✅ Built |
| Smooth inputs (no oscillation) | **Input Stability** | Frequency of direction changes in brake/throttle during steady phases | Brake%, Throttle%, diff() | NEW — flag in Notes: "[Oscillating]" | ❌ New |
| Looking ahead / connecting corners | **Inter-Corner Speed** | Speed maintenance between turn exit and next braking point | Speed trace between zones | NEW — shown in speed trace as highlighted sections | ❌ New |
| Early, light, long braking in fast corners | **Brake Duration** + **Peak Brake %** | How long the braking zone is + max pressure applied | Brake%, LapDistPct | NEW — could replace/augment Brk2Shft column | ❌ New |
| Prioritize slow corners with exits | **Exit Priority Score** | Corners ranked by: (time on following straight × speed delta potential) | Track layout + speed trace | Corner Variance table reordered by exit value | ❌ New |

---

## 2. Detailed Metric Definitions

### Apex Speed Consistency (NEW)
- **Definition:** Standard deviation of minimum speed (mph) at each braking zone across all valid laps
- **Calculation:** For each zone, collect `min_speed` from every lap → `std(min_speeds)`
- **Good:** < 2 mph std dev (hitting the same apex speed every lap)
- **Bad:** > 5 mph std dev (inconsistent commitment or line)
- **Visualization:** Small number in the braking zones table: "±1.2 mph" or color-coded dot
- **Coaching sentence:** "T5: Your apex speed varies by ±6 mph — find a consistent visual reference for turn-in commitment."

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

### Exit Priority Score (NEW)
- **Definition:** Rank corners by coaching value: `straight_length_after × (max_speed_on_straight - current_exit_speed)`
- **Calculation:** For each zone, measure the distance to the next braking zone (straight length) and the speed differential between your exit and theoretical max speed on that straight
- **Purpose:** Answers "which corner should I focus on?" — slow corners before long straights matter most
- **Visualization:** Corner Variance table sorted by exit priority instead of raw time loss
- **Coaching sentence:** "T14 feeds the longest straight — gaining 2 mph at exit here is worth 0.3s on the lap."

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
| 15 | Coaching sentence generator | Auto-generate plain-English coaching text per corner |

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
