# Mid-Ohio Sports Car Course — Full Course

## Track Info
- **Location:** Lexington, Ohio, USA
- **Length:** 2.25 mi / 3.62 km
- **Turns:** 13
- **Pit Speed:** 45 mph / 72 kph
- **Night Lighting:** No
- **AI Enabled:** Yes
- **iRacing Track No:** 153
- **Configs:** 5

---

## Turn Map — Telemetry % to Turn Number

Layout flows counter-clockwise. Start/Finish is at the bottom-center of the map.

| Track % | Turn | Name | Direction | Description |
|---|---|---|---|---|
| ~5% | **T1** | — | Right | First corner after S/F straight |
| ~15% | **T2** | The Keyhole (entry) | Right | Right-hand hairpin, slow |
| ~20% | **T3** | The Keyhole (exit) | Left | Exit of The Keyhole complex |
| ~23% | **T4** | — | Left | Uphill left, heavy braking (124→60mph) |
| ~30% | **T5** | — | Right | Uphill right |
| ~35-40% | **T6** | The Esses (entry) | Left | Entry to esses section |
| ~42% | **T7** | The Esses (mid) | Right | Middle of esses |
| ~47-51% | **T8** | The Esses (exit) | Left | Exit, leads onto back straight. Heavy braking (146→90mph). |
| ~60-62% | **T9** | Thunder Valley | Right | Entry to infield from back straight |
| ~65% | **T10** | — | Right | Continuation through infield |
| ~72% | **T11** | — | Left | Left-hander leading to Carousel |
| ~77% | **T12** | The Carousel | Right | Right-hand complex at top of circuit |
| ~87-90% | **T13** | — | Left | Final corner, leads back to S/F straight |

---

## Telemetry Braking Zones → Turn Mapping

Based on telemetry data (braking zones detected at >50% brake pressure) and GPS coordinates:

| Telemetry % | Dist | GPS Lat | GPS Lon | Entry | Min | Turn |
|---|---|---|---|---|---|---|
| 5% | 166m | 40.689602 | -82.637218 | 114 mph | 92 mph | **T1** |
| 23% | 769m | 40.685283 | -82.639049 | 124 mph | 60 mph | **T4** |
| 51% | 1778m | 40.691009 | -82.639070 | 146 mph | 90 mph | **T8 Esses exit** |
| 62% | 2200m | 40.693028 | -82.636305 | 77 mph | 61 mph | **T9 Thunder Valley** |
| 72% | 2551m | 40.694564 | -82.633150 | 87 mph | 60 mph | **T11** |
| 84% | 2971m | 40.691456 | -82.632517 | 101 mph | 86 mph | **T12 The Carousel** |
| 90% | 3183m | 40.689719 | -82.632408 | 92 mph | 63 mph | **T13** |

---

## Known Problem Corners (BMW M4 EVO GT4)

| Turn | Issue | Data |
|---|---|---|
| **T9 Thunder Valley (62%)** | HIGH PRIORITY — 0.61s loss, highest variance | 77→61mph, 0.66s StdDev |
| **T1 (5%)** | HIGH PRIORITY — 0.58s loss | 114→92mph, inconsistent entry |
| **T8 Esses exit (51%)** | Heaviest ABS zone — 48 hits on best lap | 146→90mph, fastest entry on track |
| **T11 (72%)** | Late Brake Squeeze, 47 ABS | 87→60mph |
| **T13 (90%)** | Most ABS hits (73 on best lap), Late Brake Squeeze | 92→63mph |

---

## Performance History (BMW M4 EVO GT4)

| Date | Session | Best Lap | Cleanest ABS | Notes |
|---|---|---|---|---|
| Jun 2 | Practice | 1:32.491 | 164 | First session — 5.4s improvement over 21 laps |

**Current PB:** 1:32.491
**Cleanest race lap:** N/A (no race yet)

---

## Coaching Notes

- T9 Thunder Valley and T1 are the highest priority — most inconsistent corners.
- T13 has the most ABS hits (73 on best lap) — final corner, possibly over-braking trying to get a good run onto S/F straight.
- Track is shorter and more technical than Fuji — 7 braking zones vs Fuji's 5.
- 5.4s improvement from first lap to best lap shows rapid learning curve.
- Left side tires slightly hotter than right (137°F vs 127°F front) — more right-hand corners.
- Best laps came at the end of the session (Laps 25-27) — still learning the track.
- The Keyhole (T2-T3) and The Esses (T6-T8) are the signature complexes — commit to the line.
