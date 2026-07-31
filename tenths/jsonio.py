"""
JSON normalisation for Tenths data contracts.

pandas and NumPy values leak out of the analyser everywhere: `df['Speed'].min()`
returns `numpy.float64`, a comparison of two such values returns `numpy.bool_`.
Neither is JSON-serialisable, and the previous `json.dump(..., default=str)`
turned them into strings instead of failing.

That silently produced `"is_new_pb": "False"` in session summaries. In
JavaScript a non-empty string is truthy, so a non-PB session displayed a
"New PB" badge. Stringifying unknown types hides exactly this class of bug, so
values are converted properly here and unsupported types now raise.

Usage:
    from tenths.jsonio import to_jsonable, dump_json, dumps_json
"""

import json
import math

try:
    import numpy as np
except ImportError:  # pragma: no cover - numpy is a hard dependency in practice
    np = None


def to_jsonable(value):
    """Recursively convert a value into JSON-native Python types.

    Handles NumPy scalars and arrays, pandas-style objects exposing `.item()`
    or `.tolist()`, dicts, lists, tuples and sets. Non-finite floats become
    None, because `NaN` and `Infinity` are not valid JSON.

    Raises TypeError for anything it cannot convert, so a new unsupported type
    surfaces during development rather than being stringified into a report.
    """
    # Exact JSON primitives first. bool must precede int (bool is an int).
    if value is None or isinstance(value, (str, bool)):
        return value

    if isinstance(value, int):
        return int(value)

    if isinstance(value, float):
        return value if math.isfinite(value) else None

    if isinstance(value, dict):
        return {str(key): to_jsonable(item) for key, item in value.items()}

    if isinstance(value, (list, tuple, set, frozenset)):
        return [to_jsonable(item) for item in value]

    if np is not None:
        if isinstance(value, np.bool_):
            return bool(value)
        if isinstance(value, np.integer):
            return int(value)
        if isinstance(value, np.floating):
            number = float(value)
            return number if math.isfinite(number) else None
        if isinstance(value, np.ndarray):
            return [to_jsonable(item) for item in value.tolist()]
        if isinstance(value, np.generic):
            return to_jsonable(value.item())

    # pandas scalars / other array-likes that expose the NumPy protocol
    item = getattr(value, "item", None)
    if callable(item):
        try:
            return to_jsonable(item())
        except (ValueError, TypeError):
            pass

    tolist = getattr(value, "tolist", None)
    if callable(tolist):
        try:
            return to_jsonable(tolist())
        except (ValueError, TypeError):
            pass

    raise TypeError(
        f"{type(value).__name__} is not JSON-serialisable. Add explicit handling "
        f"in tenths.jsonio.to_jsonable rather than letting it become a string."
    )


def dumps_json(data, **kwargs):
    """json.dumps with Tenths normalisation applied first."""
    return json.dumps(to_jsonable(data), **kwargs)


def dump_json(data, file_obj, **kwargs):
    """json.dump with Tenths normalisation applied first."""
    return json.dump(to_jsonable(data), file_obj, **kwargs)
