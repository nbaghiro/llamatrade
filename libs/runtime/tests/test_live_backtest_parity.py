"""Live↔backtest parity over a recorded day of minute bars.

The live path (``StrategyRuntime.stream`` over a ``FormingBarFeed`` of one-minute bars) and the
backtest path (``StrategyRuntime.run`` over the daily bars those minutes fold into) are driven
with the same portfolio and execution adapters, so any difference is the data resolution itself.
The tests assert the two agree on the bar history, on the indicator series computed from it, and
on the orders that history produces.
"""

from collections.abc import AsyncIterator, Iterable
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import numpy as np
import pytest

from llamatrade_runtime import (
    Bar,
    Fill,
    FormingBarAggregator,
    FormingBarFeed,
    HistoricalBarFeed,
    Portfolio,
    PriceData,
    RejectedSignal,
    RunResult,
    SimulatedExecution,
    StrategyRuntime,
    StrategySession,
    Trade,
    compute_all_indicators,
    daily_period_start,
)

ET = ZoneInfo("America/New_York")
MINUTES_PER_SESSION = 60
CAPITAL = 100_000.0

# RSI(SPY) selects which asset to hold: a daily-lookback indicator and a cross-symbol condition.
RSI_SWITCH = (
    '(strategy "RSI Switch" :rebalance daily '
    "(if (> (rsi SPY 14) 70) (asset TLT :weight 100) (else (asset SPY :weight 100))))"
)
RSI_SWITCH_WEEKLY = RSI_SWITCH.replace(":rebalance daily", ":rebalance weekly")


# --- recorded market data -------------------------------------------------------------------


def _sessions(first: date, count: int) -> list[date]:
    """``count`` consecutive weekday sessions starting at ``first``."""
    days: list[date] = []
    day = first
    while len(days) < count:
        if day.weekday() < 5:
            days.append(day)
        day += timedelta(days=1)
    return days


def _minute_bars(day: date, open_price: float, close_price: float) -> list[Bar]:
    """One session of minute bars walking from ``open_price`` to ``close_price``."""
    start = datetime(day.year, day.month, day.day, 9, 30, tzinfo=ET)
    step = (close_price - open_price) / MINUTES_PER_SESSION
    bars: list[Bar] = []
    price = open_price
    for i in range(MINUTES_PER_SESSION):
        nxt = price + step
        bars.append(
            Bar(
                timestamp=start + timedelta(minutes=i),
                open=price,
                high=max(price, nxt) * 1.001,
                low=min(price, nxt) * 0.999,
                close=nxt,
                volume=1_000 + i,
            )
        )
        price = nxt
    return bars


def _fold(bars: Iterable[Bar]) -> Bar:
    """The completed period bar a session of minute bars folds into."""
    ordered = list(bars)
    return Bar(
        timestamp=daily_period_start(ordered[0].timestamp),
        open=ordered[0].open,
        high=max(b.high for b in ordered),
        low=min(b.low for b in ordered),
        close=ordered[-1].close,
        volume=sum(b.volume for b in ordered),
    )


def _price_path(sessions: list[date], closes: list[float]) -> dict[date, list[Bar]]:
    """Minute bars per session for a symbol that closes at ``closes[i]`` on session ``i``."""
    path: dict[date, list[Bar]] = {}
    previous = closes[0]
    for day, close in zip(sessions, closes, strict=True):
        path[day] = _minute_bars(day, previous, close)
        previous = close
    return path


def _market(sessions: list[date]) -> dict[str, dict[date, list[Bar]]]:
    """SPY rallies then sells off hard (RSI crosses back under 70); TLT drifts up slowly."""
    warm = len(sessions) - 4
    spy_closes = [100.0 + i for i in range(warm)] + [100.0 + warm - 6.0 * (i + 1) for i in range(4)]
    tlt_closes = [50.0 + 0.05 * i for i in range(len(sessions))]
    return {
        "SPY": _price_path(sessions, spy_closes),
        "TLT": _price_path(sessions, tlt_closes),
    }


def _daily(market: dict[str, dict[date, list[Bar]]], sessions: list[date]) -> dict[str, list[Bar]]:
    return {symbol: [_fold(market[symbol][day]) for day in sessions] for symbol in market}


async def _minute_stream(
    market: dict[str, dict[date, list[Bar]]], sessions: list[date]
) -> AsyncIterator[tuple[str, Bar]]:
    """Replay the recorded minutes symbol-interleaved, exactly as a live fan-out delivers them."""
    symbols = sorted(market)
    for day in sessions:
        per_symbol = [market[symbol][day] for symbol in symbols]
        for index in range(min(len(bars) for bars in per_symbol)):
            for symbol, bars in zip(symbols, per_symbol, strict=True):
                yield symbol, bars[index]


