# Tenths — Packaging and Bundle Analysis

**Measured:** 2026-07-31, commit `d2c16a8`, PyInstaller 6.21.0, Python 3.14.5, Windows x64.

## Bundle composition

Total bundle: **80.9 MB** (dist/Tenths/ directory, after sqlite3 exclusion). Installer: **~30 MB** (Inno Setup LZMA2 compression).

### Breakdown by category

| Category | Size (MB) | Needed? | Notes |
|---|---:|---|---|
| numpy + numpy.libs | 25.9 | Yes | BLAS/LAPACK binaries; analyzer.py uses NumPy throughout |
| pandas + pandas.libs | 13.4 | Yes | DataFrames are the core data structure in analyzer.py |
| PIL (Pillow) | 12.7 | Yes | tray.py uses Image and ImageDraw for the system tray icon |
| Tenths.exe | 13.5 | Yes | PyInstaller bootloader + frozen bytecode |
| python314.dll | 6.5 | Yes | CPython runtime |
| libcrypto-3.dll + libssl-3.dll + _ssl.pyd | 6.0 | Indirect | Pulled by logging.handlers (SocketHandler uses ssl). Cannot be excluded without breaking logging. |
| sqlite3.dll + _sqlite3.pyd | 1.5 | **No** | Pulled by pandas.io.sql. Tenths never uses SQL. **Excluded in spec. Saves ~5.4 MB total** (sqlite3 + deps that only sqlite3 pulled). |
| base_library.zip | 1.3 | Yes | Stdlib bytecode |
| data/ (trackLandmarksData.json) | 1.0 | Yes | Bundled track database (457 tracks) |
| unicodedata.pyd | 0.7 | Yes | Unicode normalization for file/track names |
| tzdata | 0.5 | Low | Pulled by pandas for timezone ops. Tenths uses only `datetime.timezone.utc` (stdlib). Removing breaks `import pandas` on some builds. **Kept for safety.** |
| setuptools | 0.02 | Harmless | 8 files, 18 KB. Not worth chasing. |
| tracks/ (legacy .md maps) | 0.1 | Yes | Fallback track maps |
| Everything else | ~4.2 | Yes | yaml, dateutil, watchdog, winotify, pystray, etc. |

### Irreducible core: ~76 MB

numpy (26) + pandas (13) + PIL (13) + python (6.5) + ssl (6) + exe (13.5) = ~78 MB. The bundle is largely irreducible without replacing pandas (a major rewrite of analyzer.py, not worth it) or PIL (needs Image/ImageDraw for the tray icon, no lighter alternative).

### What was excluded

Already in the spec's `excludes` list:
- `tkinter` — GUI toolkit, unused
- `matplotlib` — plotting, unused
- `scipy` — scientific computing, unused
- `IPython`, `jupyter`, `notebook` — interactive tools, unused
- `sqlite3` — pulled by pandas.io.sql, Tenths never uses SQL storage. Saves ~1.5 MB.
- `pytest`, `_pytest` — collected via numpy._pytesttester reference but never shipped as real directories. Listed defensively.

### What was NOT excluded and why

- **ssl/libcrypto/libssl (6 MB):** Imported by `logging.handlers` (SocketHandler), which is in the import chain via `tenths/applog.py`. Excluding it breaks the logging module. Not safe.
- **tzdata (0.5 MB):** pandas imports it unconditionally on some builds/platforms. Excluding it risks a runtime `ImportError` on a user's machine even though Tenths itself never creates timezone-aware Series. Kept for safety at 0.5 MB.
- **setuptools (18 KB):** Not worth the risk of chasing. Negligible size.

### Previous hypothesis — corrected

The 2026-07-28 review suspected pytest and setuptools were inflating the bundle. Measured 2026-07-31:

- `pytest` / `_pytest` directories **do not exist** in `dist/Tenths/_internal/`. The ~150 TOC references come from `numpy._pytesttester`, a numpy module that references pytest without bundling it.
- `setuptools` ships as **8 files totalling 18 KB**. Removing it saves nothing measurable.
- `jinja2` has **zero occurrences** in the current TOC. The optional hidden-import warning noted in the original review is not reproducible.

## Resource measurements

### Processing (from source, committed fixture)

| Metric | Value |
|---|---|
| Fixture | `bmwm2csr_winton national 2026-06-06 22-26-36.ibt` (5.9 MB, 5 laps) |
| Import + analyze() wall time | 1.50 s |
| Full pipeline (analyze + report + summary) | 1.52 s |
| RSS after full pipeline | 90.4 MB |
| Delta RSS (memory consumed by processing) | 66.6 MB |
| Report HTML size | 371 KB |

### Frozen tray idle

| Metric | After 8s (settled, post-sqlite3 exclusion) |
|---|---|
| Working Set | 97.2 MB |
| CPU time consumed | 1.28 s |
| Threads | ~25 |

The previous build measured 120 MB working set after 15s. The reduction is partly from the sqlite3 exclusion and partly from a cleaner module collection.

**Interpretation for sim racing:** ~100 MB idle RAM is modest — iRacing itself uses 8–12 GB, and a modern sim-racing PC has 32+ GB. The ~1.3s of CPU at startup is the pandas/numpy import cost; after settling, idle CPU is unmeasurably low (event-driven watcher, no polling).

### Build artifacts

| Artifact | Size |
|---|---|
| dist/Tenths/ (portable folder) | 80.9 MB |
| dist/Tenths/Tenths.exe | 13.5 MB |
| installer/Output/TenthsSetup.exe | ~30 MB |

## Build evidence files

PyInstaller generates these in `build/Tenths/`. **`python installer/build.py` deletes and recreates `build/` on every run**, so copy anything you want to keep before rebuilding.

| File | Size | Contains |
|---|---|---|
| `Analysis-00.toc` | 399 KB | Full module dependency list |
| `xref-tenths.html` | 2.6 MB | Cross-reference: what imports what |
| `warn-tenths.txt` | 49 KB (318 lines) | Missing module warnings from PyInstaller |

The warn file contains only numpy internal missing-module warnings (e.g., `numpy.random.RandomState`). None are actionable or indicate a real runtime problem.
