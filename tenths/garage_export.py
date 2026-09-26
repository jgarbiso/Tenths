"""
iRacing garage setup exports (.htm) — reading them, and the reference-setup view.

The garage's File Actions > Export writes a readable .htm copy of the loaded setup,
exactly as the garage displays it (the driver's display units). It is the only
readable form of an iRacing setup: .sto files are encrypted. Exporting iRacing's
Official Setups gives free, car-specific reference setups (baseline, sprint and
endurance at each downforce level, wet, fixed); exporting the driver's own setups
gives an exact record of what was saved.

FORMAT
    After "Tire type:", every setting is written as `Label:<U>value</U>`. Section
    headings are garbled by iRacing (truncated to e.g. "ng:" or "ap:") and help
    text is interleaved, so headings are ignored. Instead, the labelled values are
    matched IN ORDER against the CarSetup keys of a recorded session of the same
    car: on 2026-09-26 all 71 Mustang GT3 values lined up with the 71 CarSetup
    leaves. Every label is checked against its key (normalised: "ARB blades" <->
    ArbBlades, "%F WtDist" <-> FWtdist); any mismatch refuses the file rather than
    guessing, because a misaligned value would be silently wrong.

OWN vs OFFICIAL
    Each export is named after its FILE (minus a trailing " export"), not the setup
    name inside it: an official setup keeps its internal name even when the driver
    saves a modified copy under the same name. On 2026-09-26 iRacing's official
    Le Mans setup (exported as lemans_ir.htm) and the driver's own lemans.sto both
    exported as setup "lemans" but differed in 12 settings. An export whose file
    name matches a .sto in the same folder is the driver's own setup; anything
    else is treated as an iRacing Official Setup.
"""

import json
import os
import re
from html import unescape

from tenths import config
from tenths.applog import get_logger

log = get_logger(__name__)

_LABELLED = re.compile(r'([A-Za-z%][^<>:]*?):<U>([^<]*)</U>')


class ExportFormatError(ValueError):
    """The export does not line up with the car's setup keys."""


def _norm(text):
    return re.sub(r"[^a-z0-9]", "", str(text).lower())


def parse_export(path):
    """{"setup", "track", "values": [(label, value), ...]} from a garage .htm export."""
    with open(path, encoding="utf-8", errors="replace") as f:
        text = f.read()
    try:
        return parse_export_text(text)
    except ExportFormatError as exc:
        raise ExportFormatError(f"{os.path.basename(path)}: {exc}") from exc


def parse_export_text(text):
    """parse_export for the file's contents."""
    head = re.search(r"setup:\s*(.*?)<br>\s*track:\s*(.*?)</H2>", text, re.S)
    try:
        body = text[text.index("Tire type:"):text.index("If the setup fails tech")]
    except ValueError as exc:
        raise ExportFormatError("not a garage setup export") from exc
    name = unescape(head.group(1)).strip().strip("<>").strip() if head else ""
    track = unescape(head.group(2)).strip() if head else ""
    values = [(label.strip(), unescape(value).strip()) for label, value in _LABELLED.findall(body)]
    return {"setup": name, "track": track, "values": values}


def align(values, setup_keys):
    """Map export values onto CarSetup keys, checking every label.

    `setup_keys` are the dotted keys of a flattened CarSetup of the same car, in
    YAML order (setup_notebook.flatten_setup). Keys without a section (e.g.
    UpdateCount) never appear in exports and are skipped.
    """
    keys = [k for k in setup_keys if "." in k]
    if len(keys) != len(values):
        raise ExportFormatError(f"{len(values)} values for {len(keys)} setup keys")
    mapped = {}
    for key, (label, value) in zip(keys, values):
        if _norm(key.rsplit(".", 1)[-1]) != _norm(label):
            raise ExportFormatError(f"label {label!r} does not match {key}")
        mapped[key] = value
    return mapped


