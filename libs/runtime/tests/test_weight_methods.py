"""Tests for the covariance-based weight methods and market-cap rejection."""

from datetime import UTC, datetime, timedelta

import numpy as np
import pytest

from llamatrade_dsl import parse_strategy, validate_strategy
from llamatrade_runtime import compile_strategy
from llamatrade_runtime.types import Bar


def _feed(sexpr: str, closes: dict[str, list[float]]):
    """Compile, feed parallel close series, return final allocation weights."""
    compiled = compile_strategy(parse_strategy(sexpr))
    n = len(next(iter(closes.values())))
    start = datetime(2024, 1, 1, tzinfo=UTC)
    alloc = {"weights": {}}
    for i in range(n):
        ts = start + timedelta(days=i)
        bars = {
            s: Bar(timestamp=ts, open=c[i], high=c[i], low=c[i], close=c[i], volume=1000)
            for s, c in closes.items()
        }
        alloc = compiled.compute_allocation(bars)
    return alloc["weights"]


def _price_series(vol: float, n: int, seed: int) -> list[float]:
    """A geometric random-walk price series with the given per-bar return volatility."""
    rng = np.random.default_rng(seed)
    returns = rng.normal(0.0, vol, n)
    return [float(p) for p in 100.0 * np.cumprod(1.0 + returns)]


def test_market_cap_method_is_rejected():
    sexpr = '(strategy "MC" (weight :method market-cap (asset AAA) (asset BBB)))'
    result = validate_strategy(parse_strategy(sexpr))
    assert result.valid is False
    assert any("market-cap" in str(e) for e in result.errors)


def test_min_variance_overweights_lower_variance_asset():
    # AAA low vol, BBB high vol, independent -> min-variance favors AAA.
    aaa = _price_series(vol=0.002, n=120, seed=1)
    bbb = _price_series(vol=0.030, n=120, seed=2)
    sexpr = '(strategy "MV" (weight :method min-variance :lookback 90 (asset AAA) (asset BBB)))'
    weights = _feed(sexpr, {"AAA": aaa, "BBB": bbb})
    assert weights["AAA"] > weights["BBB"]
    assert abs(sum(weights.values()) - 100.0) < 1e-6


def test_risk_parity_overweights_lower_vol_and_sums_to_100():
    aaa = _price_series(vol=0.004, n=120, seed=3)
    bbb = _price_series(vol=0.024, n=120, seed=4)
    sexpr = '(strategy "RP" (weight :method risk-parity :lookback 90 (asset AAA) (asset BBB)))'
    weights = _feed(sexpr, {"AAA": aaa, "BBB": bbb})
    # Equal risk contribution => the calmer asset carries a larger weight.
    assert weights["AAA"] > weights["BBB"]
    assert abs(sum(weights.values()) - 100.0) < 1e-6


def test_covariance_methods_fall_back_when_insufficient_history():
    # Only 2 bars (< 3) — min-variance must fall back without crashing.
    sexpr = '(strategy "MV" (weight :method min-variance (asset AAA) (asset BBB)))'
    weights = _feed(sexpr, {"AAA": [100.0, 101.0], "BBB": [50.0, 50.5]})
    assert weights == {} or abs(sum(weights.values()) - 100.0) < 1e-6


@pytest.mark.parametrize("method", ["min-variance", "risk-parity"])
def test_single_asset_gets_full_weight(method):
    sexpr = f'(strategy "Solo" (weight :method {method} (asset AAA)))'
    weights = _feed(sexpr, {"AAA": _price_series(vol=0.01, n=80, seed=5)})
    assert abs(weights.get("AAA", 0.0) - 100.0) < 1e-6


def _feed_ohlcv(sexpr: str, series: dict[str, list[tuple[float, int]]]):
    """Feed parallel (close, volume) series, return final allocation weights."""
    compiled = compile_strategy(parse_strategy(sexpr))
    n = len(next(iter(series.values())))
    start = datetime(2024, 1, 1, tzinfo=UTC)
    alloc = {"weights": {}}
    for i in range(n):
        ts = start + timedelta(days=i)
        bars = {}
        for s, rows in series.items():
            c, v = rows[i]
            bars[s] = Bar(timestamp=ts, open=c, high=c, low=c, close=c, volume=v)
        alloc = compiled.compute_allocation(bars)
    return alloc["weights"]