def _closing_minutes(sessions: list[date]) -> set[datetime]:
    """The final minute of each session — when a period's forming bar is complete."""
    return {
        datetime(d.year, d.month, d.day, 9, 30, tzinfo=ET)
        + timedelta(minutes=MINUTES_PER_SESSION - 1)
        for d in sessions
    }


# --- drivers --------------------------------------------------------------------------------


class _Recorder:
    """Records the runtime's lifecycle events in order."""

    def __init__(self) -> None:
        self.events: list[tuple[str, object]] = []

    def on_start(self, total_ticks: int | None) -> None:
        return None

    def on_tick(self, index: int, total: int | None, date: datetime, equity: float) -> None:
        self.events.append(("tick", date))

    def on_fill(self, fill: Fill) -> None:
        self.events.append(("fill", fill))

    def on_trade(self, trade: Trade) -> None:
        self.events.append(("trade", trade))

    def on_reject(self, rejected: RejectedSignal) -> None:
        self.events.append(("reject", rejected))

    def on_complete(self, result: RunResult) -> None:
        return None


def _loop_fills(recorder: _Recorder) -> list[Fill]:
    """Fills from inside the evaluation loop, dropping a backtest's end-of-run liquidation.

    Fills are emitted before the tick they belong to, so everything after the last tick is the
    liquidation the live path never performs.
    """
    last_tick = max(i for i, (kind, _) in enumerate(recorder.events) if kind == "tick")
    return [
        fill
        for i, (kind, event) in enumerate(recorder.events)
        if kind == "fill" and i < last_tick and isinstance(fill := event, Fill)
    ]


def _orders(recorder: _Recorder) -> list[tuple[str, str, float, float]]:
    """The order intents the run produced: symbol, side, quantity and fill price."""
    return [
        (fill.symbol, fill.side, round(fill.quantity, 9), round(fill.price, 9))
        for fill in _loop_fills(recorder)
    ]


def _order_days(recorder: _Recorder) -> list[date]:
    """The exchange-local sessions on which the run traded."""
    return sorted({fill.date.astimezone(ET).date() for fill in _loop_fills(recorder)})


def _warm_up(session: StrategySession, portfolio: Portfolio, bars: list[dict[str, Bar]]) -> None:
    """Prime indicator history from stored daily bars, as the live preload does."""
    for snapshot in bars:
        portfolio.update_prices({s: b.close for s, b in snapshot.items()})
        session.evaluate(snapshot, {}, portfolio.equity(), warm_up=True)


async def _run_live(
    sexpr: str,
    market: dict[str, dict[date, list[Bar]]],
    warm_up_sessions: list[date],
    traded_sessions: list[date],
    *,
    aggregator: FormingBarAggregator | None = None,
    seed_warm_up: bool = True,
) -> tuple[StrategySession, Portfolio, _Recorder]:
    session = StrategySession(sexpr)
    portfolio = Portfolio(CAPITAL)
    if seed_warm_up:
        daily = _daily(market, warm_up_sessions)
        _warm_up(
            session,
            portfolio,
            [{s: daily[s][i] for s in daily} for i in range(len(warm_up_sessions))],
        )
    recorder = _Recorder()
    runtime = StrategyRuntime(session, portfolio, SimulatedExecution(), observer=recorder)
    feed = FormingBarFeed(
        _minute_stream(market, traded_sessions),
        sorted(market),
        aggregator=aggregator,
        gate=lambda ts: ts in _closing_minutes(traded_sessions),
    )
    await runtime.stream(feed)
    return session, portfolio, recorder


async def _run_backtest(
    sexpr: str,
    market: dict[str, dict[date, list[Bar]]],
    warm_up_sessions: list[date],
    traded_sessions: list[date],
) -> tuple[StrategySession, Portfolio, _Recorder]:
    session = StrategySession(sexpr)
    portfolio = Portfolio(CAPITAL)
    recorder = _Recorder()
    runtime = StrategyRuntime(session, portfolio, SimulatedExecution(), observer=recorder)
    daily = _daily(market, warm_up_sessions + traded_sessions)
    start = daily_period_start(datetime(*traded_sessions[0].timetuple()[:3], tzinfo=ET))
    end = daily_period_start(datetime(*traded_sessions[-1].timetuple()[:3], tzinfo=ET))
    await runtime.run(HistoricalBarFeed(daily, start, end))
    return session, portfolio, recorder


def _history(session: StrategySession) -> dict[str, list[Bar]]:
    return session._compiled._bar_history


