"""Tests for warm-up preload — priming a live session's history from the market-data store."""

from datetime import UTC, datetime, timedelta

from llamatrade_runtime import StrategySession

from src.runner.warmup import preload_session_history

# Single-symbol strategy gated by an SPY indicator (min_bars = 5); holds SPY 100% once warm.
TREND_UP = (
    '(strategy "Trend" :rebalance daily '
    "(if (> (sma SPY 3) (sma SPY 5)) (asset SPY :weight 100) (else (asset SPY :weight 100))))"
)


class _FakeMarketData:
    """Returns a fixed per-symbol history; records the fetch args."""

    def __init__(self, bars_by_symbol: dict[str, list[dict[str, object]]]) -> None:
        self.bars_by_symbol = bars_by_symbol
        self.calls: list[tuple[str, str, int | None]] = []

    async def get_bars(
        self, symbol: str, timeframe: str = "1D", limit: int | None = None
    ) -> list[dict[str, object]]:
        self.calls.append((symbol, timeframe, limit))
        return self.bars_by_symbol.get(symbol, [])


class _FailingMarketData:
    async def get_bars(
        self, symbol: str, timeframe: str = "1D", limit: int | None = None
    ) -> list[dict[str, object]]:
        raise RuntimeError("market-data unavailable")


def _rising_bars(n: int, start: float = 100.0) -> list[dict[str, object]]:
    anchor = datetime(2024, 1, 1, tzinfo=UTC)
    return [
        {
            "timestamp": (anchor + timedelta(days=i)).isoformat(),
            "open": start + i,
            "high": start + i + 1,
            "low": start + i - 1,
            "close": start + i,
            "volume": 1_000_000,
        }
        for i in range(n)
    ]


async def test_preload_fetches_min_bars_at_session_timeframe() -> None:
    session = StrategySession(TREND_UP)
    md = _FakeMarketData({"SPY": _rising_bars(20)})

    primed = await preload_session_history(session, ["SPY"], "1Min", md)

    assert primed == 20
    assert md.calls == [("SPY", "1Min", session.min_bars + 10)]


async def test_preload_lets_session_trade_immediately() -> None:
    from llamatrade_runtime import Bar

    session = StrategySession(TREND_UP)
    md = _FakeMarketData({"SPY": _rising_bars(20)})
    await preload_session_history(session, ["SPY"], "1Min", md)

    next_ts = datetime(2024, 1, 21, tzinfo=UTC)
    orders = session.evaluate(
        {"SPY": Bar(timestamp=next_ts, open=120, high=121, low=119, close=120, volume=1_000_000)},
        {},
        100_000.0,
    )
    assert len(orders) == 1
    assert orders[0].side == "buy" and orders[0].symbol == "SPY"


async def test_preload_is_best_effort_on_fetch_failure() -> None:
    from llamatrade_runtime import Bar

    session = StrategySession(TREND_UP)

    primed = await preload_session_history(session, ["SPY"], "1Min", _FailingMarketData())

    assert primed == 0
    # Cold session: the first bar can't rebalance yet (insufficient history) -> no orders.
    first_ts = datetime(2024, 2, 1, tzinfo=UTC)
    orders = session.evaluate(
        {"SPY": Bar(timestamp=first_ts, open=100, high=101, low=99, close=100, volume=1_000_000)},
        {},
        100_000.0,
    )
    assert orders == []


async def test_preload_includes_indicator_only_symbols() -> None:
    # Strategy trades SPY but its condition reads QQQ -> QQQ must be preloaded too.
    config = (
        '(strategy "Cross" :rebalance daily '
        "(if (> (sma QQQ 3) (sma QQQ 5)) (asset SPY :weight 100) (else (asset SPY :weight 100))))"
    )
    session = StrategySession(config)
    md = _FakeMarketData({"SPY": _rising_bars(20), "QQQ": _rising_bars(20)})

    await preload_session_history(session, ["SPY"], "1Min", md)

    fetched = {sym for sym, _, _ in md.calls}
    assert fetched == {"SPY", "QQQ"}
