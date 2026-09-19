# iRacing as the Authoritative Source for Track Corner/Turn Data — Investigation

**Status:** Investigation complete. Recommendation implemented. Written 2026-09-03.
**Author:** Agent session (see git history for commit).
**Question posed:** Should Tenths build/refresh its track corner library from the
iRacing API (or from data already in the `.ibt`) instead of depending on the
enriched community landmark file `tenths/data/trackLandmarksData.json`?

> **Read this first.** The short answer is **no — and the reason is decisive**:
> iRacing does not publish per-corner turn *positions* anywhere a program can
> read them, so no API or SDK call can supply the corner spans this feature
> needs. But the investigation also found that the community file's turn
> **numbers** are already iRacing-standard and correct; the only defect is a
> handful of corrupt corner **distances**, and that is a curation problem, not a
> sourcing problem. The fix is a documented, build-time repair of those records
> keyed on iRacing's canonical `TrackID`, producing the same bundled artifact —
> not a network dependency. See the recommendation.

---

## 1. Does iRacing expose turn/corner data at all, and where?

Three candidate sources were compared. The distinction that matters throughout
is **turn count** (how many corners) versus **turn position** (where each corner
is on the lap, in metres or lap %). Tenths already has the count; it needs the
positions.

### 1a. The `.ibt` file and the pyirsdk (`irsdk`) SDK — local

`tenths/analyzer.py::parse_session_info()` reads the `WeekendInfo` block from the
`.ibt` YAML header. It already extracts, per session and with no network:

| Field read | `session_info` key | Nature |
|---|---|---|
| `TrackID` | `track_id` | iRacing's **canonical numeric track id** — a clean, exact join key |
| `TrackName` | `track_name_internal` | internal slug (e.g. `barcelona_gp`) |
| `TrackDisplayName` / `TrackConfigName` | `track_display_name` / `track_config_name` | display strings |
| `TrackLength` | `track_length_km` | length |
| `TrackNumTurns` | `track_num_turns` | **a count, e.g. 16 — not positions** |

`TrackNumTurns` is the crux for the local path: the header tells you *how many*
corners a layout has, but **carries no per-turn distance, percentage, or spline
marker**. There is no turn-position channel in the telemetry variables either
(`COACHING_CHANNELS` are physics channels: brake, throttle, `LapDistPct`, speed,
accel, RPM, wear — none encode corner boundaries).

Sector markers are also absent locally. `docs/POST_MVP.md` (Track Sections
section) already recorded, and this investigation re-confirmed, that the `.ibt`
header has **no `SplitTimeInfo` block** — iRacing's S1/S2/S3 timing sectors exist
only in the *live* session YAML during a session, read through the SDK while
driving, and even those are timing sectors, not corner boundaries. The installed
`irsdk` module (`…/site-packages/irsdk.py`) exposes no `SplitTimeInfo` structure;
that data is only present in the live in-memory session string.

**Local verdict:** the `.ibt`/SDK give an exact identity (`TrackID`) and a turn
*count*, but **no turn positions**. A local source cannot supply what this
feature needs.

### 1b. The iRacing `/data` web API — network

