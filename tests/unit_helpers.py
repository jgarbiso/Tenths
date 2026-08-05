"""
Shared test helpers for the SI-internal / display-units split.

`analyzer.analyze()` and its internals store SI (m/s, °C). Tests assert the
coaching figures a driver actually sees, which are mph, so results are converted
at the assertion boundary. This keeps each assertion's original meaning while the
pipeline carries SI.
"""

from tenths.units import mps_to_mph

# Speed-valued keys in an apex-consistency result. Names retain the historical
# `_mph` suffix; the analyzer stores m/s behind them.
APEX_SPEED_KEYS = (
    'avg_apex_mph', 'std_apex_mph',
    'spread_limit_mph', 'over_braking_limit_mph', 'apex_std_limit_mph',
    'min_speed_best_mph', 'min_speed_worst_mph',
    'min_speed_typical_low_mph', 'min_speed_typical_high_mph',
    'min_speed_spread_mph', 'over_braking_mph',
)


def apex_result_to_mph(result):
    """Convert one apex-consistency result dict from SI to mph."""
    out = dict(result)
    for key in APEX_SPEED_KEYS:
        if out.get(key) is not None:
            out[key] = mps_to_mph(out[key])
    out['per_lap_apex'] = [
        {**p, 'apex_speed_mph': mps_to_mph(p['apex_speed_mph'])}
        for p in result.get('per_lap_apex', [])
    ]
    return out


def apex_results_to_mph(results):
    """Convert a list of apex-consistency results from SI to mph."""
    return [apex_result_to_mph(r) for r in results]


def zones_to_mph(zones):
    """Convert braking-zone entry/min speeds from SI to mph."""
    out = []
    for z in zones:
        z2 = dict(z)
        for key in ('entry_mph', 'min_mph'):
            if z2.get(key) is not None:
                z2[key] = mps_to_mph(z2[key])
        out.append(z2)
    return out


def to_si_fixture(data):
    """Convert an analyzer-shaped fixture authored in mph/°F into SI.

    Fixtures stand in for `analyzer.analyze()` output, which is SI. Authoring
    them with readable mph literals and converting here keeps the fixture legible
    while feeding consumers the units they now expect. Inverse of
    `tenths.units.to_display_units`.
    """
    from tenths.units import fahrenheit_to_celsius, mph_to_mps

    def spd(v):
        return None if v is None else mph_to_mps(v)

    out = dict(data)

    out['lap_results'] = [
        {**r, 'max_speed_mph': spd(r.get('max_speed_mph'))}
        for r in data.get('lap_results', [])
    ]
    out['braking_zones'] = [
        {**z, 'entry_mph': spd(z.get('entry_mph')), 'min_mph': spd(z.get('min_mph'))}
        for z in data.get('braking_zones', [])
    ]

    apex_out = []
    for a in data.get('apex_consistency', []):
        conv = dict(a)
        for key in APEX_SPEED_KEYS:
            if conv.get(key) is not None:
                conv[key] = spd(conv[key])
        conv['per_lap_apex'] = [
            {**p, 'apex_speed_mph': spd(p.get('apex_speed_mph'))}
            for p in a.get('per_lap_apex', [])
        ]
        apex_out.append(conv)
    out['apex_consistency'] = apex_out

    out['gps_trace'] = [
        {**p, 'speed_mph': spd(p.get('speed_mph'))}
        for p in data.get('gps_trace', [])
    ]
    out['gps_traces'] = {
        lap: [{**p, 'speed_mph': spd(p.get('speed_mph'))} for p in trace]
        for lap, trace in (data.get('gps_traces') or {}).items()
    }
    out['per_lap_brake_points'] = [
        {**b, 'entries': [
            {**e, 'speed_mph': spd(e.get('speed_mph'))}
            for e in b.get('entries', [])
        ]}
        for b in data.get('per_lap_brake_points', [])
    ]
    out['tire_temps'] = {
        corner: {
            k: (fahrenheit_to_celsius(v) if isinstance(v, (int, float)) else v)
            for k, v in values.items()
        }
        for corner, values in (data.get('tire_temps') or {}).items()
    }
    return out
