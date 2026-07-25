"""Tests for the simulated execution adapter."""

from datetime import UTC, datetime

import pytest

from llamatrade_runtime import Bar, IntendedOrder, Portfolio, SimulatedExecution

D = datetime(2024, 1, 1, tzinfo=UTC)


def _bar(close: float) -> Bar:
    return Bar(timestamp=D, open=close, high=close, low=close, close=close, volume=1000)


async def test_buy_fills_at_bar_close() -> None:
    p = Portfolio(100000)
    out = await SimulatedExecution().execute(
        IntendedOrder("SPY", "buy", 10, 100.0), _bar(100.0), p, D
    )
    assert out.fill is not None
    assert out.fill.price == pytest.approx(100.0)


async def test_buy_slippage_raises_fill_price() -> None:
    p = Portfolio(100000)
    out = await SimulatedExecution(slippage_rate=0.01).execute(
        IntendedOrder("SPY", "buy", 10, 100.0), _bar(100.0), p, D
    )
    assert out.fill is not None
    assert out.fill.price == pytest.approx(101.0)


async def test_sell_zero_quantity_closes_full_position() -> None:
    p = Portfolio(100000)
    ex = SimulatedExecution(slippage_rate=0.01)
    await ex.execute(IntendedOrder("SPY", "buy", 10, 100.0), _bar(100.0), p, D)
    out = await ex.execute(IntendedOrder("SPY", "sell", 0, 100.0), _bar(100.0), p, D)
    assert out.fill is not None
    assert out.fill.quantity == pytest.approx(10)
    assert out.fill.price == pytest.approx(99.0)  # sell slippage lowers price
    assert not p.positions


async def test_unknown_side_rejects() -> None:
    p = Portfolio(100000)
    out = await SimulatedExecution().execute(
        IntendedOrder("SPY", "hold", 10, 100.0), _bar(100.0), p, D
    )
    assert out.rejected is not None
    assert "Unsupported signal type" in out.rejected.reason


async def test_liquidate_closes_at_last_price() -> None:
    p = Portfolio(100000)
    ex = SimulatedExecution()
    await ex.execute(IntendedOrder("SPY", "buy", 10, 100.0), _bar(100.0), p, D)
    p.update_prices({"SPY": 130.0})
    outcomes = await ex.liquidate(p, D)
    assert len(outcomes) == 1
    assert outcomes[0].trade is not None
    assert outcomes[0].trade.exit_price == pytest.approx(130.0)
    assert not p.positions


async def test_liquidate_without_last_price_rejects() -> None:
    p = Portfolio(100000)
    ex = SimulatedExecution()
    # open() does not record a last price; without an intervening tick, liquidation cannot mark it
    await ex.execute(IntendedOrder("SPY", "buy", 10, 100.0), _bar(100.0), p, D)
    outcomes = await ex.liquidate(p, D)
    assert outcomes[0].rejected is not None
    assert "no last price" in outcomes[0].rejected.reason