def _indicator_series(session: StrategySession) -> dict[str, np.ndarray]:
    """Every indicator the strategy reads, computed over the session's own bar history."""
    series: dict[str, np.ndarray] = {}
    for symbol, bars in _history(session).items():
        specs = [i for i in session._compiled.indicators if i.symbol == symbol]
        if not specs:
            continue
        prices = PriceData(
            open=np.array([b.open for b in bars]),
            high=np.array([b.high for b in bars]),
            low=np.array([b.low for b in bars]),
            close=np.array([b.close for b in bars]),
            volume=np.array([b.volume for b in bars]),
        )
        series.update(compute_all_indicators(specs, prices))
    return series


# --- parity ---------------------------------------------------------------------------------


async def test_live_history_is_the_backtest_daily_series_bar_for_bar() -> None:
    sessions = _sessions(date(2025, 6, 2), 24)
    warm_up, traded = sessions[:20], sessions[20:]
    market = _market(sessions)

    live, _, _ = await _run_live(RSI_SWITCH, market, warm_up, traded)
    backtest, _, _ = await _run_backtest(RSI_SWITCH, market, warm_up, traded)

    assert _history(live) == _history(backtest)
    for symbol in market:
        # One bar per session, not one per streamed minute.
        assert len(_history(live)[symbol]) == len(sessions)


async def test_live_indicator_series_equals_the_backtest_series() -> None:
    sessions = _sessions(date(2025, 6, 2), 24)
    warm_up, traded = sessions[:20], sessions[20:]
    market = _market(sessions)

    live, _, _ = await _run_live(RSI_SWITCH, market, warm_up, traded)
    backtest, _, _ = await _run_backtest(RSI_SWITCH, market, warm_up, traded)

    live_series = _indicator_series(live)
    backtest_series = _indicator_series(backtest)
    assert set(live_series) == set(backtest_series) and live_series
    for key, values in live_series.items():
        np.testing.assert_array_equal(values, backtest_series[key])


async def test_live_orders_equal_backtest_orders() -> None:
    sessions = _sessions(date(2025, 6, 2), 24)
    warm_up, traded = sessions[:20], sessions[20:]
    market = _market(sessions)

    live_session, live_portfolio, live_recorder = await _run_live(
        RSI_SWITCH, market, warm_up, traded
    )
    bt_session, bt_portfolio, bt_recorder = await _run_backtest(RSI_SWITCH, market, warm_up, traded)

    orders = _orders(live_recorder)
    assert orders  # the sell-off flips the condition, so the run is not vacuous
    assert orders == _orders(bt_recorder)
    assert _order_days(live_recorder) == _order_days(bt_recorder)
    assert live_session.current_weights == bt_session.current_weights
    assert live_session.last_rebalance == bt_session.last_rebalance
    # The backtest liquidates at the last known prices, which are the live marks.
    assert live_portfolio.equity() == pytest.approx(bt_portfolio.equity())


async def test_cross_symbol_condition_holds_the_other_leg_in_both_paths() -> None:
    """RSI(SPY) high must put the book in TLT in live exactly as it does in backtest."""
    sessions = _sessions(date(2025, 6, 2), 22)
    warm_up, traded = sessions[:20], sessions[20:]
    market = _market(sessions)
    # Keep SPY rallying through the traded sessions so RSI stays above 70.
    market["SPY"] = _price_path(sessions, [100.0 + i for i in range(len(sessions))])

    live_session, _, live_recorder = await _run_live(RSI_SWITCH, market, warm_up, traded)
    bt_session, _, bt_recorder = await _run_backtest(RSI_SWITCH, market, warm_up, traded)

    assert live_session.current_weights == {"TLT": 100.0}
    assert live_session.current_weights == bt_session.current_weights
    assert _orders(live_recorder) == _orders(bt_recorder)
    assert {symbol for symbol, *_ in _orders(live_recorder)} == {"TLT"}


async def test_weekly_rebalance_fires_on_the_same_sessions() -> None:
    sessions = _sessions(date(2025, 6, 2), 30)
    warm_up, traded = sessions[:20], sessions[20:]
    market = _market(sessions)

    live_session, _, live_recorder = await _run_live(RSI_SWITCH_WEEKLY, market, warm_up, traded)
    bt_session, _, bt_recorder = await _run_backtest(RSI_SWITCH_WEEKLY, market, warm_up, traded)

    assert _order_days(live_recorder) == _order_days(bt_recorder)
    assert _orders(live_recorder) == _orders(bt_recorder)
    assert live_session.last_rebalance == bt_session.last_rebalance
    # A weekly clock trades on Mondays only, well short of the traded session count.
    assert all(day.weekday() == 0 for day in _order_days(live_recorder))