The official authenticated Data API (`members-ng.iracing.com/data`) was inspected
via the publicly tracked schema at
[popmonkey/iracing-data-api-doc `doc.json`](https://github.com/popmonkey/iracing-data-api-doc)
(a nightly mirror of the live `/data/doc` endpoint; the live endpoint itself
returns HTTP 401 without authentication, which is consistent with the auth
findings in §2). The **entire** `track` group is two endpoints, neither of which
takes parameters:

| Endpoint | Returns | Corner positions? |
|---|---|---|
| `GET /data/track/get` | The full track catalogue: `track_id`, `track_name`, `config_name`, `track_config_length`, `corners_per_lap` (**a count**), `category`, `site`, `pit_road_speed_limit`, coordinates, etc. | **No.** `corners_per_lap` is a count, the same information as `TrackNumTurns`. |
| `GET /data/track/assets` | Per-track image asset paths, "relative to `https://images-static.iracing.com/`" (the endpoint's own documented note), including `track_map` (a base URL) and `track_map_layers`: `background`, `inactive`, `active`, `pitroad`, `start-finish`, `turns`. | **No — these are rendered SVG images.** |

The `track_map_layers.turns` entry is the closest thing iRacing publishes to
"turn data", and it is a **rendered SVG overlay** — a picture of the turn-number
labels positioned over the track-map drawing, meant to be composited in a UI. It
is not a machine-readable list of turn positions in metres or lap %. Extracting
corner boundaries from it would mean parsing an SVG's geometry and re-deriving
where each label sits relative to the racing line — an OCR/geometry heuristic on
an image, not reading a data field. That is a fabrication pipeline, not a source
of authoritative positions.

**API verdict:** the `/data` API returns richer *metadata and imagery* than the
`.ibt` header, but for corner **positions** it offers only the same turn *count*
plus an SVG picture. It does not publish iRacing-standard turn positions.

### 1c. Official track asset/metadata

Covered by `track/assets` above: SVG map layers and static images only. No
structured corner-position payload is published for a `TrackID`.

---

## 2. Authentication and cost

Facts, recorded at the factual level (see also `docs/IRACING_API.md`, which this
section updates and does not contradict):

- **Legacy username/password authentication was retired on 2026-… (Dec 9, 2025).**
  All programmatic access now requires **OAuth2**.
  ([iRacing OAuth2 workflow docs](https://oauth.iracing.com/oauth2/book/data_api_workflow.html),
  [iracingdataapi wrapper](https://github.com/jasondilworth56/iracingdataapi).)
- **Access token lifetime is short** (documented at 600 s / 10 min); refresh
  tokens are single-use with a ~7-day lifetime. A headless "password limited"
  flow exists but **requires registering an OAuth2 client with iRacing and is
  restricted to fewer than 3 users** — not viable for a distributed tool.
- **Accounts with 2FA cannot use the legacy path at all**; the wrapper's own
  README notes this is an iRacing limitation.
- **Rate limiting applies.** The API signals limits with HTTP `429` and
  `x-ratelimit-*` headers; automated clients must back off. (General `429`
  semantics; the specific iRacing quotas are not publicly published as a fixed
  number and were not measured here — see §4.)

**Impact on Tenths' core promise.** `docs/ARCHITECTURE_VISION.md` states the
current tool has **"No server, no database, no accounts"** and is offline by
design; the iRacing API is explicitly deferred to Phase 5. Using it at **runtime,
per end user** would compromise that promise directly: it requires each user to
hold iRacing credentials/tokens, be online at processing time, and stay within
rate limits — for data (corner positions) the API does not even contain. A
**one-time / occasional developer-run library build** that produces a bundled
artifact (offline for all end users) would not compromise the promise. These are
very different, and only the second is compatible with the architecture — but see
§3, because it turns out the API cannot supply the data either way.

---

## 3. Does the API actually contain iRacing turn numbers/positions? (the crux)

**No.** This is the finding that settles the whole task. Neither `track/get` nor
`track/assets` returns per-corner turn positions. They return a corner *count*
(`corners_per_lap`) and an SVG *image* of the turn labels. There is no field, in
any track endpoint, giving the lap distance or percentage where a numbered corner
begins and ends.

Therefore **an API is the wrong tool for this specific need.** Wiring up OAuth2
to fetch `track/get` would buy an exact `TrackID`→name/length/count mapping we
can already read from every `.ibt` header for free, and would not deliver a
single corner boundary. Forcing an API solution here would be exactly the
"try endpoints until one returns something and wire it up" failure this task was
written to avoid.

### What the community file actually is, re-examined

Given the API dead end, the corner-position data has to come from somewhere, and
the only broad source in existence is the bundled community file. A previous
session established it is a heavily enriched derivative of CrewChief's landmark
data (schema changed `landmarkName`→`landmarkNames`, iRacing turn numbers added,
~420 tracks beyond upstream). This investigation adds a decisive observation
about its **quality of turn numbering**, obtained by running the production
loader over the four known-corrupt tracks after the load-time validator drops
the bad records:

```
barcelona gp -> T1 T2 T3 T4 T5 T6 T7 T8  [T9 dropped]  T10 T11 … T16
aragon gp    -> T1 … T9  [T10 dropped]  T11 … T18
aragon moto  -> T1 … T9  [T10 dropped]  T11 … T17
martinsville -> T1 T2  [T3 dropped]  T4
```

Every sequence is a clean `T1..TN` with **exactly the one corrupt corner
missing**. The turn *numbers* are already iRacing-standard and correct — the
corruption is confined to the corrupt record's **distance pair**, nothing else.
Inspecting the raw records shows two different corruption modes:

| Track | Record (`start -> end`) | Prev corner end | Next corner start | Diagnosis |
|---|---|---|---|---|
| `barcelona gp` T9 | `2800 -> 2005` | T8 @ 2690 | T10 @ 3420 | **start is correct and in lap order; end is garbage** (2005 sits back among T5–T8). Unrecoverable end. |
| `aragon gp` T10 | `2236 -> 473` | T9 @ 2176 | T11 @ 2641 | same: start correct, end garbage. |
| `aragon moto` T10 | `2236 -> 473` | T9 @ 2176 | T11 @ 2641 | same. |
| `martinsville` T3 | `481 -> 474` | T2 @ 285 | T4 @ 475 | **genuine transposition** of a tiny 7 m sliver; both values sit correctly between T2 and T4. |

This is why a blind start/end **swap is wrong**: it fixes `martinsville`
(`474 -> 481`, valid, between T2 and T4) but for `barcelona`/`aragon` it would
place the corner back over T5–T8 — a *different* wrong answer, not a fix. The
discriminator is simple and evidence-based: if `start` already falls in lap order
between the previous and next corner (`prev_end < start < next_start`) then the
**start is trustworthy and only the end is corrupt**; if `start > next_start` the
record is a transposition and the pair should be swapped.

For the "start trustworthy, end garbage" cases the true end is **not recoverable
from any authoritative source** — the API does not have it and no other field
encodes it. The honest treatment is to anchor the corner at its known-good start
as a short, bounded zone (clamped below the next corner's start) so `get_turn_name`
can reach it at its real location, rather than fabricating a wide span whose end
we cannot justify.

---

## 4. Terms of service / rate limits for programmatic access (facts, no conclusion)

Recorded as verifiable facts, in the same discipline `docs/OUTSTANDING_ISSUES.md`
requires; **no license or permission conclusion is drawn here** (see the note
added to `docs/OUTSTANDING_ISSUES.md`):

- Programmatic `/data` access requires an authenticated iRacing member session
  via OAuth2; the API is not anonymous. (Live `/data/doc` returned HTTP 401
  unauthenticated during this investigation.)
- The API enforces rate limits signalled by HTTP `429` and `x-ratelimit-*`
  response headers; clients are expected to back off. A specific published
  numeric quota was **not** located and is **not asserted**.
- iRacing account terms govern account and data use; whether they permit
  redistribution of API-returned data, and under what conditions, was **not**
  determined and is left as an explicit open question for the owner.
- The community landmark dataset's own redistribution position is tracked
  separately in `THIRD_PARTY_NOTICES.md` / `docs/OUTSTANDING_ISSUES.md` (RR-001)
  and is unchanged by this investigation.

**Note on why an API is attractive for licensing:** the task framing suggested
that sourcing from the user's own account "sidesteps redistributing a third-party
dataset." That reasoning does not rescue the API here, because the API does not
contain the corner positions in the first place — there is nothing to source. The
licensing question that remains is about the *community file* we continue to
bundle, which is already tracked under RR-001.

---

## 5. Recommendation

**Do not add an iRacing API dependency for corner data. Fix the data at build
time and keep shipping a bundled, offline artifact.** Justification against each
alternative:

| Option | Verdict |
|---|---|
| **Local `.ibt`/SDK turn positions** | Impossible — the header has a turn *count* only, no positions; no SDK field either. |
| **One-time API library build** | Pointless for this need — `track/get`/`track/assets` do not contain corner positions; it would fetch a count + an SVG image. |
| **Per-user runtime API fetch + cache** | Rejected — breaks the offline/zero-account promise (ARCHITECTURE_VISION) *and* still would not return corner positions. |
| **Curated build-time correction of the community file, keyed on `TrackID`** | **Chosen.** It is the only path that actually restores the four corners, needs no network or account, keeps the artifact offline for end users, and preserves 457-track coverage. |
| **"API can't provide turn numbers — do X instead"** | This *is* option 4. The honest alternative the task allowed for. |

### The chosen approach, concretely

1. **A build-time generator** (`tools/build_track_corner_overrides.py`, developer-run,
   never in the end-user pipeline) reads the bundled `trackLandmarksData.json`,
   detects reversed/corrupt corner distance records using the neighbour-order
   evidence above, and emits a small, reviewed **override artifact**
   (`tenths/data/track_corner_overrides.json`) keyed on **iRacing `TrackID`**
   (canonical identity) with the track slug recorded for traceability. Each
   override carries a `reason` and its provenance so the correction is auditable,
   not magic.
2. **`track_map.py` applies the overrides at load**, keyed on `TrackID` when the
   caller supplies it (from `session_info['track_id']`), falling back to the
   existing slug path for tracks the id cannot resolve. The corrected corner then
   flows through the *existing* validation, clamping and unique-naming guards
   untouched — a repaired record must still pass the same range checks as any
   other, so a bad override cannot regress the guarantees `_load_from_landmarks`
   already enforces.
3. **Turn numbers come from the community file**, which is already correct; the
   override only repairs distances, never invents a turn number.
4. **Fallback chain unchanged:** overrides → validated community landmarks →
   `tracks/*.md`. If the override artifact is absent or a track is unknown,
   behaviour is exactly today's. Absent beats wrong; regressing coverage is worse
   than a single dropped corner.

### The one case we honestly cannot fully fix

For `barcelona gp` T9 and `aragon gp`/`aragon moto` T10 the corner **start** is
recoverable and correct, so the corner becomes reachable at its true location; the
corner **end** is genuinely unknown and is bounded conservatively rather than
fabricated. `martinsville` T3 is fully recovered (a clean transposition). This is
stated plainly in the artifact and in the tests, per the Definition of Done: the
doc explains precisely why the chosen source cannot reproduce an exact span for
three of the four, and what is done instead.

### Provenance (per deliverable 5)

- **Inputs used:** `.ibt` `WeekendInfo.TrackID` / `TrackName` (via
  `analyzer.parse_session_info`); bundled `tenths/data/trackLandmarksData.json`.
- **API/SDK fields evaluated and rejected:** `/data/track/get.corners_per_lap`
  (count), `/data/track/assets.track_map_layers.turns` (SVG image); `.ibt`
  `WeekendInfo.TrackNumTurns` (count); live-SDK `SplitTimeInfo` (timing sectors,
  live only). None provide corner positions.
- **Artifact regeneration:** run `python tools/build_track_corner_overrides.py`
  from the repo root; it rewrites `tenths/data/track_corner_overrides.json` and
  prints what it changed. The script is deterministic and idempotent.
