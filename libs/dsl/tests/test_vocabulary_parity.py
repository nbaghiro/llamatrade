"""The indicator vocabulary has one authority (ast.INDICATORS); derived tables must match.

The expected-sources table below pins get_required_sources against the series the runtime
library actually reads per indicator (llamatrade_runtime/indicators/library.py,
compute_indicator). The spec's own source (always "close" from the extractor) is granted
unconditionally, which is why donchian carries "close" even though the runtime reads only
high/low for it.
"""

import pytest

from llamatrade_dsl.analysis import (
    INDICATOR_DEFAULT_PERIODS,
    IndicatorSpec,
    get_required_sources,
)
from llamatrade_dsl.ast import INDICATORS

EXPECTED_SOURCES: dict[str, set[str]] = {
    "sma": {"close"},
    "ema": {"close"},
    "rsi": {"close"},
    "macd": {"close"},
    "bbands": {"close"},
    "stddev": {"close"},
    "momentum": {"close"},
    "atr": {"close", "high", "low"},
    "adx": {"close", "high", "low"},
    "stoch": {"close", "high", "low"},
    "cci": {"close", "high", "low"},
    "williams-r": {"close", "high", "low"},
    "keltner": {"close", "high", "low"},
    "donchian": {"close", "high", "low"},
    "obv": {"close", "volume"},
    "mfi": {"close", "high", "low", "volume"},
    "vwap": {"close", "high", "low", "volume"},
}


def test_default_periods_table_matches_vocabulary() -> None:
    assert set(INDICATOR_DEFAULT_PERIODS) == set(INDICATORS)


def test_expected_sources_table_matches_vocabulary() -> None:
    assert set(EXPECTED_SOURCES) == set(INDICATORS)


@pytest.mark.parametrize("indicator", sorted(INDICATORS))
def test_required_sources_match_runtime_reads(indicator: str) -> None:
    spec = IndicatorSpec(
        indicator_type=indicator,
        symbol="SPY",
        source="close",
        params=INDICATOR_DEFAULT_PERIODS[indicator],
        output_key=f"{indicator}_SPY_close",
        output_field=None,
        required_bars=1,
    )
    assert get_required_sources([spec]) == EXPECTED_SOURCES[indicator]
