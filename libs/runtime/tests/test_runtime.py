"""End-to-end tests for StrategyRuntime and the feed."""

from datetime import UTC, datetime

import pytest

from llamatrade_runtime import (
    Bar,
    ExecutionOutcome,
    Fill,
    HistoricalBarFeed,
    IntendedOrder,
    NullObserver,
    Portfolio,
    RejectedSignal,
    RunResult,
    RuntimeCancelled,
    SimulatedExecution,
    StrategyRuntime,
    Trade,
    build_session,
)
from tests.conftest import MakeBars, RunStrategy

EQUAL_WEIGHT = """(strategy "Equal Weight"
  :rebalance daily
  (weight :method equal
    (asset SPY)
    (asset QQQ)))"""


async def test_equal_weight_generates_trades_for_all_symbols(
    make_bars: MakeBars, run_strategy: RunStrategy
) -> None:
    bars = make_bars({"SPY": [400.0] * 30, "QQQ": [300.0] * 30})
    result = await run_strategy(EQUAL_WEIGHT, bars)
    assert result.final_equity > 0
    assert len(result.equity_curve) > 0
    assert {t.symbol for t in result.trades} == {"SPY", "QQQ"}


async def test_empty_feed_returns_initial_capital() -> None:
    session, _symbols, _min_bars = build_session(EQUAL_WEIGHT)
    feed = HistoricalBarFeed({}, datetime(2024, 1, 1, tzinfo=UTC), datetime(2024, 2, 1, tzinfo=UTC))
    result = await StrategyRuntime(session, Portfolio(50000), SimulatedExecution()).run(feed)
    assert result.final_equity == 50000
    assert result.trades == []


async def test_should_abort_raises_runtime_cancelled(make_bars: MakeBars) -> None:
    bars = make_bars({"SPY": [400.0] * 30, "QQQ": [300.0] * 30})
    session, _symbols, min_bars = build_session(EQUAL_WEIGHT)
    feed = HistoricalBarFeed(bars, bars["SPY"][min_bars].timestamp, bars["SPY"][-1].timestamp)
    runtime = StrategyRuntime(session, Portfolio(100000), SimulatedExecution())
    with pytest.raises(RuntimeCancelled):
        await runtime.run(feed, should_abort=lambda: True)


async def test_observer_receives_lifecycle_events(
    make_bars: MakeBars, run_strategy: RunStrategy
) -> None:
    class RecordingObserver:
        def __init__(self) -> None:
            self.starts = 0
            self.ticks = 0
            self.fills = 0
            self.completes = 0

        def on_start(self, total_ticks: int | None) -> None:
            self.starts += 1

        def on_tick(self, index: int, total: int | None, date: datetime, equity: float) -> None:
            self.ticks += 1

        def on_fill(self, fill: Fill) -> None:
            self.fills += 1

        def on_trade(self, trade: Trade) -> None:
            return None

        def on_reject(self, rejected: RejectedSignal) -> None:
            return None

        def on_complete(self, result: RunResult) -> None:
            self.completes += 1

    obs = RecordingObserver()
    bars = make_bars({"SPY": [400.0] * 30, "QQQ": [300.0] * 30})
    await run_strategy(EQUAL_WEIGHT, bars, observer=obs)
    assert obs.starts == 1
    assert obs.completes == 1
    assert obs.ticks > 0
    assert obs.fills > 0


def test_feed_total_ticks_counts_only_trading_dates(make_bars: MakeBars) -> None:
    bars = make_bars({"SPY": [400.0] * 20})
    feed = HistoricalBarFeed(bars, bars["SPY"][5].timestamp, bars["SPY"][-1].timestamp)
    assert feed.total_ticks == 15


async def test_monthly_rebalance_trades_no_more_than_daily(
    make_bars: MakeBars, run_strategy: RunStrategy
) -> None:
    closes = {"SPY": [400.0 + i for i in range(40)], "QQQ": [300.0 - i * 0.3 for i in range(40)]}
    bars = make_bars(closes)
    daily = await run_strategy(EQUAL_WEIGHT, bars)
    monthly = await run_strategy(
        EQUAL_WEIGHT.replace(":rebalance daily", ":rebalance monthly"), bars
    )
    assert len(monthly.trades) <= len(daily.trades)


