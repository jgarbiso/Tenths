# Technical Debt

Items identified during development that are acceptable for current use but should be addressed before production distribution.

---

## Watcher (`tenths/service/watcher.py`)

| # | Issue | Impact | Fix When |
|---|-------|--------|----------|
| W1 | `_set_low_priority()` lowers entire process priority, not per-thread | Main loop also runs at below-normal during processing | Before adding tray UI in same process (Tier 3) |
| W2 | `_can_open_exclusive()` uses shared read, not true exclusive lock | Could theoretically trigger if iRacing allows read while still writing | If false triggers observed in production |
| W3 | No processing of pre-existing .ibt files on startup | Files present before watcher starts are missed | Tier 2 — add startup scan |
| W4 | `_processed` set grows unbounded | Negligible for typical sessions (1-5 per evening) | If watcher runs continuously for weeks |

## Analyzer (`tenths/analyzer.py`)

| # | Issue | Impact | Fix When |
|---|-------|--------|----------|
| A1 | Braking zone detection only catches >50% brake pressure | Misses light-braking corners (e.g., 11 of 16 turns at Barber) | When iRacing API provides official turn positions (Phase 5) |
| A2 | Schema downgrade not prevented in migration system | If a newer Tenths version's JSON is opened by older version, it stamps the older schema | Before multi-user distribution |

## Report (`tenths/report.py`)

| # | Issue | Impact | Fix When |
|---|-------|--------|----------|
| R1 | JS is embedded as Python string — no syntax validation at generation time | Stray brace can silently break all rendering | Consider extracting JS to a separate .js template file (Phase 2 dashboard) |
| R2 | Leaflet + Chart.js loaded from CDN | First load requires internet; subsequent loads cached | Bundle locally if packaging as offline installer (Tier 3) |

## Process (`tenths/process.py`)

| # | Issue | Impact | Fix When |
|---|-------|--------|----------|
| P1 | `generate_day_notes` session type detection is a string match list | New iRacing session types (e.g., "Warmup", "Lone Qualify") may not be caught | Add to list as discovered, or switch to "skip header if `## ` + timestamp pattern found" |
