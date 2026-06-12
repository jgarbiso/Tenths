# UX Improvements — HTML Report

## Status: Core issues RESOLVED ✅

Issues 1-4 from the original review have been implemented. Additional enhancements remain documented below for future work.

---

## Resolved Issues

### 1. Action buttons vs mode toggles ✅
- Created new `.action-btn` CSS class — outlined border, accent-blue when active
- "⊕ Brake Points" and "⇄ Compare" are visually distinct from pill-shaped Speed/Brake toggles

### 2. Controls visual grouping ✅
- Added `.controls-divider` (1px vertical line) between control groups
- Map: Rotate | Speed/Brake | Brake Points
- Telemetry: Lap selector | Compare + delta | Legend

### 3. Active state clarity ✅
- Active action buttons: `border-color: var(--accent-blue); background: #448aff18; color: var(--accent-blue)`
- Compare shows lap time delta badge: "Δ -0.8s" (green) or "Δ +0.8s" (red)
- Compare dropdown has blue left border when visible

### 4. Rotation controls clarity ✅
- Added "Rotate" text label before the ↶/↷ buttons
- Now reads: "Rotate ↶ 45° ↷"

---

## Development Notes (report.py)

### ⚠️ JS Code Structure Warning

The `_get_js()` function in `report.py` returns a large block of JavaScript as a Python string. When editing:

1. **Brace matching is critical** — Python doesn't validate JS syntax. A stray `}` will silently break all subsequent functions at runtime with no build-time error.
2. **Test after every edit** — Always regenerate the HTML and open in browser after modifying JS in report.py. Check browser console (F12) for errors.
3. **Function boundaries** — Each function must end with exactly one `}` at the correct indentation. When moving code between functions, double-check you didn't duplicate or lose a closing brace.
4. **Template literals** — The JS uses backtick strings with `${}` interpolation. These are inside a Python string, so be careful with escaping. Python f-strings are NOT used inside `_get_js()`.

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