async def test_mid_session_start_folds_the_preloaded_partial_bar() -> None:
    """A session started mid-day adopts the partial bar its preload already covers."""
    sessions = _sessions(date(2025, 6, 2), 22)
    warm_up, traded = sessions[:21], sessions[21:]
    market = _market(sessions)
    start_day = traded[0]
    split = MINUTES_PER_SESSION // 2

    # The warm-up preload returns closed sessions plus the currently forming bar (daily reads
    # include it), so the session's history already holds the morning of the start day.
    live_session = StrategySession(RSI_SWITCH)
    portfolio = Portfolio(CAPITAL)
    daily = _daily(market, warm_up)
    _warm_up(
        live_session, portfolio, [{s: daily[s][i] for s in daily} for i in range(len(warm_up))]
    )
    morning = {s: _fold(market[s][start_day][:split]) for s in market}
    _warm_up(live_session, portfolio, [morning])

    aggregator = FormingBarAggregator(seed=live_session.last_bars())
    afternoon = {s: {start_day: market[s][start_day][split:]} for s in market}
    recorder = _Recorder()
    runtime = StrategyRuntime(live_session, portfolio, SimulatedExecution(), observer=recorder)
    await runtime.stream(
        FormingBarFeed(
            _minute_stream(afternoon, [start_day]),
            sorted(market),
            aggregator=aggregator,
            gate=lambda ts: ts in _closing_minutes([start_day]),
        )
    )

    bt_session, _, bt_recorder = await _run_backtest(RSI_SWITCH, market, warm_up, traded)

    # The stitched morning + streamed afternoon reproduce the whole session's bar.
    for symbol in market:
        assert _history(live_session)[symbol][-1] == _fold(market[symbol][start_day])
        assert len(_history(live_session)[symbol]) == len(sessions)
    assert _orders(recorder) == _orders(bt_recorder)
    assert live_session.current_weights == bt_session.current_weights


async def test_decision_on_a_forming_bar_matches_a_backtest_over_the_same_close_so_far() -> None:
    """Evaluating mid-session equals a backtest whose last bar is the close so far."""
    sessions = _sessions(date(2025, 6, 2), 21)
    warm_up, traded = sessions[:20], sessions[20:]
    market = _market(sessions)
    day = traded[0]
    minutes_seen = 1  # the rebalance clock fires on the session's first complete snapshot

    session = StrategySession(RSI_SWITCH)
    portfolio = Portfolio(CAPITAL)
    daily = _daily(market, warm_up)
    _warm_up(session, portfolio, [{s: daily[s][i] for s in daily} for i in range(len(warm_up))])
    recorder = _Recorder()
    runtime = StrategyRuntime(session, portfolio, SimulatedExecution(), observer=recorder)
    await runtime.stream(FormingBarFeed(_minute_stream(market, traded), sorted(market)))

    # The same run as a backtest, with the traded session represented by its close so far.
    close_so_far = {s: dict(market[s]) for s in market}
    for symbol in market:
        close_so_far[symbol][day] = market[symbol][day][:minutes_seen]
    _, _, bt_recorder = await _run_backtest(RSI_SWITCH, close_so_far, warm_up, traded)

    assert _orders(recorder)
    assert _orders(recorder) == _orders(bt_recorder)


async def test_intraday_evaluation_sees_close_so_far_and_keeps_completed_sessions_exact() -> None:
    """With no close-aligned gate the current session reads close-so-far, never minute bars."""
    sessions = _sessions(date(2025, 6, 2), 23)
    warm_up, traded = sessions[:20], sessions[20:]
    market = _market(sessions)

    session = StrategySession(RSI_SWITCH)
    portfolio = Portfolio(CAPITAL)
    daily = _daily(market, warm_up)
    _warm_up(session, portfolio, [{s: daily[s][i] for s in daily} for i in range(len(warm_up))])
    runtime = StrategyRuntime(session, portfolio, SimulatedExecution(), observer=_Recorder())
    # Stop part-way through the last session: its bar must be the fold of the minutes so far.
    partial = MINUTES_PER_SESSION // 3
    truncated = {s: dict(market[s]) for s in market}
    truncated["SPY"][traded[-1]] = market["SPY"][traded[-1]][:partial]
    truncated["TLT"][traded[-1]] = market["TLT"][traded[-1]][:partial]
    await runtime.stream(FormingBarFeed(_minute_stream(truncated, traded), sorted(market)))

    for symbol in market:
        history = _history(session)[symbol]
        assert len(history) == len(sessions)  # one slot per session, not per minute
        # Completed sessions are the exact daily bars.
        for offset, day in enumerate(traded[:-1], start=len(warm_up)):
            assert history[offset] == _fold(market[symbol][day])
        # The session in progress is the fold of the minutes received so far.
        assert history[-1] == _fold(market[symbol][traded[-1]][:partial])
