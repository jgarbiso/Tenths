# Circuito de Navarra — Speed Circuit

## Track Info
- **Location:** Navarra, Spain
- **Length:** 2.44 mi / 3.92 km
- **Turns:** 15
- **Pit Speed:** 37 mph / 60 kph
- **Night Lighting:** No
- **iRacing Track No:** 515
- **Direction:** Clockwise

---

## Turn Map — Telemetry % to Turn Number

Layout flows clockwise. S/F straight runs left-to-right at the bottom of the map.

| Track % | Turn | Name | Direction | Description |
|---|---|---|---|---|
| ~5-9% | **T1** | — | Right | First corner after S/F straight |
| ~11-16% | **T2** | — | Left | Tight left hairpin. Heavy braking zone. |
| ~17-21% | **T3** | — | Right | Tight right exiting hairpin complex |
| ~24-28% | **T4** | — | Left | Left-hander heading uphill |
| ~30-35% | **T5** | — | Right | Right-hander, lower-middle of circuit |
| ~38-42% | **T6** | — | Left | Left-hander |
| ~44-48% | **T7** | — | Left | Left-hander, middle-left area |
| ~50-54% | **T8** | — | Left | Left at top-left entering infield complex |
| ~56-60% | **T9** | — | Right | Right at top of infield. Heaviest braking zone (111→35mph). |
| ~62-66% | **T10** | — | Right | Right, infield complex |
| ~67-71% | **T11** | — | Right | Right, continuing infield |
| ~73-77% | **T12** | — | Right | Exiting infield complex |
| ~79-83% | **T13** | — | Right | Right at top-right |
| ~85-89% | **T14** | — | Right | Far right, leading back to S/F |
| ~91-95% | **T15** | — | Right | Last corner before S/F straight |

---

## Telemetry Braking Zones → Turn Mapping

Based on telemetry data from BMW M2 CS Racing:

| Telemetry % | Entry | Min | Turn |
|---|---|---|---|
| ~14% | 111 mph | — | **T2** (tight left hairpin) |
| ~29% | — | — | **T4** (left-hander uphill) |
| ~35% | — | — | **T5** (right-hander) |
| ~44% | — | — | **T7** (left-hander) |
| ~57% | 111 mph | 35 mph | **T9** (infield hairpin — heaviest stop) |
| ~66% | — | — | **T10** (infield complex) |
| ~76% | — | — | **T12** (right complex) |
| ~87% | — | — | **T14** (right before final straight) |

---

## Known Problem Corners (BMW M2 CS)

| Turn | Issue | Data |
|---|---|---|
| **T9 (57%)** | Heaviest ABS zone — over-braking into infield hairpin | 93 ABS hits, 87% max brake, entry 111mph to 35mph |
| **T4 (29%)** | HIGH PRIORITY time loss — inconsistent entry | 0.62s loss, 0.52 StdDev |
| **T5 (35%)** | Lugging risk — wrong gear at apex | Apex RPM 3424 (May 24) |
| **T12 (76%)** | Panic braking straight — not combining lateral grip | 61% brake, 0.48G lateral |
| **T2 (14%)** | High ABS on heavy stop | 44-139 ABS depending on session |

---

## Performance History (BMW M2 CS)

| Date | Best Lap | Cleanest ABS | Key Finding |
|---|---|---|---|
| May 22 | 1:56.272 | 97 | First visit, CPU bottleneck (44fps) |
| May 23 AM | 1:55.926 | 187 | |
| May 23 PM | 1:53.495 | 149 | Race PB |
| May 24 | 1:56.323 | 124 | AI race, lugging at T5 |
| May 25 AM | 1:53.650 | 92 | Cleanest race lap |
| May 25 PM | 1:55.162 | 156 | Fatigue regression |

**Current PB:** 1:53.495 (May 23)
**Cleanest race lap:** 92 ABS (May 25)

---

## Coaching Notes

- T9 is the key corner. Build brake pressure progressively on the 111mph stop — don't stab to 87%.
- T4 has the highest variance — pick a fixed braking marker and commit to it every lap.
- When ABS starts climbing mid-race, back off 2-3mph entry for one lap to reset rhythm.
- Fatigue causes regression to old habits after ~6 races in a day.
