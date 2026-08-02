"""Shared series statistics for the metrics, weight methods, and filters (one definition each)."""

from __future__ import annotations

import numpy as np

from llamatrade_runtime.types import Bar


def trailing_return(bars: list[Bar], lookback: int) -> float:
    """Percent return over ``lookback`` bars (base is bars[-(lookback+1)]); 0.0 on short
    history or a non-positive base.

    ``lookback`` counts intervals, so it spans ``lookback + 1`` bars and agrees with the
    ``momentum`` indicator (``close[-1] - close[-(lookback+1)]``) on the same lookback.
    """
    if lookback < 1 or len(bars) < lookback + 1:
        return 0.0
    start = bars[-(lookback + 1)].close
    end = bars[-1].close
    return (end - start) / start if start > 0 else 0.0


def return_volatility(bars: list[Bar], lookback: int | None = None) -> float:
    """Raw std of bar-to-bar returns over the (optional) lookback window; 0.0 if fewer than 2 bars."""
    series = bars[-lookback:] if lookback else bars
    if len(series) < 2:
        return 0.0
    closes = np.array([b.close for b in series], dtype=np.float64)
    returns = np.diff(closes) / closes[:-1]
    return float(np.std(returns)) if len(returns) > 0 else 0.0


def average_dollar_volume(bars: list[Bar], lookback: int | None = None) -> float:
    """Mean dollar volume (close × volume) over the (optional) lookback window; 0.0 if empty."""
    series = bars[-lookback:] if lookback else bars
    if not series:
        return 0.0
    return sum(b.close * b.volume for b in series) / len(series)
