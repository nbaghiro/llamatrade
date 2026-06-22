"""Tests for StrategySession — the unified live/backtest evaluator.

These cover the two things the old per-symbol live adapter got wrong:
  1. cross-symbol conditions (hold TLT when RSI(SPY) is high) must evaluate correctly
     with all symbols fed together;
  2. the rebalance gate is portfolio-level, not consumed by whichever symbol came first.
"""

from datetime import UTC, datetime, timedelta

import pytest

from llamatrade_compiler.session import StrategySession
from llamatrade_compiler.sizing import Holding, SizingMode
from llamatrade_compiler.types import Bar

# RSI(SPY) switch: when SPY is strongly up (RSI > 70) move to TLT, else hold SPY.
SWITCH = (
    '(strategy "RSI Switch" :rebalance daily '
    "(if (> (rsi SPY 14) 70) "
    "(asset TLT :weight 100) "
    "(else (asset SPY :weight 100))))"
)


def _bar(ts: datetime, close: float) -> Bar:
    return Bar(timestamp=ts, open=close, high=close, low=close, close=close, volume=1_000)


def _series(symbol_closes: dict[str, list[float]], start: datetime) -> list[dict[str, Bar]]:
    """Turn parallel close lists into a list of {symbol: Bar} steps, one per day."""
    n = len(next(iter(symbol_closes.values())))
    steps: list[dict[str, Bar]] = []
    for i in range(n):
        ts = start + timedelta(days=i)
        steps.append({sym: _bar(ts, closes[i]) for sym, closes in symbol_closes.items()})
    return steps


def _run(session: StrategySession, steps: list[dict[str, Bar]], holdings, equity):
    """Feed every step; return the orders from the final step."""
    last: list = []
    for step in steps:
        last = session.evaluate(step, holdings, equity)
    return last


def test_degraded_eval_count_surfaces_through_session():
    """A NaN price makes the condition unevaluable; the session counts it (Issue 5A).

    A raw price comparison propagates NaN deterministically (indicators absorb a
    stray NaN by design, so they don't), making this a clean observability check.
    """
    price_switch = (
        '(strategy "Price Switch" :rebalance daily '
        "(if (> (price SPY) 0) (asset SPY :weight 100) (else (asset TLT :weight 100))))"
    )
    session = StrategySession(price_switch, sizing_mode=SizingMode.DRIFT)
    start = datetime(2024, 1, 1, tzinfo=UTC)
    # Clean warm-up, then a bad (NaN) SPY close.
    spy = [100.0, 101.0, float("nan")]
    tlt = [50.0, 50.0, 50.0]
    steps = _series({"SPY": spy, "TLT": tlt}, start)

    assert session.degraded_eval_count == 0
    _run(session, steps, holdings={}, equity=10_000.0)
    assert session.degraded_eval_count > 0

    # reset() clears the counter for a fresh run.
    session.reset()
    assert session.degraded_eval_count == 0


def test_cross_symbol_condition_picks_tlt_when_spy_rsi_high():
    session = StrategySession(SWITCH, sizing_mode=SizingMode.DRIFT)
    start = datetime(2024, 1, 1, tzinfo=UTC)
    # SPY strictly rising -> RSI -> ~100 -> > 70 -> target TLT. TLT flat-ish.
    spy = [100.0 + i for i in range(40)]
    tlt = [50.0 for _ in range(40)]
    steps = _series({"SPY": spy, "TLT": tlt}, start)

    orders = _run(session, steps, holdings={}, equity=10_000.0)

    assert session.current_weights.get("TLT") == 100.0
    buys = {o.symbol: o for o in orders if o.side == "buy"}
    assert "TLT" in buys  # cross-symbol condition worked: bought TLT off RSI(SPY)


def test_cross_symbol_condition_picks_spy_when_spy_rsi_low():
    session = StrategySession(SWITCH, sizing_mode=SizingMode.DRIFT)
    start = datetime(2024, 1, 1, tzinfo=UTC)
    # SPY strictly falling -> RSI low -> condition false -> else -> target SPY.
    spy = [140.0 - i for i in range(40)]
    tlt = [50.0 for _ in range(40)]
    steps = _series({"SPY": spy, "TLT": tlt}, start)

    _run(session, steps, holdings={}, equity=10_000.0)

    assert session.current_weights.get("SPY") == 100.0


