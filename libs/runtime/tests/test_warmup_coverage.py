"""Acceptance gate: declared ``required_bars`` must cover each indicator's true warm-up.

The retained-history window and the warm-up gate both derive from ``required_bars``. If that
understates the first bar at which an indicator's slowest output is defined, every condition
referencing it is permanently NaN (the ADX-always-NaN class of bug: ADX is only defined at
``2 * period`` bars while its nominal period is ``period``). This computes each indicator over
a long clean series and asserts ``first_non_nan_index + 1 <= required_bars`` for the slowest of
its outputs, across a representative parameter set for every vocabulary indicator.
"""

import numpy as np
import pytest

from llamatrade_dsl.analysis import IndicatorSpec, _calculate_required_bars
from llamatrade_dsl.ast import INDICATORS
from llamatrade_runtime.indicators.library import PriceData, compute_indicator

# Representative parameters per indicator: the library default plus a larger set that
# stresses the warm-up formula (e.g. ADX(30) needs 60 bars, MACD(5,35,12) signal needs 46).
# The multi-param indicators also include partial-param tuples (a reference that omits later
# params, which the parser accepts); the warm-up must pad from the defaults, not crash.
_PARAM_SETS: dict[str, list[tuple[int | float, ...]]] = {
    "sma": [(14,), (50,)],
    "ema": [(14,), (50,)],
    "rsi": [(14,), (30,)],
    "macd": [(12, 26, 9), (5, 35, 12), (12,), (12, 26)],
    "bbands": [(20, 2.0), (10, 2.5), (20,)],
    "atr": [(14,), (30,)],
    "adx": [(14,), (30,)],
    "stoch": [(14, 3, 3), (21, 5, 4), (14,), (14, 3)],
    "cci": [(20,), (40,)],
    "williams-r": [(14,), (28,)],
    "obv": [()],
    "mfi": [(14,), (28,)],
    "vwap": [()],
    "keltner": [(20, 2.0), (10, 3.0), (20,)],
    "donchian": [(20,), (55,)],
    "stddev": [(20,), (40,)],
    "momentum": [(10,), (30,)],
}

_CASES = [
    (indicator, params) for indicator in sorted(INDICATORS) for params in _PARAM_SETS[indicator]
]


def _clean_prices(n: int) -> PriceData:
    rng = np.random.default_rng(20240729)
    close = 100.0 + np.cumsum(rng.standard_normal(n))
    high = close + np.abs(rng.standard_normal(n))
    low = close - np.abs(rng.standard_normal(n))
    volume = rng.integers(100_000, 1_000_000, n).astype(float)
    return PriceData(open=close.copy(), high=high, low=low, close=close, volume=volume)


def test_every_vocabulary_indicator_has_a_param_set() -> None:
    assert set(_PARAM_SETS) == set(INDICATORS)


@pytest.mark.parametrize(
    "indicator,params", _CASES, ids=[f"{ind}-{'x'.join(map(str, p))}" for ind, p in _CASES]
)
def test_required_bars_covers_warmup(indicator: str, params: tuple[int | float, ...]) -> None:
    prices = _clean_prices(400)
    required = _calculate_required_bars(indicator, params)
    spec = IndicatorSpec(
        indicator_type=indicator,
        symbol="SPY",
        source="close",
        params=params,
        output_key="probe",
        output_field=None,
        required_bars=required,
    )
    outputs = compute_indicator(spec, prices)
    assert outputs, f"{indicator}{params}: produced no output"

    # The slowest output determines warm-up: take the latest first-defined index across all.
    first_defined = -1
    for key, series in outputs.items():
        finite = np.where(np.isfinite(series))[0]
        assert finite.size > 0, (
            f"{indicator}{params} output {key} is all-NaN over {len(prices)} bars"
        )
        first_defined = max(first_defined, int(finite[0]))

    assert first_defined + 1 <= required, (
        f"{indicator}{params}: slowest output first defined at index {first_defined} "
        f"(needs {first_defined + 1} bars) but required_bars={required}"
    )
