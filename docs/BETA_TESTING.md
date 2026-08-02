# Tenths Beta — What to Expect

Thanks for testing. This is a pre-release build: the analysis is solid and
validated, but some rough edges are known and listed here so you don't waste time
reporting things I already know about.

---

## Installing

1. Run `TenthsSetup.exe`. It installs to your user folder — no admin rights.
2. Windows may show a **"Windows protected your PC"** warning. The build is not
   code-signed yet. Click **More info** then **Run anyway**. If you'd rather not,
   that's completely reasonable — say so and I'll get a certificate first.
3. Leave **"Start Tenths with Windows"** checked.

Tenths lives in your system tray. Right-click it for Open Last Report, Pause
Processing, Start with Windows, and Exit.

## Turn on iRacing telemetry

Tenths can only read what iRacing writes, and iRacing writes telemetry only when
logging is on.

- **Per session:** press **Alt + L** in the sim.
- **Always on (recommended):** close iRacing, open `Documents\iRacing\app.ini`,
  set `irsdkLogAll=1` under `[Telemetry]`, save, restart iRacing.

## First check

Open a Command Prompt and run:

```cmd
"%LOCALAPPDATA%\Tenths\Tenths.exe" config
```

That prints every path Tenths is using and whether each exists. **If anything
goes wrong, send me this output first** — it answers most questions immediately.

If your telemetry lives somewhere unusual:

```cmd
"%LOCALAPPDATA%\Tenths\Tenths.exe" config --telemetry-root "D:\path\to\telemetry"
```

---

## Known limitations

These are understood and tracked. No need to report them.

### Physics coaching is GT4-specific only
Braking and shifting diagnostics were validated on GT4 cars. Every other class —
including GT3 — uses a **Generic** profile. Your report shows your real iRacing
class, but the coaching rules are not yet class-specific beyond GT4. Some
notes may be less relevant for your car.

### Race results need a manual export
For finishing position and iRating on a race report, export the result from the
iRacing website (the Export button on a race result page). It lands in Downloads
and Tenths matches it automatically. Without it you still get full telemetry
coaching, just no position or iRating.

### Corner detection misses light-braking corners
Braking zones are found where brake pressure exceeds 50%, so gentle corners may
not appear. Fast, heavy-braking corners are reliable.

### Coaching thresholds are not fully validated
Speed-relative thresholds are new and tuned against a small number of sessions.
If a coaching note looks obviously wrong for a corner you know well, **that is
worth reporting** — it's exactly the feedback I need.

---

## What is worth reporting

Most valuable first:

1. **A coaching note that is wrong.** You know your driving better than the tool.
   Tell me the corner, what it said, and what you'd actually say.
2. **A session that produced no report.** Include the log (below).
3. **Wrong numbers.** Lap times should match iRacing exactly. If they don't,
   that's serious — tell me immediately.
4. **A crash or a stuck tray icon.**
5. **Anything confusing in the report.** If you have to work out what a number
   means, that's a design bug.

## How to report

Include:

- **The log file:** `%LOCALAPPDATA%\Tenths\logs\tenths.log`
  (paste that path into Explorer's address bar). This is the single most useful
  thing you can send.
- **Output of `Tenths.exe config`**
- The car and track, and roughly when the session was.
- The `session_report.html` if the problem is visible in the report.

> The log records session processing and errors. It does not contain your
> password or payment details. It does contain your file paths and the car and
> track names you drove.

## Where your data lives

```
Documents\iRacing\telemetry\
├── index.html                       ← browse all sessions
├── _archive\                        ← processed .ibt files
└── <car>\<track>\<date>\<time>\
    ├── session_report.html
    ├── session_notes.md
    └── session_summary.json
```

Nothing is uploaded anywhere. Everything stays on your machine.

## Uninstalling

Uninstall from Windows Settings, or the Start Menu entry. That removes the app,
its logs, and the settings file. **Your reports and archived telemetry are left
in place** — they live in iRacing's own `Documents\iRacing\telemetry` folder.
Delete that yourself if you want them gone.

---

## A note on failures

If processing fails, Tenths retries a few times, then shows a notification and
**leaves your `.ibt` file alone** so nothing is lost. The reason is always in the
log. If you hit this, sending the log means I can usually fix it directly.
