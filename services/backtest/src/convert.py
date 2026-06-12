"""Shared value-conversion helpers for the backtest service."""

from typing import SupportsFloat, cast


def safe_float(val: object, default: float = 0.0) -> float:
    """Convert a loosely-typed value (JSONB, proto, Decimal) to float.

    Returns `default` for None, unparseable strings, and values that fail
    float conversion.
    """
    if val is None:
        return default
    if isinstance(val, (int, float)):
        return float(val)
    if isinstance(val, str):
        try:
            return float(val)
        except ValueError:
            return default
    if hasattr(val, "__float__"):
        try:
            return float(cast(SupportsFloat, val))
        except TypeError, ValueError:
            return default
    return default