def latest_session(car_slug, root=None):
    """(car display name, setup name) of the car's most recent notebook session."""
    from tenths.setup_notebook import load_notebook
    folder = os.path.join(root or config.NOTEBOOK_DIR, car_slug)
    latest = None
    if os.path.isdir(folder):
        for name in os.listdir(folder):
            if name.endswith(".json") and name not in ("limits.json", "reference_setups.json"):
                for entry in load_notebook(os.path.join(folder, name)).get("entries", []):
                    if latest is None or entry.get("recorded", "") > latest.get("recorded", ""):
                        latest = entry
    if not latest:
        return car_slug, None
    return latest.get("car") or car_slug, os.path.splitext(latest.get("setup_name", ""))[0] or None


def setup_keys_for_car(car_slug, root=None):
    """CarSetup keys (YAML order) from the car's notebook, or [] if none recorded.

    Every session in a car's notebook stores `settings` and `computed`, but not
    the readings (hot pressure, temps, tread) that exports also contain, so the
    full key order is re-read from a recorded .ibt.
    """
    from tenths.analyzer import read_session_yaml
    from tenths.setup_notebook import flatten_setup, load_notebook
    folder = os.path.join(root or config.NOTEBOOK_DIR, car_slug)
    if not os.path.isdir(folder):
        return []
    for name in sorted(os.listdir(folder)):
        if not name.endswith(".json") or name in ("limits.json", "reference_setups.json"):
            continue
        for entry in reversed(load_notebook(os.path.join(folder, name)).get("entries", [])):
            for base in (config.ARCHIVE_DIR, config.TELEMETRY_ROOT):
                path = os.path.join(base, entry.get("id", ""))
                if os.path.isfile(path):
                    car_setup = read_session_yaml(path).get("CarSetup")
                    if car_setup:
                        return list(flatten_setup(car_setup))
    return []


def load_exports(setups_dir, setup_keys):
    """Parse and align every .htm export in a car's setups folder.

    Returns (setups, skipped): setups is a list of {"file", "setup" (from the file
    name), "saved_as" (name inside the export), "track", "source": "own"|"official",
    "values": {key: value}}, one per distinct name (the newest export wins);
    skipped lists (file, reason).
    """
    own_names = {os.path.splitext(f)[0].lower() for f in os.listdir(setups_dir)
                 if f.lower().endswith(".sto")}
    files = sorted((f for f in os.listdir(setups_dir) if f.lower().endswith(".htm")),
                   key=lambda f: os.path.getmtime(os.path.join(setups_dir, f)))
    by_name, skipped = {}, []
    for name in files:
        path = os.path.join(setups_dir, name)
        try:
            parsed = parse_export(path)
            values = align(parsed["values"], setup_keys)
        except (OSError, ExportFormatError) as exc:
            skipped.append((name, str(exc)))
            continue
        setup = re.sub(r"\s+export$", "", os.path.splitext(name)[0], flags=re.I)
        by_name[setup.lower()] = {
            "file": name,
            "setup": setup,
            "saved_as": parsed["setup"],
            "track": parsed["track"],
            "source": "own" if setup.lower() in own_names else "official",
            "values": values,
        }
    return list(by_name.values()), skipped


# ── Reference view ────────────────────────────────────────────────────────────

def _comparable_settings(keys):
    """Keys worth comparing: real settings, not readings, cosmetics or computed values."""
    from tenths.setup_notebook import classify_setup
    settings, _ = classify_setup({k: "" for k in keys})
    return [k for k in keys if k in settings]


