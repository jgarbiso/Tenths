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

The exact factor 2.23694 is used throughout. Older code used the rounded 2.237,
which differs by 3e-5 relative — below display rounding, but the precise value
is used here so conversions round-trip cleanly.
"""

MPS_TO_MPH = 2.23694
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
