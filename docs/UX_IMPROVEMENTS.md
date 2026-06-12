# UX Improvements — HTML Report

## Status: Documented, not yet implemented

---

## Problem: Button Discoverability & Hierarchy

### Issues

1. **"Compare" and "Brake Points" look identical to mode toggles (Speed/Brake)** — All use the same `toggle-btn` class. Users can't distinguish view modes from action buttons.
2. **Controls split across two areas** — Map controls in map header, telemetry controls in telemetry header. No visual grouping.
3. **Active state too subtle** — When Compare is active, just gets slightly lighter background. Hard to tell what's on/off.
4. **Rotation controls look like undo/redo** — ↶/↷ could be confusing.

### Recommended Fix: Option A — Outlined Action Buttons

Give action buttons a distinct visual treatment from mode toggles:

- **Mode toggles** (Speed/Brake): Pill-shaped group, mutually exclusive, current style
- **Action buttons** (Compare, Brake Points): 1px border with rounded corners, accent color border when active, filled background when active

```
Inactive:  border: 1px solid var(--border); color: var(--text-secondary);
Active:    border-color: var(--accent-blue); background: #448aff20; color: var(--text-primary);
```

Visual treatment:
```
[ Speed | Brake ]   〔⊕ Brake Points〕

[ Lap 4 ★ ▾ ]   〔⇄ Compare〕  [ Lap 5 ▾ ]
```

### Additional Enhancements to Implement

1. **Lap time delta between compare dropdowns** — Show "Δ +0.8s" so you immediately know the gap without reading the chart

2. **Color-code comparison dropdown** — Left border in cyan/accent-blue when active to distinguish from primary selector

3. **Keyboard shortcuts** (future):
   - `1-9` to select laps
   - `C` to toggle compare
   - `B` for brake points
   - `S` for speed mode, `K` for brake mode
   - Show as tooltips on hover

4. **Active state badge on section headers** — When Brake Points is active: `TRACK MAP • Brake Points`

---

## Other UX Items to Address

### Table Density
- Corner names wrap on narrow viewports — consider truncating with tooltip on hover
- Braking zones table has many columns — consider responsive column hiding on smaller screens

### Map Usability
- Add zoom controls (+ / - buttons) for users without scroll wheels or trackpads
- Show track name inside the map as a watermark when zoomed out

### Telemetry Charts
- Consider adding vertical dashed lines at braking zone entry points on the charts (align map zones with chart positions visually)
- Clicking a braking zone in the table could scroll/highlight that region on the chart

### Mobile
- Current layout breaks below ~900px — the grid collapses but map becomes very small
- Consider a mobile-first "summary mode" that shows just: lap time, position badge, ABS sparkline, key findings text
