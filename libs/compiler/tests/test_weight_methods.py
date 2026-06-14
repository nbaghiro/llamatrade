"""Tests for the covariance-based weight methods and market-cap rejection."""

from datetime import UTC, datetime, timedelta

import numpy as np
import pytest

from llamatrade_compiler import compile_strategy
from llamatrade_compiler.types import Bar
from llamatrade_dsl import parse_strategy, validate_strategy


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
