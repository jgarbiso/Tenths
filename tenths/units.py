"""
Unit conversion helpers
========================
All internal data is SI; convert only at display time.

Internal (pipeline, JSON summaries):
    speed        m/s
    temperature  °C
    distance     metres

Display (report HTML, notes, CLI):
    speed        mph (imperial, default) or km/h (metric)
    temperature  °F (imperial, default) or °C (metric)
    distance     miles (imperial, default) or km (metric)

The factor is deliberately 2.237, matching what the analyzer used inline before
speeds moved to SI. The physically exact value is 2.2369362920544; adopting it
here would shift every displayed speed by ~3e-5 relative, which is invisible
after display rounding but would mean this refactor changed output as well as
structure. Correcting the constant is tracked separately in POST_MVP.md so that
any resulting change is attributable to that decision rather than to this one.
"""

MPS_TO_MPH = 2.237
MPS_TO_KPH = 3.6
METRES_PER_MILE = 1609.344


def mps_to_mph(mps):
    """Metres per second to miles per hour."""
    return mps * MPS_TO_MPH


def mps_to_kph(mps):
    """Metres per second to kilometres per hour."""
    return mps * MPS_TO_KPH


def mph_to_mps(mph):
    """Miles per hour to metres per second."""
    return mph / MPS_TO_MPH


def kph_to_mps(kph):
    """Kilometres per hour to metres per second."""
    return kph / MPS_TO_KPH


def celsius_to_fahrenheit(c):
    """Celsius to Fahrenheit."""
    return c * 9 / 5 + 32


def fahrenheit_to_celsius(f):
    """Fahrenheit to Celsius."""
    return (f - 32) * 5 / 9


def metres_to_miles(m):
    """Metres to miles."""
    return m / METRES_PER_MILE


def metres_to_km(m):
    """Metres to kilometres."""
    return m / 1000.0


def speed_display(mps, metric=False):
    """Convert m/s to display speed with label.

    Returns (value, label).
    """
    if metric:
        return mps * MPS_TO_KPH, "km/h"
    return mps * MPS_TO_MPH, "mph"


def temp_display(celsius, metric=False):
    """Convert °C to display temperature with label.

    Returns (value, label).
    """
    if metric:
        return celsius, "°C"
    return celsius * 9 / 5 + 32, "°F"


def distance_display(metres, metric=False):
    """Convert metres to display distance with label.

    Returns (value, label).
    """
    if metric:
        return metres / 1000.0, "km"
    return metres / METRES_PER_MILE, "mi"


# ── Analyzer output conversion ────────────────────────────────────────────────

# Speed keys carrying m/s from the analyzer, grouped by the rounding consumers
# previously received. Apex metrics arrived pre-rounded to 1dp in mph; raw traces
# and lap maxima arrived unrounded. Preserving that split keeps generated reports
# and notes numerically identical to before the SI refactor.
_APEX_SPEED_KEYS_1DP = (
    'avg_apex_mph', 'std_apex_mph',
    'spread_limit_mph', 'over_braking_limit_mph', 'apex_std_limit_mph',
    'min_speed_best_mph', 'min_speed_worst_mph',
    'min_speed_typical_low_mph', 'min_speed_typical_high_mph',
    'min_speed_spread_mph', 'over_braking_mph',
)


def to_display_units(data, metric=False):
    """Return a copy of an `analyzer.analyze()` dict in display units.

    The analyzer emits SI (m/s, °C). Consumers that render values — the HTML
    report, the markdown notes, the track-map generator — call this once and then
    work entirely in display units, keeping the historical `*_mph` key names. The
    input dict is not mutated.
    """
    def spd(value, ndigits=None):
        if value is None:
            return None
        converted, _ = speed_display(value, metric=metric)
        return converted if ndigits is None else round(converted, ndigits)

    def tmp(value):
        if not isinstance(value, (int, float)):
            return value
        converted, _ = temp_display(value, metric=metric)
        return converted

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
        converted = dict(a)
        for key in _APEX_SPEED_KEYS_1DP:
            if key in converted:
                converted[key] = spd(converted[key], 1)
        converted['per_lap_apex'] = [
            {**p, 'apex_speed_mph': spd(p.get('apex_speed_mph'), 1)}
            for p in a.get('per_lap_apex', [])
        ]
        apex_out.append(converted)
    out['apex_consistency'] = apex_out

    out['gps_trace'] = [
        {**p, 'speed_mph': spd(p.get('speed_mph'))}
        for p in data.get('gps_trace', [])
    ]
    out['gps_traces'] = {
        lap: [{**p, 'speed_mph': spd(p.get('speed_mph'))} for p in trace]
        for lap, trace in (data.get('gps_traces') or {}).items()
    }

    # Speeds live in the nested per-zone `entries` list, not on the zone itself.
    out['per_lap_brake_points'] = [
        {**b, 'entries': [
            {**e, 'speed_mph': spd(e.get('speed_mph'))}
            for e in b.get('entries', [])
        ]}
        for b in data.get('per_lap_brake_points', [])
    ]

    tire_temps = {}
    for corner, values in (data.get('tire_temps') or {}).items():
        conv = {k: tmp(v) for k, v in values.items()}
        # Average the converted corner temperatures rather than converting the
        # averaged value. Both are mathematically equal, but the original code
        # used this order and reproducing it keeps results bit-identical.
        parts = [conv.get(k) for k in ('inner', 'mid', 'outer')]
        if all(isinstance(p, (int, float)) for p in parts):
            conv['avg'] = sum(parts) / 3
        tire_temps[corner] = conv
    out['tire_temps'] = tire_temps

    return out
