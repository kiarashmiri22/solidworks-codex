from math import isfinite

_TO_METERS = {
    "mm": 0.001,
    "cm": 0.01,
    "m": 1.0,
    "in": 0.0254,
    "ft": 0.3048,
}


def to_meters(value: float, unit: str) -> float:
    if unit not in _TO_METERS:
        raise ValueError(f"Unsupported length unit {unit!r}; use mm, cm, m, in, or ft.")
    value = float(value)
    if not isfinite(value):
        raise ValueError("Dimensions must be finite numbers.")
    return value * _TO_METERS[unit]


def positive_meters(value: float, unit: str, label: str) -> float:
    meters = to_meters(value, unit)
    if meters <= 0:
        raise ValueError(f"{label} must be greater than zero.")
    return meters
