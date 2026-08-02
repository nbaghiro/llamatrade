"""The runner folds the one-minute live stream into one bar per strategy period.

Both loops (the hand-rolled ``_process_bar`` path and the ``StrategyRuntime`` path) must hand the
session a daily grid, so live indicators read what a backtest of the same strategy reads.
"""

from collections.abc import AsyncIterator
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4
from zoneinfo import ZoneInfo

from llamatrade_alpaca import MockBarStream, MockTradeStream
from llamatrade_alpaca import StreamBar as BarData
from llamatrade_runtime import Bar, StrategySession

from src.runner.runner import RunnerConfig, StrategyRunner
from src.runner.runtime_adapters import StreamBarFeed

ET = ZoneInfo("America/New_York")

SWITCH = (
    '(strategy "RSI Switch" :rebalance daily '
    "(if (> (rsi SPY 14) 70) (asset TLT :weight 100) (else (asset SPY :weight 100))))"
)


def _bar(symbol: str, ts: datetime, close: float, volume: int = 100) -> BarData:
    return BarData(
        symbol=symbol,
        timestamp=ts,
        open=close,
        high=close * 1.01,
        low=close * 0.99,
        close=close,
        volume=volume,
    )


def _session_minutes(day: datetime, count: int) -> list[datetime]:
    open_time = day.replace(hour=9, minute=30, tzinfo=ET)
    return [open_time + timedelta(minutes=i) for i in range(count)]


def _runner(session: StrategySession) -> tuple[StrategyRunner, AsyncMock]:
    config = RunnerConfig(
        tenant_id=uuid4(),
        execution_id=uuid4(),
        strategy_id=uuid4(),
        symbols=["SPY", "TLT"],
        timeframe="1Min",
        warmup_bars=5,
        enforce_trading_hours=False,
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


def _history(session: StrategySession, symbol: str) -> list[Bar]:
    return session._compiled._bar_history[symbol]


class _FiniteStream:
    def __init__(self, bars: list[BarData]) -> None:
        self._bars = bars

    async def stream(self) -> AsyncIterator[BarData]:
        for bar in self._bars:
            yield bar


async def test_hand_rolled_loop_folds_minutes_into_one_bar_per_session() -> None:
    session = StrategySession(SWITCH)
    runner, _ = _runner(session)

    days = [datetime(2025, 7, 14), datetime(2025, 7, 15), datetime(2025, 7, 16)]
    closes = [100.0, 105.0, 98.0, 101.0]
    for day in days:
        for index, ts in enumerate(_session_minutes(day, len(closes))):
            await runner._process_bar(_bar("SPY", ts, closes[index], volume=10))
            await runner._process_bar(_bar("TLT", ts, 50.0, volume=10))

    spy = _history(session, "SPY")
    assert len(spy) == len(days)  # one slot per session, not per minute
    for offset, day in enumerate(days):
        bar = spy[offset]
        assert bar.timestamp == day.replace(tzinfo=ET)
        assert bar.open == 100.0
        assert bar.high == 105.0 * 1.01
        assert bar.low == 98.0 * 0.99
        assert bar.close == 101.0
        assert bar.volume == 40


async def test_runtime_loop_folds_minutes_into_one_bar_per_session() -> None:
    session = StrategySession(SWITCH)
    runner, _ = _runner(session)

    days = [datetime(2025, 7, 14), datetime(2025, 7, 15)]
    closes = [100.0, 105.0, 101.0]
    bars: list[BarData] = []
    for day in days:
        for index, ts in enumerate(_session_minutes(day, len(closes))):
            bars.append(_bar("SPY", ts, closes[index], volume=10))
            bars.append(_bar("TLT", ts, 50.0, volume=10))
    runner.bar_stream = _FiniteStream(bars)
    runner._running = True

    await runner._run_via_runtime()

    spy = _history(session, "SPY")
    assert len(spy) == len(days)
    assert spy[-1].open == 100.0
    assert spy[-1].close == 101.0
    assert spy[-1].volume == 30


async def test_forming_bar_is_seeded_from_the_warm_up_preload() -> None:
    """A session started mid-day keeps the morning the preload already covered."""
    session = StrategySession(SWITCH)
    day = datetime(2025, 7, 15)
    # The preload's daily read includes the currently forming bar (09:30 → now).
    morning = Bar(
        timestamp=day.replace(tzinfo=ET), open=90.0, high=99.0, low=89.0, close=95.0, volume=5_000
    )
    session.evaluate({"SPY": morning, "TLT": morning}, {}, 0.0, warm_up=True)

    runner, _ = _runner(session)
    for ts in _session_minutes(day, 3)[-2:]:
        await runner._process_bar(_bar("SPY", ts, 96.0, volume=10))
        await runner._process_bar(_bar("TLT", ts, 50.0, volume=10))

    spy = _history(session, "SPY")
    assert len(spy) == 1  # still one bar for the day, not a second one
    assert spy[0].open == 90.0  # the preloaded morning open survived
    assert spy[0].low == 89.0
    assert spy[0].close == 96.0
    assert spy[0].volume == 5_020


async def test_stream_feed_ticks_on_wall_clock_but_bars_carry_the_period() -> None:
    day = datetime(2025, 7, 15)
    minutes = _session_minutes(day, 2)
    bars = [_bar(symbol, ts, 100.0) for ts in minutes for symbol in ("SPY", "TLT")]
    feed = StreamBarFeed(_FiniteStream(bars), ["SPY", "TLT"])

    ticks = [tick async for tick in feed]

    assert [ts for ts, _, _ in ticks] == minutes
    assert all(snapshot["SPY"].timestamp == day.replace(tzinfo=ET) for _, snapshot, _ in ticks)
