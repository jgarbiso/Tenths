# iRacing Data API — Research & Integration Plan

## Summary

The iRacing Data API provides car, track, series, and race result data. However, as of December 9, 2025, **legacy authentication (username/password) was retired**. All third-party applications must now use **OAuth2**.

---

## Current Status (June 2026)

### What works WITHOUT the API:
- **Car display name** — parsed from .ibt file header (`CarScreenName` field in session info YAML)
- **Track display name** — parsed from .ibt file header (`TrackDisplayName` + `TrackConfigName`)
- **Session type** — parsed from .ibt file header (`EventType`: Race/Practice/Qualify)
- **Car class** — parsed from .ibt file header (`CarClassShortName`)
- **Track metadata** — parsed from .ibt file header (turns, pit speed, length, GPS coords)

**Conclusion: For telemetry processing, we do NOT need the API.** Every .ibt file contains all the metadata needed for session notes generation.

### What the API WOULD add:
- Full car/track catalog (for building a reference database without running sessions)
- Race results auto-pulling (instead of manually downloading CSV/JSON from iRacing website)
- Driver stats, season standings, iRating history
- Series schedules (know what track is coming next week)

---

## Authentication — What Changed

### Before Dec 9, 2025 (Legacy Auth):
```python
# THIS NO LONGER WORKS
from iracingdataapi.client import irDataClient
idc = irDataClient(username="email", password="password")
idc.get_cars()  # → returns data
```

### After Dec 9, 2025 (OAuth2 Required):
```python
# This works but requires a valid OAuth2 access token
from iracingdataapi.client import irDataClient
idc = irDataClient(access_token="your_oauth2_token")
idc.get_cars()  # → returns data
```

### Source:
- [iRacing Support: Legacy Authentication Removal](https://support.iracing.com/support/solutions/articles/31000173894)
- [iRacing Forums: Legacy Authentication Removal - Dec 9, 2025](https://forums.iracing.com/discussion/84226/legacy-authentication-removal-dec-9-2025)

---

## OAuth2 Flows Available

### 1. Authorization Code Flow (Recommended for apps with UI)
- User is redirected to `https://oauth.iracing.com/authorize`
- User logs in on iRacing's site (2FA supported)
- iRacing redirects back to your app with an authorization code
- App exchanges code for access token + refresh token
- **Access token lifetime:** 600 seconds (10 minutes)
- **Refresh token lifetime:** 7 days (single use)
- **Best for:** Web apps, desktop apps with browser integration

### 2. Password Limited Flow (Headless clients only)
- Direct username/password → token exchange
- **Requirements:**
  - Client MUST allow fewer than 3 users
  - Users MUST be pre-registered with iRacing (contact them)
  - Client MUST keep its client secret confidential
  - Bypasses 2FA
- **Not viable** for a personal/open-source tool without registering with iRacing

### Source:
- [iRacing OAuth2 Documentation](https://oauth.iracing.com/oauth2/book/data_api_workflow.html)
- [Password Limited Flow](https://oauth.iracing.com/oauth2/book/password_limited_flow.html)

---

## Python Library: `iracingdataapi`

- **PyPI:** https://pypi.org/project/iracingdataapi/
- **GitHub:** https://github.com/jasondilworth56/iracingdataapi
- **Version:** 1.4.4 (March 2026)
- **Supports:** OAuth2 via `access_token` parameter
- **Dependencies:** requests, pydantic

### Key Methods:
```python
idc.get_cars()          # All cars (id, name, path, class)
idc.get_tracks()        # All tracks (id, name, config, length, turns)
idc.get_carclasses()    # Car class groupings
idc.get_series()        # All series
idc.result_search_series()  # Race results
idc.stats_member_recent_races()  # Your recent races
```

### Verified Issue:
The `username/password` auth appears to succeed (no exception thrown on init) but subsequent API calls return empty responses causing `JSONDecodeError: Expecting value: line 1 column 1 (char 0)`. This is because the legacy auth endpoint returns a cookie but the actual data endpoints reject it.

---

## Implementation Plan (When Ready)

### Phase 1: Local OAuth2 Flow
Build a `tenths login` command that:
1. Starts a temporary local HTTP server (e.g., `http://localhost:8765/callback`)
2. Opens the browser to iRacing's OAuth2 authorize URL
3. User logs in on iRacing's page (supports 2FA)
4. iRacing redirects to localhost with the auth code
5. Script exchanges code for access + refresh tokens
6. Tokens saved to `~/.tenths/tokens.json` (encrypted or at minimum file-permission protected)
7. Auto-refresh before expiry using the refresh token

### Phase 2: Cache Pull
Once authenticated:
```cmd
tenths sync                    # Pull cars, tracks, series → cache/
tenths sync --results          # Also pull recent race results
```

### Phase 3: Auto Race Results
After a race, if cached auth is available:
```cmd
tenths process --fetch-results  # Auto-pull race results from API
```

---

## OAuth2 Client Registration

To use the Authorization Code Flow, we likely need to register Tenths as an OAuth2 client with iRacing. This would give us:
- A `client_id`
- A `client_secret` (if confidential client)
- Approved redirect URIs (e.g., `http://localhost:8765/callback`)

**TODO:** Check if iRacing has a developer portal or if this requires contacting them directly.

---

## Decision: Why We're Not Doing This Now

1. The .ibt header provides all metadata needed for session notes (car name, track name, event type)
2. OAuth2 requires either:
   - Registering as an OAuth2 client with iRacing (unknown process)
   - Using the Password Limited Flow (requires pre-registration per user)
3. The primary use case (telemetry processing) works fully without the API
4. API integration adds complexity (token management, refresh logic, error handling)
5. Better to implement when we build the web frontend (which naturally needs a server + browser flow)

---

## Files

- `tenths/setup_iracing_cache.py` — Existing script (currently broken due to legacy auth retirement). Keep for reference, update when OAuth2 is implemented.
- This document — `docs/IRACING_API.md`
