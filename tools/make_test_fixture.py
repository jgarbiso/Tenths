"""
Build a committable test fixture from a real .ibt file.

Real telemetry is valuable for tests because it carries all the messiness that
synthetic data does not: sensor noise, imperfect lines, real braking traces.
It cannot be committed as-is for two reasons, both of which this tool fixes.

1. **Privacy.** An .ibt embeds the full driver list for the session: real names,
   iRacing customer IDs, abbreviations, initials and team names. Even "practice"
   sessions list everyone on the server (9-60 people). Every identity is
   replaced here, including the recording driver's, so nothing personal ships.

2. **Size.** A full session is 25-170MB, mostly channels the analyser never
   reads (283 channels, ~1100 bytes per sample). Keeping only the ~51 channels
   the analyser uses and a handful of laps takes a 52MB file to about 4-5MB.

Telemetry samples themselves are copied through unmodified, so the fixture is
genuinely real data for the laps it retains.

Usage:
    python tools/make_test_fixture.py <source.ibt> <dest.ibt> [--laps 4]
    python tools/make_test_fixture.py <source.ibt> <dest.ibt> --inspect
"""

import argparse
import os
import struct
import sys

import yaml

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tests"))

import irsdk  # noqa: E402
from synthetic_ibt import write_ibt  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tenths.analyzer import COACHING_CHANNELS  # noqa: E402

# Channels the analyser reads, plus SessionTime for sample-rate derivation
NEEDED = set(COACHING_CHANNELS) | {"SessionTime", "SessionTick"}

# Identity fields replaced wherever they appear in the session info
ANON_DRIVER = {
    "UserName": "Test Driver",
    "AbbrevName": "Driver, Test",
    "Initials": "TD",
    "TeamName": "Test Team",
    "UserID": 0,
    "CarNumber": "0",
    "CarNumberRaw": 0,
    "IRating": 1500,
    "LicString": "B 3.00",
    "LicLevel": 12,
    "LicSubLevel": 300,
    "ClubName": "Testland",
    "ClubID": 0,
    "DivisionName": "Division 1",
}


def valid_lap_numbers(path):
    """Lap numbers the analyser considers valid, in order."""
    from tenths.analyzer import parse_ibt, get_valid_laps
    df, _rate, _veh, _ven = parse_ibt(path)
    return sorted(get_valid_laps(df))


def read_session_info(path):
    with open(path, "rb") as f:
        header = f.read(112)
        _, info_len, info_offset = struct.unpack_from("iii", header, 12)
        f.seek(info_offset)
        raw = f.read(info_len).decode("latin-1").rstrip("\x00")
    return yaml.safe_load(raw)


def anonymize_session_info(info, keep_car_idx):
    """Strip every identity, keeping only an anonymised entry for the player.

    Also drops sections the analyser never reads and which can carry extra
    personal or setup detail: QualifyResultsInfo, CameraInfo, RadioInfo,
    SplitTimeInfo and CarSetup.
    """
    out = {k: v for k, v in info.items()
           if k in ("WeekendInfo", "SessionInfo", "DriverInfo")}

    di = dict(out.get("DriverInfo", {}))
    drivers = di.get("Drivers", []) or []
    player = None
    for d in drivers:
        if d.get("CarIdx") == keep_car_idx:
            player = dict(d)
            break
    if player is None and drivers:
        player = dict(drivers[0])
    if player is None:
        player = {"CarIdx": keep_car_idx}

    for field, value in ANON_DRIVER.items():
        if field in player or field in ("UserName", "UserID"):
            player[field] = value
    di["Drivers"] = [player]
    di["DriverUserID"] = 0
    out["DriverInfo"] = di

    # Session results reference CarIdx values for cars that no longer exist
    si = dict(out.get("SessionInfo", {}) or {})
    sessions = []
    for s in (si.get("Sessions") or []):
        s = dict(s)
        for key in ("ResultsPositions", "ResultsFastestLap"):
            s.pop(key, None)
        sessions.append(s)
    if sessions:
        si["Sessions"] = sessions
        out["SessionInfo"] = si

    return out


