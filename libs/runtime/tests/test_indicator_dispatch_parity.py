"""Every indicator the language accepts must be computable by the runtime library."""

import numpy as np
import pytest

from llamatrade_dsl.analysis import IndicatorSpec
from llamatrade_dsl.ast import INDICATORS
from llamatrade_runtime.indicators.library import PriceData, compute_indicator


def _prices(n: int = 120) -> PriceData:
    rng = np.random.default_rng(7)
    close = 100.0 + np.cumsum(rng.normal(0, 0.5, n))
    return PriceData(
        open=close - 0.1,
        high=close + 0.5,
        low=close - 0.5,
        close=close,
        volume=np.full(n, 10_000.0),
    )


@pytest.mark.parametrize("indicator", sorted(INDICATORS))
def test_every_vocabulary_indicator_computes(indicator: str) -> None:
    params = (14,) if indicator != "macd" else (12, 26, 9)
    spec = IndicatorSpec(
        indicator_type=indicator,
        symbol="SPY",
        source="close",
        params=params,
        output_key=f"{indicator}_SPY_close_{'_'.join(str(p) for p in params)}",
        output_field=None,
        required_bars=40,
    )
    outputs = compute_indicator(spec, _prices())
    assert outputs, f"{indicator} produced no output series"
    for series in outputs.values():
        assert len(series) > 0