def test_inverse_vol_excludes_zero_variance_symbol():
    # BBB is flat (zero variance) → excluded (0 weight), not dominating via a σ=0.0001 floor.
    aaa = _price_series(vol=0.02, n=100, seed=11)
    bbb = [100.0] * 100
    sexpr = (
        '(strategy "IV" (weight :method inverse-volatility :lookback 90 (asset AAA) (asset BBB)))'
    )
    weights = _feed(sexpr, {"AAA": aaa, "BBB": bbb})
    assert weights["AAA"] == pytest.approx(100.0)
    assert weights["BBB"] == pytest.approx(0.0)


def test_inverse_vol_all_zero_variance_falls_back_to_equal():
    sexpr = (
        '(strategy "IV" (weight :method inverse-volatility :lookback 90 (asset AAA) (asset BBB)))'
    )
    weights = _feed(sexpr, {"AAA": [100.0] * 100, "BBB": [50.0] * 100})
    assert weights["AAA"] == pytest.approx(50.0)
    assert weights["BBB"] == pytest.approx(50.0)


def test_min_variance_fallback_excludes_zero_variance_symbol():
    # < 3 bars → _aligned_returns is None → inherits the corrected inverse-vol fallback.
    sexpr = '(strategy "MV" (weight :method min-variance (asset AAA) (asset BBB)))'
    weights = _feed(sexpr, {"AAA": [100.0, 101.0], "BBB": [50.0, 50.0]})  # BBB flat
    # No crash, sums to 100 (or empty during warmup); if resolved, flat BBB must not dominate.
    if weights:
        assert weights.get("BBB", 0.0) <= weights.get("AAA", 0.0)


def test_volume_filter_ranks_by_average_not_last_bar():
    # AAA's LAST bar volume is highest, but its 3-bar average dollar volume is lowest, so the
    # filter must select BBB — proving it averages over :lookback instead of reading one bar.
    sexpr = (
        '(strategy "V" (filter :by volume :select (top 1) :lookback 3 '
        "(weight :method equal (asset AAA) (asset BBB))))"
    )
    series = {
        "AAA": [(10.0, 10), (10.0, 10), (10.0, 10), (10.0, 3000)],
        "BBB": [(10.0, 1500), (10.0, 1500), (10.0, 1500), (10.0, 1500)],
    }
    weights = _feed_ohlcv(sexpr, series)
    assert weights.get("BBB", 0.0) == pytest.approx(100.0)
    assert weights.get("AAA", 0.0) == pytest.approx(0.0)


def _ramp(start: float, end: float, n: int) -> list[float]:
    return [start + (end - start) * i / (n - 1) for i in range(n)]


def test_momentum_weights_proportional_to_trailing_return():
    # AAA rises most, CCC medium, BBB least -> weights ordered by trailing return, winner biggest.
    series = {
        "AAA": _ramp(100.0, 200.0, 100),
        "CCC": _ramp(100.0, 150.0, 100),
        "BBB": _ramp(100.0, 120.0, 100),
    }
    sexpr = (
        '(strategy "M" (weight :method momentum :lookback 90 (asset AAA) (asset BBB) (asset CCC)))'
    )
    weights = _feed(sexpr, series)
    assert weights["AAA"] > weights["CCC"] > weights["BBB"] > 0
    assert abs(sum(weights.values()) - 100.0) < 1e-6


def test_momentum_all_negative_falls_back_to_equal():
    # Every asset is declining -> all trailing returns negative -> clip to 0 -> equal weight.
    series = {
        "AAA": _ramp(200.0, 100.0, 100),
        "BBB": _ramp(150.0, 100.0, 100),
        "CCC": _ramp(120.0, 100.0, 100),
    }
    sexpr = (
        '(strategy "M" (weight :method momentum :lookback 90 (asset AAA) (asset BBB) (asset CCC)))'
    )
    weights = _feed(sexpr, series)
    for w in weights.values():
        assert w == pytest.approx(100.0 / 3.0)


def test_momentum_top_selects_then_weights_survivors_proportionally():
    series = {
        "AAA": _ramp(100.0, 200.0, 100),  # strongest
        "CCC": _ramp(100.0, 150.0, 100),  # 2nd
        "BBB": _ramp(100.0, 120.0, 100),  # weakest -> dropped by :top 2
    }
    sexpr = (
        '(strategy "M" (weight :method momentum :lookback 90 :top 2 '
        "(asset AAA) (asset BBB) (asset CCC)))"
    )
    weights = _feed(sexpr, series)
    assert weights["AAA"] > weights["CCC"] > 0
    assert weights.get("BBB", 0.0) == pytest.approx(0.0)  # not in the top 2
    assert abs(sum(weights.values()) - 100.0) < 1e-6