def audit_for_identities(info, allowed=("Test Driver", "Driver, Test", "TD", "Test Team")):
    """Return any suspicious identity-like values left in the info block."""
    findings = []

    def walk(obj, path=""):
        if isinstance(obj, dict):
            for k, v in obj.items():
                if k in ("UserName", "AbbrevName", "Initials", "TeamName") and v not in allowed:
                    findings.append(f"{path}.{k} = {v!r}")
                if k in ("UserID", "DriverUserID") and v not in (0, None):
                    findings.append(f"{path}.{k} = {v!r}")
                walk(v, f"{path}.{k}")
        elif isinstance(obj, list):
            for i, v in enumerate(obj):
                walk(v, f"{path}[{i}]")

    walk(info)
    return findings


def build(source, dest, keep_laps=4, verbose=True):
    info = read_session_info(source)
    car_idx = info.get("DriverInfo", {}).get("DriverCarIdx", 0)
    original_drivers = len(info.get("DriverInfo", {}).get("Drivers", []) or [])

    ibt = irsdk.IBT()
    ibt.open(source)
    try:
        tick_rate = ibt._header.tick_rate
        names = [n for n in ibt.var_headers_names if n in NEEDED]
        laps = ibt.get_all("Lap")

        # Ask the analyser itself which laps are valid, so no fixture slot is
        # wasted on an out-lap or a lap the pipeline would discard anyway.
        chosen = valid_lap_numbers(source)[:keep_laps]
        if len(chosen) < 3:
            raise SystemExit(
                f"Source yields only {len(chosen)} valid laps; need at least 3 "
                "for corner variance")
        unique = sorted(set(laps))

        keep = set(chosen)
        indices = [i for i, lap in enumerate(laps) if lap in keep]

        channel_data = {}
        specs = []
        for name in names:
            vh = ibt._var_headers_dict[name]
            if vh.count != 1:
                continue  # scalar channels only
            specs.append((name, vh.type, vh.unit))
            channel_data[name] = ibt.get_all(name)
    finally:
        ibt.close()

    rows = [{name: channel_data[name][i] for name, _, _ in specs} for i in indices]

    clean_info = anonymize_session_info(info, car_idx)
    leftovers = audit_for_identities(clean_info)
    if leftovers:
        raise SystemExit(f"Refusing to write: identity data remains: {leftovers}")

    buf_len = write_ibt(dest, specs, rows, clean_info,
                        tick_rate=tick_rate, lap_count=len(chosen))

    if verbose:
        src_mb = os.path.getsize(source) / 1024 / 1024
        dst_mb = os.path.getsize(dest) / 1024 / 1024
        print(f"source : {os.path.basename(source)}  {src_mb:.1f}MB")
        print(f"         drivers listed: {original_drivers}  laps available: {len(unique)}")
        print(f"fixture: {os.path.basename(dest)}  {dst_mb:.1f}MB  ({src_mb / dst_mb:.1f}x smaller)")
        print(f"         laps kept: {chosen}   samples: {len(rows)}   rate: {tick_rate}Hz")
        print(f"         channels: {len(specs)}  bytes/sample: {buf_len}")
        print(f"         identities: all replaced (audit clean)")
    return dest


def inspect(path):
    info = read_session_info(path)
    drivers = info.get("DriverInfo", {}).get("Drivers", []) or []
    print(f"{os.path.basename(path)}")
    print(f"  sections: {list(info.keys())}")
    print(f"  drivers listed: {len(drivers)}")
    for d in drivers[:10]:
        print(f"    CarIdx={d.get('CarIdx')} name={d.get('UserName')!r} "
              f"UserID={d.get('UserID')} team={d.get('TeamName')!r}")
    findings = audit_for_identities(info)
    print(f"  identity audit: {'CLEAN' if not findings else findings[:10]}")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("source")
    ap.add_argument("dest", nargs="?")
    ap.add_argument("--laps", type=int, default=4)
    ap.add_argument("--inspect", action="store_true",
                    help="report identities in a file instead of building")
    args = ap.parse_args()

    if args.inspect:
        inspect(args.source)
        return
    if not args.dest:
        ap.error("dest is required unless --inspect is given")
    os.makedirs(os.path.dirname(os.path.abspath(args.dest)), exist_ok=True)
    build(args.source, args.dest, keep_laps=args.laps)


if __name__ == "__main__":
    main()
