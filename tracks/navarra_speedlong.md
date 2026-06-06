# Circuito de Navarra — Speed Circuit

## Track Info
- **Location:** Navarra, Spain
- **Length:** 2.44 mi / 3.92 km
- **Turns:** 15
- **Pit Speed:** 37 mph / 60 kph
- **Night Lighting:** No
- **iRacing Track No:** 515

---

## Turn Map — Telemetry % to Turn Number

| Track % | Turn | Direction | Description |
|---|---|---|---|
| ~13-15% | T1-T2 | Right hairpin | First braking zone after main straight. Heavy stop. |
| ~28-29% | T3 | Left | Short straight into left-hander heading uphill |
| ~35-36% | T4 | Right | Tight right after T3, uphill section |
| ~43-44% | T5 | Right | Right-hander at bottom of infield |
| ~57-58% | T6-T7 | Left hairpin | Long left-hand complex. Heaviest braking zone on track (111→35mph). |
| ~65-67% | T8 | Left | Left-hander leading onto back section |
| ~75-76% | T9-T10 | Right complex | Top of circuit, tight complex at highest point |
| ~87% | T13-T14 | Right | Right-hand complex before final straight |

---

## Known Problem Corners (BMW M2 CS)

| Turn | Issue | Data |
|---|---|---|
| **T6-T7 (57%)** | Heaviest ABS zone — over-braking into infield hairpin | 93 ABS hits, 87% max brake, entry 111mph to 35mph |
| **T3 (29%)** | HIGH PRIORITY time loss — inconsistent entry | 0.62s loss, 0.52 StdDev |
| **T4 (35%)** | Lugging risk — wrong gear at apex | Apex RPM 3424 (May 24) |
| **T9-T10 (76%)** | Panic braking straight — not combining lateral grip | 61% brake, 0.48G lateral |
| **T1-T2 (14%)** | High ABS on heavy stop | 44-139 ABS depending on session |

---

## Performance History (BMW M2 CS)

| Date | Best Lap | Cleanest ABS | Key Finding |
|---|---|---|---|
| May 22 | 1:56.272 | 97 | First visit, CPU bottleneck (44fps) |
| May 23 AM | 1:55.926 | 187 | |
| May 23 PM | 1:53.495 | 149 | Race PB |
| May 24 | 1:56.323 | 124 | AI race, lugging at T4 |
| May 25 AM | 1:53.650 | 92 | Cleanest race lap |
| May 25 PM | 1:55.162 | 156 | Fatigue regression |

**Current PB:** 1:53.495 (May 23)
**Cleanest race lap:** 92 ABS (May 25)

---

## Coaching Notes

- T6-T7 is the key corner. Build brake pressure progressively on the 111mph stop — don't stab to 87%.
- T3 has the highest variance — pick a fixed braking marker and commit to it every lap.
- When ABS starts climbing mid-race, back off 2-3mph entry for one lap to reset rhythm.
- Fatigue causes regression to old habits after ~6 races in a day.