async def test_rotation_buys_new_symbol_that_sorts_before_its_funding_sell(
    make_bars: MakeBars,
) -> None:
    """A full rotation must complete even when the buy sorts before the sell that funds it.

    Holds ZZZ while it sits below its SMA, then flips fully to AAA. AAA sorts before ZZZ, so
    without sells-before-buys ordering the AAA buy runs while cash is still tied up in ZZZ and is
    rejected — AAA would never be bought. With the fix, ZZZ is sold first and AAA fills.
    """
    config = (
        '(strategy "Rotate" :rebalance daily '
        "(if (> (price ZZZ) (sma ZZZ 3)) (asset AAA :weight 100) "
        "(else (asset ZZZ :weight 100))))"
    )
    zzz = [100, 100, 100, 95, 90, 85, 80, 120, 140, 160, 180, 180]
    bars = make_bars({"ZZZ": [float(c) for c in zzz], "AAA": [50.0] * len(zzz)})
    session, symbols, min_bars = build_session(config)
    feed = HistoricalBarFeed(
        {s: bars[s] for s in symbols},
        bars["ZZZ"][min_bars].timestamp,
        bars["ZZZ"][-1].timestamp,
    )
    result = await StrategyRuntime(session, Portfolio(100000), SimulatedExecution()).run(feed)

    traded = {t.symbol for t in result.trades}
    assert "ZZZ" in traded  # bought early, sold at the flip
    assert "AAA" in traded  # the buy that sorts before its funding sell filled


async def test_stream_submits_orders_and_never_liquidates(make_bars: MakeBars) -> None:
    """Live driver: evaluate + submit each tick, no liquidation, no RunResult."""
    submitted: list[tuple[str, str]] = []

    class RecordingExecution:
        async def execute(
            self, order: IntendedOrder, bar: Bar, portfolio: Portfolio, date: datetime
        ) -> ExecutionOutcome:
            submitted.append((order.side, order.symbol))
            return ExecutionOutcome()  # accepted; the fill arrives out-of-band, not inline

        async def liquidate(self, portfolio: Portfolio, date: datetime) -> list[ExecutionOutcome]:
            raise AssertionError("stream() must never liquidate live positions")

    session, symbols, min_bars = build_session(EQUAL_WEIGHT)
    bars = make_bars({"SPY": [400.0] * 30, "QQQ": [300.0] * 30})
    feed = HistoricalBarFeed(
        {s: bars[s] for s in symbols},
        bars["SPY"][min_bars].timestamp,
        bars["SPY"][-1].timestamp,
    )
    runtime = StrategyRuntime(session, Portfolio(100000), RecordingExecution())

    result = await runtime.stream(feed)

    assert result is None
    # execute never fills the book → holdings stay empty → the strategy keeps issuing buys.
    assert submitted
    assert all(side == "buy" for side, _ in submitted)


async def test_stream_should_stop_halts_early(make_bars: MakeBars) -> None:
    ticks = 0

    class NoopExecution:
        async def execute(
            self, order: IntendedOrder, bar: Bar, portfolio: Portfolio, date: datetime
        ) -> ExecutionOutcome:
            return ExecutionOutcome()

        async def liquidate(self, portfolio: Portfolio, date: datetime) -> list[ExecutionOutcome]:
            return []

    class TickCounter(NullObserver):
        def on_tick(self, index: int, total: int | None, date: datetime, equity: float) -> None:
            nonlocal ticks
            ticks += 1

    session, symbols, min_bars = build_session(EQUAL_WEIGHT)
    bars = make_bars({"SPY": [400.0] * 30, "QQQ": [300.0] * 30})
    feed = HistoricalBarFeed(
        {s: bars[s] for s in symbols},
        bars["SPY"][min_bars].timestamp,
        bars["SPY"][-1].timestamp,
    )
    runtime = StrategyRuntime(session, Portfolio(100000), NoopExecution(), observer=TickCounter())

    await runtime.stream(feed, should_stop=lambda: ticks >= 2)

    assert ticks == 2
