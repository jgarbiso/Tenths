# Related Tools — Research Record

**Researched 2026-09-25.** A snapshot of the iRacing telemetry / AI setup landscape,
taken to decide whether to build, buy or borrow. Products change quickly: treat
feature and pricing details as true on that date and re-check before relying on
them. Everything here comes from each product's own public pages or repository;
none of the commercial tools was tested hands-on.

**Question asked:** is there already an iRacing telemetry AI agent doing what the
Tenths setup notebook does — capture the setup as driven, measure car behaviour
from telemetry, and recommend setup changes from the driver's own data?

**Answer:** commercially, yes — at least one close match. In open source, no:
nothing combines setup capture, telemetry-measured balance, setup history and
experiment tracking. See "Decisions" at the end.

---

## Commercial: AI setup engineers (direct overlap with the setup notebook)

| Product | What it does | Model | Notes |
|---|---|---|---|
| [Virtual Paddock](https://virtualpaddock.app/en/) | AI "Setup Engineer" from the stint's `.ibt`; measures understeer/oversteer independently of driver feedback; ranked changes with trade-offs; per-car real slider ranges; staged process (aero → ARBs → springs → dampers → electronics → diff → alignment); detects whether each change was applied; weighs driver ratings; stops when lap times plateau | Cloud, account, telemetry upload. Closed beta, invite only. Free tier (15 "Radio Calls"/mo) to $6/mo; setup analysis consumes Radio Calls, cost per analysis not stated | Closest match. Supports Ford Mustang GT3 and Road Atlanta Full. **Owner decided not to use it (2026-09-25).** |
| [Coach Dave Delta — Setup IQ](https://coachdaveacademy.com/tutorials/how-to-use-setup-iq-delta/) | Auto-tunes any setup from braking/steering/throttle telemetry; writes a new setup file per iteration ("IQ V1 …"); needs ≥ 5 clean laps per iteration | Paid Delta subscription | LMU and ACC only; **iRacing "coming soon"** as of 2026-09. |
| [PitLabs](https://www.overtake.gg/threads/pitlabs-ai-setup-engineer-telemetry-iracing.298376/) | AI setup engineer: telemetry plus the driver's description; explains each change | Paid; account sync | Launched 2026-08; little independent evidence. |
| [Racing Setup AI](https://www.racingsetup.com/en/) | Chat assistant; upload setup files or telemetry screenshots | Paid tiers | Lighter on data than the others. |

## Commercial: coaching and telemetry (overlap with Tenths' session reports)

- [Track Titan](https://www.tracktitan.io/) — AI coaching against reference laps; free tier without AI tips; setups on the top tier.
- [Trophi.ai](https://www.trophi.ai/sim-racing-coaching/iracing) — live voice coach, post-session technique scoring; partnered with Grid and Go setups.
- [Hotlap.ai](https://www.hotlap.ai/) — free; distance-aligned lap comparison, understeer/overdriving detection; no setup advice.
- [Braking Lab](https://www.brakinglab.com/en/features/race-engineer) — lightweight Windows client analysing braking zones automatically (closest to Tenths' report side).
- [RaceData AI](https://www.racedata.ai/), Garage 61 (see `POST_MVP.md` → Garage 61 Reference Laps) — telemetry platforms.

## Open source

| Project | What it does | License (2026-09-25) | Reusable in Tenths (MIT)? |
|---|---|---|---|
| [Simulator Controller](https://github.com/SeriousOldMan/Simulator-Controller) | Mature AI pit crew (444★, 14k commits). Setup Workbench recommends changes from described handling problems; LLM Setup Engineer analyses handling and driving style from one lap's telemetry; Telemetry Analyzer plays tones on understeer/oversteer. Supports iRacing among ~11 sims. AutoHotkey. | CC BY-NC-SA (non-commercial, share-alike) | **No** — ideas only |
| [RacerzLab / RaceLab Garage](https://github.com/kishosha706/RacerzLab) | Local-first `.ibt` analysis; baseline/test "Test Basket" with an **A/B/A2** workflow; evidence-gated conclusions; has an `AGENTS.md`. Does *not* recommend setup changes; no understeer metric; no `.sto` decoding. NASCAR-oval focus, alpha, 0★. | None stated (all rights reserved) | **No** — ideas only |
| [PulsePanda/iracing-telemetry-analyzer](https://github.com/PulsePanda/iracing-telemetry-analyzer) | Local Node.js lap comparison, braking zones, consistency. Likely the "iracing-telemetry-analyzer" reviewed in `ARCHITECTURE_VISION.md` (decision there: borrow, don't build on). | None stated | No |
| [TRACE.IT](https://github.com/naizens/TRACE.IT) | Desktop `.ibt` lap overlay / per-corner time | None stated | No |
| [rapidtelem](https://github.com/mhmatthew/rapidtelem) | Single-HTML-file telemetry viewer | MIT | Yes, but nothing Tenths lacks |
| [Mu](https://github.com/patrickmoore/Mu) | `.ibt` → MoTeC i2 export; saves the setup used (inactive since 2022) | None stated | No |
| [MotecLogGenerator](https://github.com/BoYanZh/MotecLogGenerator) | Many formats incl. `.ibt` → MoTeC `.ld` | GPL-3.0 | Only by relicensing Tenths |
| [race-mcp](https://github.com/consolecowboy0/race-mcp), [racing-engineer](https://github.com/Wesleyxl/racing-engineer), [RaceEngineer](https://github.com/benitz94/RaceEngineer) | Early "agentic race engineer" projects on **live** telemetry, mostly coaching | race-mcp MIT; others unchecked | Not needed |
| [iracing-mcp-server](https://github.com/ellettie/iracing-mcp-server), [iracing-data-mcp-server](https://github.com/emilioSp/iracing-data-mcp-server) | MCP access to live SDK / iRacing Data API | — | Not needed |
| [ibt](https://github.com/teamjorge/ibt) (Go), [ibt-telemetry](https://github.com/SkippyZA/ibt-telemetry) (Node) | `.ibt` parsers | — | Tenths uses pyirsdk |

**Licensing rule used:** a repository with no license is all rights reserved; do
not copy code from it. CC BY-NC-SA and GPL are incompatible with Tenths' MIT
license. Ideas, methods and facts (e.g. "a softer front ARB adds oversteer") are
not covered by these licenses and may be used; write our own implementation.

---

## What Tenths does that none of these do (as of 2026-09-25)

- Fully offline, no account, the driver's data never leaves the machine.
- Evidence the driver or an agent can audit: balance compared **at equal lateral
  g**, measured only on **settled-tyre laps**, against a **same-setup noise
  floor** and **A/B/A drift correction**. All four were added after raw
  comparisons misled us on real sessions (see `tenths/setup_notebook.py`).
- Setup captured as driven (in-car values from live channels), a per car/track
  history, per-track experiment logs and per-car lessons, readable by any agent.

Where the commercial tools are ahead: per-car expert knowledge built in, an
in-sim overlay and radio, and reference laps from faster drivers.

## Ideas adopted from this research

| Idea | Source | Where it went |
|---|---|---|
| A/B/A2 test design to separate a change from drift | RacerzLab | Notebook "A/B/A tests" section; `ENGINEER.md` test protocol (2026-09-25) |
| Fixed order of work and a stopping rule | Virtual Paddock's public description | `ENGINEER.md` "Order of work and when to stop" (2026-09-25) |
| Per-car garage ranges so recommendations never exceed the car | Virtual Paddock | Already had `limits.json` |
| Verify each change actually made it into the car | Virtual Paddock | Already had "Changes vs session N" + garage export check |

## Ideas deferred

- Live understeer/oversteer tones in the car (Simulator Controller) — only if
  live feedback is ever in scope; reimplement, do not copy.
- Reference laps from faster drivers — `POST_MVP.md` → Garage 61 Reference Laps.

## Most useful source for new cars

Not any of the above: iRacing's official **car user manual** (PDF, linked from
iracing.com/resources/user-manuals). For the Mustang GT3 it supplied damper
direction, ARB direction, ABS/TC semantics and aero targets, recorded in that
car's `limits.json`. Cross-check against the in-game garage and its setup notes
(garage Export `.htm`), which are more current than the manual.

## Setup knowledge sources (follow-up, 2026-09-26)

| Source | What it gives | Use |
|---|---|---|
| iRacing **Official Setups** in the garage (baseline, `_sprint`, `_endurance`, `_wet`, `fixed`, downforce variants per the car manual) | iRacing's own car-specific setups for the current build; exportable to readable `.htm` via File Actions > Export | **Best reference source**: free, no account, no licensing issue. Compare variants to see how iRacing moves each setting between trims. Proposed: an importer for garage `.htm` exports as notebook reference setups. |
| iRacing car user manual (per car) | Direction of every adjustment, aero targets, in-car setting semantics | Already used for the Mustang GT3 (`limits.json` guide) |
| [OptimumG Tech Tips](https://optimumg.com/category/technical-papers/tech-tips/) (free PDFs; e.g. [Springs & Dampers 2](http://downloads.optimumg.com/Technical_Papers/Springs&Dampers_Tech_Tip_2.pdf), [5](http://downloads.optimumg.com/Technical_Papers/Springs&Dampers_Tech_Tip_5.pdf)) | Physics of roll stiffness distribution, damping ratios | Background for the springs/dampers stages |
| [Sim Racing Manual — understeer/oversteer fixes](https://simracingmanual.com/setups/understeer-oversteer-fixes/) | Lever-by-phase map: brake bias (entry), diff (exit), ARBs (mid), wing (high speed), pressures (everywhere) | Consistent with the Mustang manual; matches the notebook's phases |
| [iRacing Car Setup Guide (2010)](https://ir-core-sites.iracing.com/members/pdfs/iRacing_Car_Setup_Guide_20100910.pdf) | iRacing's official general fundamentals | Old; fundamentals only |
| Books: Carroll Smith *Tune to Win*; Milliken *Race Car Vehicle Dynamics*; Paul Haney *The Racing & High-Performance Tire* | Standard references behind most guides | Paid |
| Track Titan setup library | Mustang GT3 "High Downforce Baseline" page exists | Values not visible without a paid login — not usable |
| [SimRace.app](https://simrace.app/problems) | Another AI race engineer reading telemetry, free tier | Competitor, not a reference |

No open-source project was found with a reusable handling-problem -> setup-change
knowledge base.

## Garage 61 setups (follow-up, 2026-09-26)

Members' setup parameters are public by default; commercial (setup-shop) setups
are forced private. The API reaches other drivers' laps only with Garage 61's
approval, and it is unverified whether lap details include setup values. Full
notes and the proposed integration: `POST_MVP.md` → Garage 61 Reference Laps.

## Decisions

- 2026-09-25: Owner is not interested in Virtual Paddock (cloud, account,
  metered). Continue building the offline setup notebook.
- 2026-09-25: Do not build on any open-source project; borrow ideas only (above).
- 2026-09-26: Owner wants to explore Garage 61 public setups as reference
  examples. API application "Tenths" requested the same day (own data +
  analyses, personal token); awaiting approval. Submitted form, rationale and
  next steps: `POST_MVP.md` → Garage 61 Reference Laps → API application request.
