"""Tests for the shared series-statistics primitives."""

from datetime import UTC, datetime, timedelta

import numpy as np
import pytest

from llamatrade_runtime import Bar
from llamatrade_runtime.evaluation.statistics import (
    average_dollar_volume,
    return_volatility,
    trailing_return,
)


def _bars(closes: list[float]) -> list[Bar]:
    t = datetime(2024, 1, 1, tzinfo=UTC)
    return [
        Bar(timestamp=t + timedelta(days=i), open=c, high=c, low=c, close=c, volume=1)
        for i, c in enumerate(closes)
    ]


def _bars_v(rows: list[tuple[float, int]]) -> list[Bar]:
    """Bars from (close, volume) pairs."""
    t = datetime(2024, 1, 1, tzinfo=UTC)
    return [
        Bar(timestamp=t + timedelta(days=i), open=c, high=c, low=c, close=c, volume=v)
        for i, (c, v) in enumerate(rows)
    ]


def test_trailing_return_basic() -> None:
    bars = _bars([100, 105, 110])  # lookback 2 -> from bars[-2]=105 to bars[-1]=110
    assert trailing_return(bars, 2) == pytest.approx((110 - 105) / 105)


def test_trailing_return_insufficient_or_degenerate_is_zero() -> None:
    assert trailing_return(_bars([100, 110]), 5) == 0.0  # not enough history
    assert trailing_return([], 3) == 0.0
    assert trailing_return(_bars([100, 110]), 0) == 0.0  # lookback < 1


def test_trailing_return_nonpositive_base_is_zero() -> None:
    assert trailing_return(_bars([50, 0, 110]), 2) == 0.0  # base = bars[-2] = 0


def test_return_volatility_zero_when_flat() -> None:
    assert return_volatility(_bars([100, 100, 100, 100])) == 0.0


def test_return_volatility_matches_std_of_returns() -> None:
    closes = [100, 102, 101, 105, 103]
    arr = np.array(closes, dtype=float)
    expected = float(np.std(np.diff(arr) / arr[:-1]))
    assert return_volatility(_bars(closes)) == pytest.approx(expected)


def test_return_volatility_lookback_slices_to_recent_window() -> None:
    closes = [100, 200, 101, 102, 103]  # violent early, calm last 3
    arr = np.array([101, 102, 103], dtype=float)
    expected = float(np.std(np.diff(arr) / arr[:-1]))
    assert return_volatility(_bars(closes), 3) == pytest.approx(expected)


def test_return_volatility_insufficient_is_zero() -> None:
    assert return_volatility(_bars([100])) == 0.0
    assert return_volatility([]) == 0.0


def test_average_dollar_volume_basic() -> None:
    bars = _bars_v([(10.0, 100), (10.0, 200), (10.0, 300)])
    # mean of close*volume = (1000 + 2000 + 3000) / 3 = 2000
    assert average_dollar_volume(bars) == pytest.approx(2000.0)


def test_average_dollar_volume_lookback_slices() -> None:
    bars = _bars_v([(10.0, 9999), (10.0, 100), (10.0, 200), (10.0, 300)])
    # last 3 only: (1000 + 2000 + 3000) / 3 = 2000 (the huge first bar is excluded)
    assert average_dollar_volume(bars, 3) == pytest.approx(2000.0)


def test_average_dollar_volume_dollar_weights_not_share_count() -> None:
    # A: high price, low shares. B: low price, high shares. A has more *dollar* volume.
    a = average_dollar_volume(_bars_v([(500.0, 100), (500.0, 100)]))  # 50_000
    b = average_dollar_volume(_bars_v([(5.0, 5000), (5.0, 5000)]))  # 25_000
    assert a > b


def test_average_dollar_volume_short_history_averages_available() -> None:
    bars = _bars_v([(10.0, 100), (10.0, 200)])
    # lookback 5 but only 2 bars → average the 2 present: (1000 + 2000) / 2 = 1500
    assert average_dollar_volume(bars, 5) == pytest.approx(1500.0)


def test_average_dollar_volume_empty_is_zero() -> None:
    assert average_dollar_volume([]) == 0.0
