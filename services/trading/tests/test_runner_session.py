"""Tests for the runner's merged-symbol StrategySession path (P6 rewire).

Verifies the two properties the old per-symbol path lacked:
  1. bar synchronization — the strategy evaluates once per period, only after every
     subscribed symbol has produced that period's bar;
  2. cross-symbol conditions — a condition on one symbol drives allocation of another.
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from llamatrade_alpaca import MockBarStream, MockTradeStream
from llamatrade_alpaca import StreamBar as BarData
from llamatrade_compiler import StrategySession

from src.runner.runner import RunnerConfig, StrategyRunner

# RSI(SPY) switch: rising SPY -> RSI high -> hold TLT (cross-symbol condition).
SWITCH = (
    '(strategy "RSI Switch" :rebalance daily '
    "(if (> (rsi SPY 14) 70) (asset TLT :weight 100) (else (asset SPY :weight 100))))"
)


def _bar(symbol: str, ts: datetime, close: float) -> BarData:
    return BarData(
        symbol=symbol, timestamp=ts, open=close, high=close, low=close, close=close, volume=1000
    )


def _runner(session: StrategySession) -> tuple[StrategyRunner, AsyncMock]:
    config = RunnerConfig(
        tenant_id=uuid4(),
        execution_id=uuid4(),
        strategy_id=uuid4(),
        symbols=["SPY", "TLT"],
        timeframe="1Min",
        warmup_bars=5,
        enforce_trading_hours=False,  # don't gate on market hours in the test
    )
    order_executor = AsyncMock()
    order_executor.submit_order.return_value = MagicMock(
        id=uuid4(), status="submitted", client_order_id="lt-test"
    )
    risk_manager = AsyncMock()
    risk_manager.check_order.return_value = MagicMock(passed=True, violations=[])
    runner = StrategyRunner(
        config=config,
        strategy_fn=None,
        bar_stream=MockBarStream(bars={"SPY": [], "TLT": []}),
        trade_stream=MockTradeStream(),
        order_executor=order_executor,
        risk_manager=risk_manager,
        session=session,
    )
    return runner, order_executor


async def test_requires_a_session_or_strategy_fn():
    config = RunnerConfig(
        tenant_id=uuid4(),
        execution_id=uuid4(),
        strategy_id=uuid4(),
        symbols=["SPY"],
        timeframe="1Min",
    )
    with pytest.raises(ValueError, match="session or a strategy_fn"):
        StrategyRunner(
            config=config,
            strategy_fn=None,
            bar_stream=MockBarStream(bars={"SPY": []}),
            trade_stream=MockTradeStream(),
            order_executor=AsyncMock(),
            risk_manager=AsyncMock(),
        )


async def test_does_not_evaluate_until_all_symbols_have_the_period_bar():
    runner, order_executor = _runner(StrategySession(SWITCH))
    ts = datetime(2024, 1, 1, 14, 30, tzinfo=UTC)
    # Only SPY's bar for this period — TLT missing -> must not evaluate/submit.
    await runner._process_bar(_bar("SPY", ts, 100.0))
    order_executor.submit_order.assert_not_called()
    assert runner._last_evaluated_ts is None


async def test_cross_symbol_condition_buys_tlt_when_spy_rsi_high():
    session = StrategySession(SWITCH)
    runner, order_executor = _runner(session)
    base = datetime(2024, 1, 1, 14, 30, tzinfo=UTC)

    # Feed both symbols each period; SPY strictly rising -> RSI ~100 -> target TLT.
    for i in range(40):
        ts = base + timedelta(days=i)
        await runner._process_bar(_bar("SPY", ts, 100.0 + i))
        await runner._process_bar(_bar("TLT", ts, 50.0))

    assert session.current_weights.get("TLT") == 100.0
    # A TLT buy must have been submitted (cross-symbol condition drove it).
    submitted_symbols = {
        call.kwargs.get("order", call.args[2] if len(call.args) > 2 else None).symbol
        for call in order_executor.submit_order.call_args_list
    }
    assert "TLT" in submitted_symbols


async def test_evaluates_once_per_period_not_per_symbol_bar():
    runner, order_executor = _runner(StrategySession(SWITCH))
    base = datetime(2024, 1, 1, 14, 30, tzinfo=UTC)
    # Warm up past min_bars so a rebalance can fire.
    for i in range(40):
        ts = base + timedelta(days=i)
        await runner._process_bar(_bar("SPY", ts, 100.0 + i))
        await runner._process_bar(_bar("TLT", ts, 50.0))

    # Re-feeding the SAME final period's bars must not trigger another evaluation.
    last_ts = base + timedelta(days=39)
    calls_before = order_executor.submit_order.call_count
    await runner._process_bar(_bar("SPY", last_ts, 139.0))
    await runner._process_bar(_bar("TLT", last_ts, 50.0))
    assert order_executor.submit_order.call_count == calls_before
