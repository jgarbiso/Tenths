# Fuji International Speedway — No Chicane

## Track Info
- **Location:** Oyama, Shizuoka Prefecture, Japan
- **Length:** 2.78 mi / 4.48 km
- **Turns:** 14
- **Pit Speed:** 35 mph / 56 kph
- **Night Lighting:** No
- **AI Enabled:** Yes
- **iRacing Track No:** 445
- **Configs:** 2 (No Chicane, with Chicane)

---

## Turn Map — Telemetry % to Turn Number

Layout flows clockwise. Start/Finish is on the main straight (top of map, traveling left-to-right).

| Track % | Turn | Name | Direction | Description |
|---|---|---|---|---|
| ~14-15% | **T1-T2** | TGR Corner | Right | End of 0.9mi main straight. Heaviest braking zone. |
| ~27-28% | **T3** | Coca-Cola Corner | Right | Medium-speed right after short straight from T1-T2 |
| ~35-36% | **T4** | 100R | Left | Fast left-hand sweeper, high lateral G |
| ~43% | **T5-T6** | Hairpin | Left | Tight hairpin. Second-heaviest braking zone. |
| ~60-63% | **T7-T8** | — | Left/Right | Infield section leading to back straight |
| ~67-68% | **T9** | 300R | Left | Fast left sweeper, minimal braking |
| ~74-79% | **T10** | Dunlop Corner | Right | Medium-speed right at bottom of circuit |
| ~80-82% | **T11-T12** | Netz | Left | Left-handers climbing back uphill |
| ~87-90% | **T13-T14** | Panasonic Corner | Left | Final corner complex before main straight |

---

## Telemetry Braking Zones → Turn Mapping

Based on actual telemetry data (braking zones detected at >50% brake pressure):

| Telemetry % | Turn | Confirmed By |
|---|---|---|
| 14-15% | **T1-T2 TGR Corner** | All sessions — heaviest ABS zone, 154-157mph entry |
| 27-28% | **T3 Coca-Cola Corner** | All sessions — 117-124mph entry, often 0 ABS |
| 43% | **T5-T6 Hairpin** | All sessions — 90-98mph entry to 42-71mph |
| 60-63% | **T7-T8** | All sessions — 132-139mph entry, second-heaviest braking |
| 74-79% | **T10 Dunlop Corner** | All sessions — 74-83mph entry, ABS + oversteer risk |

Note: T4 100R, T9 300R, and T13-T14 Panasonic are fast corners with minimal or no heavy braking (not detected as braking zones at >50%).

---

## Known Problem Corners (BMW M4 EVO GT4)

| Turn | Issue | Data |
|---|---|---|
| **T10 Dunlop (74-79%)** | Late Brake Squeeze + oversteer risk on trail braking | 45-61 ABS, 0.41s time loss |
| **T1-T2 TGR (14-15%)** | Lazy Initial Brake — T2Peak 1.12s (target <0.4s). Regresses under race pressure. | 6-175 ABS depending on session |
| **T7-T8 (60-63%)** | Late Brake Squeeze, second-heaviest braking zone | 18-64 ABS, entry 132-139mph |
| **T5-T6 Hairpin (43%)** | Occasional Early Shift flag | 0-15 ABS, generally clean |

---

## Performance History (BMW M4 EVO GT4)

| Date | Session | Best Lap | Cleanest ABS | Notes |
|---|---|---|---|---|
| May 25 | Practice | 1:47.866 | 93 | First session |
| May 25 | Race | 1:47.318 | 37 | Cleanest (at the time) |
| May 26 | Qualifying | 1:47.334 | 77 | |
| May 26 | Race | 1:45.642 | 69 | PB (at the time) |
| May 28 | Practice | 1:46.761 | 181 | High ABS, experimenting |
| May 28 | Race | 1:46.059 | 107 | P18/25, SOF 1402, consistent |
| May 30 | Practice | 1:45.841 | 95 | T3 brake shape 0.43s |
| May 30 | Race (AM) | 1:45.703 | 23 | P7/27, NEW PB + CLEANEST |
| May 30 | Practice (PM) | **1:45.229** | 112 | **NEW PB**, T10 at target |
| May 30 | Race (PM) | 1:47.428 | 11 | P24/28, incidents Lap 2-3 |
| May 31 | Practice | 1:45.001 | 214 | T1 0.42s, T3 0.35s — AT TARGET |
| May 31 | Race | 1:47.8 | — | P26/27, wall at T3 exit (Lap 2) |

**Current PB:** 1:45.001 (May 31 practice)
**Cleanest race lap:** 23 ABS (May 30 Lap 12)

---

## Coaching Notes

- T10 Dunlop is the current priority — Late Brake Squeeze + oversteer risk on trail braking.
- T1 is solved on clean laps (6 ABS on May 26) but regresses under race pressure (88 ABS on May 28). The faster initial brake spike triggers ABS because modulation after the spike isn't there yet.
- All zones show "Lazy Initial Brake" — need to spike pedal to 80-90% within 0.4s while downforce is highest, then progressively release as speed drops.
- Apex brake 0% everywhere — car is rotating well, no over-slowing.
- Oversteer risk flagged at T1 exit and T10 Dunlop — releasing brake too late into rotation.
- Left side tires run 10-14°F hotter than right — track is predominantly right-hand corners.
- Gap to field: ~3s to winner, ~2s to midfield. Brake shape improvement will find 1-2s.
- The GT4 braking sequence: Spike → Progressive release → Off before turn-in.
