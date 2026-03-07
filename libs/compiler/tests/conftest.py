"""Shared test fixtures for compiler library tests."""

from datetime import UTC, datetime, timedelta

import numpy as np
import pytest

from llamatrade_compiler.pipeline import PriceData
from llamatrade_compiler.types import Bar


@pytest.fixture
def sample_bars() -> list[Bar]:
    """Generate 100 bars of synthetic OHLCV data with random walk."""
    np.random.seed(42)
    n = 100
    base_price = 100.0
    base_time = datetime(2024, 1, 1, 9, 30, tzinfo=UTC)
    bars = []

    price = base_price
    for i in range(n):
        # Random walk
        change = np.random.randn() * 0.02
        open_price = price
        close_price = price * (1 + change)
        high_price = max(open_price, close_price) * (1 + abs(np.random.randn() * 0.005))
        low_price = min(open_price, close_price) * (1 - abs(np.random.randn() * 0.005))
        volume = int(np.random.randint(100000, 1000000))

        bars.append(
            Bar(
                timestamp=base_time + timedelta(minutes=i),
                open=open_price,
                high=high_price,
                low=low_price,
                close=close_price,
                volume=volume,
            )
        )
        price = close_price

    return bars


@pytest.fixture
def trending_up_bars() -> list[Bar]:
    """Generate 100 bars with strong upward trend."""
    n = 100
    base_time = datetime(2024, 1, 1, 9, 30, tzinfo=UTC)
    bars = []

    for i in range(n):
        # Steady uptrend: +0.5% per bar
        base = 100.0 * (1.005**i)
        open_price = base * 0.998
        close_price = base * 1.002
        high_price = close_price * 1.001
        low_price = open_price * 0.999
        volume = 500000 + i * 1000

        bars.append(
            Bar(
                timestamp=base_time + timedelta(minutes=i),
                open=open_price,
                high=high_price,
                low=low_price,
                close=close_price,
                volume=volume,
            )
        )

    return bars


@pytest.fixture
def trending_down_bars() -> list[Bar]:
    """Generate 100 bars with strong downward trend."""
    n = 100
    base_time = datetime(2024, 1, 1, 9, 30, tzinfo=UTC)
    bars = []

    for i in range(n):
        # Steady downtrend: -0.5% per bar
        base = 100.0 * (0.995**i)
        open_price = base * 1.002
        close_price = base * 0.998
        high_price = open_price * 1.001
        low_price = close_price * 0.999
        volume = 500000 + i * 1000

        bars.append(
            Bar(
                timestamp=base_time + timedelta(minutes=i),
                open=open_price,
                high=high_price,
                low=low_price,
                close=close_price,
                volume=volume,
            )
        )

    return bars


@pytest.fixture
def flat_market_bars() -> list[Bar]:
    """Generate 100 bars with minimal price change (sideways market)."""
    n = 100
    base_time = datetime(2024, 1, 1, 9, 30, tzinfo=UTC)
    base_price = 100.0
    bars = []

    for i in range(n):
        # Small oscillation around base price
        noise = np.sin(i * 0.2) * 0.5
        center = base_price + noise
        open_price = center * 0.9995
        close_price = center * 1.0005
        high_price = max(open_price, close_price) * 1.001
        low_price = min(open_price, close_price) * 0.999
        volume = 300000

        bars.append(
            Bar(
                timestamp=base_time + timedelta(minutes=i),
                open=open_price,
                high=high_price,
                low=low_price,
                close=close_price,
                volume=volume,
            )
        )

    return bars


@pytest.fixture
def sample_prices(sample_bars: list[Bar]) -> PriceData:
    """Convert sample bars to PriceData."""
    return PriceData(
        open=np.array([b.open for b in sample_bars]),
        high=np.array([b.high for b in sample_bars]),
        low=np.array([b.low for b in sample_bars]),
        close=np.array([b.close for b in sample_bars]),
        volume=np.array([b.volume for b in sample_bars]),
    )


@pytest.fixture
def trending_up_prices(trending_up_bars: list[Bar]) -> PriceData:
    """Convert trending up bars to PriceData."""
    return PriceData(
        open=np.array([b.open for b in trending_up_bars]),
        high=np.array([b.high for b in trending_up_bars]),
        low=np.array([b.low for b in trending_up_bars]),
        close=np.array([b.close for b in trending_up_bars]),
        volume=np.array([b.volume for b in trending_up_bars]),
    )


@pytest.fixture
def trending_down_prices(trending_down_bars: list[Bar]) -> PriceData:
    """Convert trending down bars to PriceData."""
    return PriceData(
        open=np.array([b.open for b in trending_down_bars]),
        high=np.array([b.high for b in trending_down_bars]),
        low=np.array([b.low for b in trending_down_bars]),
        close=np.array([b.close for b in trending_down_bars]),
        volume=np.array([b.volume for b in trending_down_bars]),
    )


# New allocation-based strategy fixtures


@pytest.fixture
def simple_allocation_sexpr() -> str:
    """Simple equal-weight allocation strategy S-expression."""
    return """
    (strategy "Simple Allocation"
        :benchmark SPY
        :rebalance monthly
        (weight :method equal
            (asset AAPL)
            (asset GOOGL)
            (asset MSFT)))
    """


@pytest.fixture
def conditional_allocation_sexpr() -> str:
    """Conditional allocation with RSI-based switching."""
    return """
    (strategy "RSI Switching"
        :benchmark SPY
        :rebalance weekly
        (if (> (rsi SPY 14) 70)
            (weight :method equal
                (asset TLT)
                (asset GLD))
            (weight :method equal
                (asset SPY)
                (asset QQQ))))
    """


@pytest.fixture
def momentum_allocation_sexpr() -> str:
    """Momentum-based allocation strategy."""
    return """
    (strategy "Momentum"
        :benchmark SPY
        :rebalance monthly
        (weight :method momentum :lookback 90 :top 3
            (asset AAPL)
            (asset GOOGL)
            (asset MSFT)
            (asset AMZN)
            (asset META)))
    """


@pytest.fixture
def sma_crossover_allocation_sexpr() -> str:
    """SMA crossover conditional allocation."""
    return """
    (strategy "SMA Crossover Allocation"
        :benchmark SPY
        :rebalance daily
        (if (crosses-above (sma SPY 10) (sma SPY 20))
            (asset SPY :weight 100)
            (asset TLT :weight 100)))
    """


@pytest.fixture
def filter_allocation_sexpr() -> str:
    """Filter-based momentum allocation."""
    return """
    (strategy "Top Momentum"
        :benchmark SPY
        :rebalance monthly
        (filter :by momentum :lookback 60 :select top :count 2
            (weight :method equal
                (asset AAPL)
                (asset GOOGL)
                (asset MSFT)
                (asset AMZN))))
    """