def test_switch_sells_old_buys_new_when_already_holding():
    session = StrategySession(SWITCH, sizing_mode=SizingMode.DRIFT)
    start = datetime(2024, 1, 1, tzinfo=UTC)
    spy = [100.0 + i for i in range(40)]  # RSI high -> target TLT
    tlt = [50.0 for _ in range(40)]
    steps = _series({"SPY": spy, "TLT": tlt}, start)

    # Already holding SPY when the switch fires.
    holdings = {"SPY": Holding("SPY", 100.0)}
    orders = _run(session, steps, holdings=holdings, equity=14_000.0)

    by_symbol = {o.symbol: o for o in orders}
    assert by_symbol["SPY"].side == "sell"
    assert by_symbol["TLT"].side == "buy"


def test_warmup_emits_nothing_until_min_bars():
    session = StrategySession(SWITCH)
    start = datetime(2024, 1, 1, tzinfo=UTC)
    # Fewer bars than min_bars -> no weights, no orders, clock not advanced.
    short = session.min_bars - 1
    spy = [100.0 + i for i in range(short)]
    tlt = [50.0 for _ in range(short)]
    steps = _series({"SPY": spy, "TLT": tlt}, start)

    for step in steps:
        assert session.evaluate(step, {}, 10_000.0) == []
    assert session.last_rebalance is None
    assert session.current_weights == {}


def test_monthly_gate_is_portfolio_level():
    # A monthly strategy: once warm, it should rebalance on the first evaluated day of a
    # new month and NOT again until the next month — regardless of multiple symbols.
    monthly = (
        '(strategy "Monthly SPY" :rebalance monthly '
        "(if (> (rsi SPY 14) 70) (asset TLT :weight 100) (else (asset SPY :weight 100))))"
    )
    session = StrategySession(monthly)
    start = datetime(2024, 1, 1, tzinfo=UTC)
    # 70 daily bars spans Jan, Feb, into Mar.
    spy = [100.0 + i for i in range(70)]
    tlt = [50.0 for _ in range(70)]
    steps = _series({"SPY": spy, "TLT": tlt}, start)

    rebalanced_on: list = []
    for step in steps:
        orders = session.evaluate(step, {}, 10_000.0)
        if orders or (session.last_rebalance == _date_of(step)):
            rebalanced_on.append(session.last_rebalance)

    # Distinct rebalance dates should be at most one per calendar month touched after warmup.
    months = {(d.year, d.month) for d in rebalanced_on if d is not None}
    assert len(months) <= 3  # Jan(after warmup)/Feb/Mar
    # And no two recorded rebalances share a month with different days (one day per month).
    by_month: dict = {}
    for d in rebalanced_on:
        if d is None:
            continue
        key = (d.year, d.month)
        by_month.setdefault(key, set()).add(d.day)
    for days in by_month.values():
        assert len(days) == 1


def _date_of(step: dict[str, Bar]):
    return next(iter(step.values())).timestamp.date()


def test_unparseable_strategy_raises_value_error():
    with pytest.raises(ValueError, match="parse"):
        StrategySession("(this is not valid dsl")


def test_invalid_strategy_raises_value_error():
    # Parses but fails validation (market-cap is rejected).
    with pytest.raises(ValueError, match="Invalid strategy"):
        StrategySession('(strategy "X" (weight :method market-cap (asset AAA) (asset BBB)))')


def test_empty_bars_returns_empty():
    session = StrategySession(SWITCH)
    assert session.evaluate({}, {}, 10_000.0) == []


def test_reset_clears_state():
    session = StrategySession(SWITCH)
    start = datetime(2024, 1, 1, tzinfo=UTC)
    spy = [100.0 + i for i in range(40)]
    tlt = [50.0 for _ in range(40)]
    _run(session, _series({"SPY": spy, "TLT": tlt}, start), holdings={}, equity=10_000.0)
    assert session.last_rebalance is not None

    session.reset()
    assert session.last_rebalance is None
    assert session.current_weights == {}


def test_session_properties_exposed():
    session = StrategySession(SWITCH)
    assert session.name == "RSI Switch"
    assert set(session.symbols) == {"SPY", "TLT"}
    assert session.min_bars > 0
    assert session.rebalance_frequency == "daily"