def render_reference(car, setups, current=None):
    """Markdown view. `current` is the driver's current setup name (their latest
    session); it is listed first and is what the 'Matches' column compares."""
    own = sorted((s for s in setups if s["source"] == "own"),
                 key=lambda s: (s["setup"].lower() != (current or "").lower(), s["setup"]))
    official = sorted((s for s in setups if s["source"] == "official"), key=lambda s: s["setup"])
    if not setups:
        return f"# Reference setups — {car}\n\nNo garage exports found.\n"
    keys = _comparable_settings(list(setups[0]["values"]))
    out = [
        f"# Reference setups — {car}",
        "",
        "_Generated by Tenths from garage exports (File Actions > Export) in the car's "
        "iRacing setups folder. Values are exactly as the garage shows them. Rebuild with "
        "`tenths notebook references <car>`._",
        "",
        f"{len(official)} iRacing Official Setups, {len(own)} of your own. Official setups "
        "are iRacing's starting points for this car — sprint vs endurance and each "
        "downforce level — not answers for your driving. Use them to see which values "
        "iRacing's engineers consider normal, and as test candidates.",
        "",
    ]
    if own and official:
        ref = own[0]
        out += ["## Your setups against iRacing's range", "",
                f"A value no official setup uses is marked **outside**. The last column counts "
                f"official setups with exactly the value in **{ref['setup']}**"
                f"{' (your current setup)' if current and ref['setup'].lower() == current.lower() else ''}.",
                ""]
        head = ("| Setting | " + " | ".join(s["setup"] for s in own)
                + f" | Official values | Officials matching {ref['setup']} |")
        out += [head, "|---|" + "---|" * len(own) + "---|---|"]
        for key in keys:
            off_vals = [s["values"].get(key) for s in official]
            distinct = sorted({v for v in off_vals if v is not None}, key=_sort_key)
            cells = []
            for s in own:
                v = s["values"].get(key)
                cells.append(f"**{v}** (outside)" if v not in distinct else str(v))
            matches = [s["setup"] for s in official if s["values"].get(key) == ref["values"].get(key)]
            section, _, name = key.rpartition(".")
            out.append(f"| {section.split('.')[-1]} {name} | " + " | ".join(cells)
                       + f" | {' / '.join(distinct)} | {len(matches)} of {len(official)} |")
        out.append("")
    out += ["## All setups", "",
            "| Setting | " + " | ".join(s["setup"] + (" (yours)" if s["source"] == "own" else "")
                                      for s in own + official) + " |",
            "|---|" + "---|" * len(own + official)]
    for key in keys:
        section, _, name = key.rpartition(".")
        out.append(f"| {section.split('.')[-1]} {name} | "
                   + " | ".join(str(s["values"].get(key, "—")) for s in own + official) + " |")
    return "\n".join(out) + "\n"


def _sort_key(value):
    match = re.match(r"\s*([-+]?\d+(?:\.\d+)?)", str(value))
    return (0, float(match.group(1)), str(value)) if match else (1, 0.0, str(value))


def build_references(car_slug, setups_dir=None, root=None):
    """Import a car's garage exports into <notebook>/<car>/reference_setups.{json,md}.

    Returns (md_path, setups, skipped). Raises ExportFormatError if the car has no
    recorded session to take the setup-key order from.
    """
    from tenths.jsonio import to_jsonable
    root = root or config.NOTEBOOK_DIR
    setups_dir = setups_dir or os.path.join(config.iracing_dir(), "setups", car_slug)
    if not os.path.isdir(setups_dir):
        raise ExportFormatError(f"no setups folder: {setups_dir}")
    keys = setup_keys_for_car(car_slug, root)
    if not keys:
        raise ExportFormatError(f"no recorded session for {car_slug}; drive one first so the "
                                "setup layout is known")
    setups, skipped = load_exports(setups_dir, keys)
    folder = os.path.join(root, car_slug)
    os.makedirs(folder, exist_ok=True)
    car_name, current = latest_session(car_slug, root)
    with open(os.path.join(folder, "reference_setups.json"), "w", encoding="utf-8") as f:
        json.dump(to_jsonable({"setups": setups, "skipped": skipped}), f, indent=1)
    md_path = os.path.join(folder, "reference_setups.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(render_reference(car_name, setups, current))
    return md_path, setups, skipped
