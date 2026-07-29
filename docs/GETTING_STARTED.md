# Getting Started with Tenths

Tenths is your automated race engineer for iRacing. It watches for new telemetry, and the moment a session ends it builds a visual coaching report that tells you **where you're losing time and why** — no manual steps, no charts to decipher.

This guide gets you from install to your first report in about five minutes.

---

## What you need

- **iRacing** (any membership)
- **Windows 10 or 11**

That's it for installation. Tenths analyzes laps and renders the Summary view locally. The current Detailed map/charts load third-party CDN assets and need internet access for full functionality.

---

## Step 1 — Install Tenths

1. Download the latest **Tenths installer** (`TenthsSetup.exe`).
2. Run it. It installs to your user folder (no admin rights needed) and adds a Start Menu entry.
3. During setup, leave **"Start Tenths with Windows"** checked so Tenths is always ready when you race.

Tenths runs quietly in your **system tray** (bottom-right of the taskbar, near the clock). Look for the Tenths icon — that's it running in the background.

---

## Step 2 — Turn on iRacing telemetry

This is the one setting you must enable — Tenths analyzes the telemetry files iRacing writes to disk, and iRacing only writes them when telemetry logging is on.

**Option A — per session (simplest):**
While in the sim (you don't need to be in the car yet), press **Alt + L**. A small telemetry icon appears on screen. You'll need to do this each time you enter a session.

**Option B — always on (set once, forget it):**
1. Close iRacing.
2. Open `Documents\iRacing\app.ini` in Notepad.
3. Find the `[Telemetry]` section and set:
   ```
   irsdkLogAll=1
   ```
4. Save and restart iRacing. Now every session records automatically.

Most people prefer Option B so they never forget.

> Telemetry files land in `Documents\iRacing\telemetry\`. Tenths watches this folder automatically.

---

## Step 3 — Drive

With Tenths running, drive a practice, qualifying session, or race. When you leave the session (or the session ends), iRacing finishes writing the telemetry file. Files created while Tenths is stopped are not yet recovered automatically on startup; this is a documented release blocker.

---

## Step 4 — Get your report

A few seconds after your session ends, Tenths pops a **Windows notification**. For a race it looks like:

> **P4/12 at Mid-Ohio | iR +23**
> Best: 1:31.8 (14 laps)

For a practice or test session the title is just the session type and track (e.g. *"Practice at Mid-Ohio"*), and a new personal best adds a *"🏆 NEW PERSONAL BEST!"* line.

Click the **Open Report** button on the notification to open your report in the browser. (You can also right-click the tray icon → **Open Last Report**.)

---

## Reading your report

The report opens on the **Summary** tab — designed to be read at a glance, even in VR.

**Hero numbers** (top row):
- **Best Lap** — your fastest clean lap
- **Recoverable** — total time you're leaving on the table vs your own best corners
- **vs Previous** — how you compare to your last session here (green = faster)
- **Laps** — valid laps analyzed

**Next Race Focus** — the single most important thing to work on, in plain English:
> *T5 Hairpin — 0.41s · Release the brake more progressively — you're losing time to a stepped release.*

**Focus Cards** — your top 3 time-loss corners, each with a coaching sentence and the corner's entry→apex speed so you know exactly which corner it means.

**Mini track map** — your problem corners marked in red so you can see where they are on the lap.

Want the raw data? Click the **Detailed** tab for the full track heatmap, telemetry traces, brake-release shapes, and lap tables.

---

## The tray menu

Right-click the Tenths tray icon:

| Option | What it does |
|--------|--------------|
| **Open Last Report** | Opens your most recent session report (also the default double-click action) |
| **Pause Processing** | Temporarily stops watching for new sessions |
| **Start with Windows** | Toggle auto-launch on boot |
| **Exit** | Stops Tenths |

> To browse indexed sessions, open **`index.html`** at the top of your telemetry folder (see "Where your data lives" below).

---

## Where your data lives

Successfully processed watcher sessions are saved under your telemetry folder, organized by car → track → date → session time. Manual CLI output is not yet fully consistent with this layout and is tracked as a release blocker:

```
Documents\iRacing\telemetry\
├── index.html                        ← Browse all your sessions
├── bmwm4gt3\
│   └── roadatlanta_full\
│       └── 2026-07-22\
│           └── 20-57-09\
│               ├── session_report.html   ← Your visual report
│               ├── session_notes.md      ← Text coaching notes
│               └── session_summary.json  ← Raw data
```

Open **`index.html`** at the top level to see every indexed session and filter by car or track. The current tray menu does not include a Browse Sessions action.

---

## Race results (optional)

To show your finishing position and iRating change on race reports, export the result from the iRacing website (the "Export" button on a race result page) — it downloads to your Downloads folder, and Tenths automatically matches it to the session. Tenths identifies your result using your own driver ID from the telemetry, so no configuration is needed.

---

## Troubleshooting

**No report appeared after my session.**
Telemetry logging probably wasn't on. Confirm Step 2 — press Alt+L in-sim, or set `irsdkLogAll=1` in `app.ini`. Check that new `.ibt` files are appearing in `Documents\iRacing\telemetry\`.

**Tenths showed a "Telemetry folder not found" notification.**
Tenths couldn't find `Documents\iRacing\telemetry\`. Enable telemetry in iRacing (Step 2) so the folder gets created, then restart Tenths from the Start Menu.

**The report opened but corner names look like percentages (e.g. "83.0%").**
Tenths has corner data for 450+ iRacing tracks built in. If a track shows percentages, it's one we don't have yet — the analysis is still fully accurate, just without the named turns.

**I don't see the tray icon.**
Click the small "^" arrow near the clock to show hidden icons. You can drag the Tenths icon out to keep it visible.

**How do I stop Tenths from running?**
Right-click the tray icon → Exit. To stop it launching on boot, uncheck "Start with Windows" first.

---

## That's it

Race as normal with Tenths and telemetry recording enabled. Each successfully processed session produces coaching that points to the next opportunity; startup recovery, retries, and complete per-session CLI consistency remain pre-release work.
