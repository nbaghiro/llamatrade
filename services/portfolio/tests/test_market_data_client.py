"""Market-data adapter tests — pure price extraction plus the client seams.

Covers the snapshot price fallback chain (trade → quote midpoint → daily close
→ latest close → miss), the omit-on-miss contract of ``get_prices`` (a missing
price must fall back to cost basis downstream, never mark to zero), and the
fail-soft empty results on transport errors.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, cast

import pytest

from llamatrade_proto.generated import market_data_pb2
from llamatrade_proto.timestamps import to_proto_timestamp

from src.clients.market_data import (
    MarketDataClient,
    _bar_close,
    _normalize_target,
    _snapshot_price,
    get_market_data_client,
)

D = Decimal


def _dec(value: str) -> Any:
    from llamatrade_proto.generated import common_pb2

    return common_pb2.Decimal(value=value)


def _bar(close: str | None) -> market_data_pb2.Bar:
    bar = market_data_pb2.Bar(symbol="SPY")
    if close is not None:
        bar.close.CopyFrom(_dec(close))
    return bar


# --- target normalization -----------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("market-data:8840", "http://market-data:8840"),
        ("http://market-data:8840", "http://market-data:8840"),
        ("https://md.example.com", "https://md.example.com"),
    ],
)
def test_normalize_target(raw: str, expected: str) -> None:
    assert _normalize_target(raw) == expected


def test_client_singleton_is_reused() -> None:
    assert get_market_data_client() is get_market_data_client()


# --- bar close ----------------------------------------------------------------


def test_bar_close_reads_the_close() -> None:
    assert _bar_close(_bar("480.25")) == D("480.25")


def test_bar_close_absent_is_zero() -> None:
    assert _bar_close(_bar(None)) == D("0")


def test_bar_close_zero_is_zero() -> None:
    assert _bar_close(_bar("0")) == D("0")


# --- snapshot price fallback chain --------------------------------------------


def test_snapshot_price_prefers_latest_trade() -> None:
    snapshot = market_data_pb2.Snapshot(
        latest_trade=market_data_pb2.Trade(price=_dec("101")),
        latest_quote=market_data_pb2.Quote(bid_price=_dec("99"), ask_price=_dec("100")),
        daily_bar=_bar("98"),
    )
    assert _snapshot_price(snapshot) == D("101")


def test_snapshot_price_zero_trade_falls_to_quote_midpoint() -> None:
    snapshot = market_data_pb2.Snapshot(
        latest_trade=market_data_pb2.Trade(price=_dec("0")),
        latest_quote=market_data_pb2.Quote(bid_price=_dec("99"), ask_price=_dec("101")),
    )
    assert _snapshot_price(snapshot) == D("100")


def test_snapshot_price_one_sided_quote_falls_to_daily_bar() -> None:
    snapshot = market_data_pb2.Snapshot(
        latest_quote=market_data_pb2.Quote(bid_price=_dec("99")),
        daily_bar=_bar("98"),
    )
    assert _snapshot_price(snapshot) == D("98")


def test_snapshot_price_zero_daily_falls_to_latest_bar() -> None:
    snapshot = market_data_pb2.Snapshot(daily_bar=_bar("0"), latest_bar=_bar("97.5"))
    assert _snapshot_price(snapshot) == D("97.5")


def test_snapshot_price_without_any_source_is_zero() -> None:
    assert _snapshot_price(market_data_pb2.Snapshot(symbol="SPY")) == D("0")


# --- get_prices / get_latest_price --------------------------------------------


class _FakeConnectClient:
    """Recorded stand-in for the generated Connect client (transport seam)."""

    def __init__(
        self,
        snapshots: dict[str, market_data_pb2.Snapshot] | None = None,
        bars: list[market_data_pb2.Bar] | None = None,
        *,
        fail: bool = False,
        delay: float = 0.0,
    ) -> None:
        self._delay = delay
        self._snapshots = snapshots or {}
        self._bars = bars or []
        self._fail = fail
        self.snapshot_requests: list[list[str]] = []
        self.bar_requests: list[market_data_pb2.GetHistoricalBarsRequest] = []
        self.headers_seen: list[dict[str, str]] = []

    async def get_snapshots(
        self, request: market_data_pb2.GetSnapshotsRequest, headers: dict[str, str]
    ) -> market_data_pb2.GetSnapshotsResponse:
        self.snapshot_requests.append(list(request.symbols))
        await asyncio.sleep(self._delay)
        if self._fail:
            raise ConnectionError("market-data unreachable")
        self.headers_seen.append(headers)
        response = market_data_pb2.GetSnapshotsResponse()
        for symbol, snapshot in self._snapshots.items():
            response.snapshots[symbol].CopyFrom(snapshot)
        return response

    async def get_historical_bars(
        self, request: market_data_pb2.GetHistoricalBarsRequest, headers: dict[str, str]
    ) -> market_data_pb2.GetHistoricalBarsResponse:
        self.bar_requests.append(request)
        await asyncio.sleep(self._delay)
        if self._fail:
            raise ConnectionError("market-data unreachable")
        return market_data_pb2.GetHistoricalBarsResponse(bars=self._bars)


class _Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def _client(
    fake: _FakeConnectClient, clock: _Clock | None = None, call_timeout: float = 5.0
) -> MarketDataClient:
    client = MarketDataClient(
        target="market-data:8840",
        price_ttl=15.0,
        closes_ttl=300.0,
        call_timeout=call_timeout,
        clock=clock or _Clock(),
    )
    client._client = cast(Any, fake)
    return client


def _priced(**prices: str) -> dict[str, market_data_pb2.Snapshot]:
    return {
        symbol: market_data_pb2.Snapshot(latest_trade=market_data_pb2.Trade(price=_dec(price)))
        for symbol, price in prices.items()
    }


async def test_get_prices_uppercases_and_maps_usable_prices() -> None:
    fake = _FakeConnectClient(
        snapshots={
            "AAPL": market_data_pb2.Snapshot(latest_trade=market_data_pb2.Trade(price=_dec("150")))
        }
    )
    prices = await _client(fake).get_prices(["aapl"])

    assert prices == {"AAPL": D("150")}
    assert fake.snapshot_requests == [["AAPL"]]
    assert "Authorization" in fake.headers_seen[0]  # service token attached


async def test_get_prices_omits_symbols_without_a_usable_price() -> None:
    """A priceless snapshot is OMITTED (not 0) so readers fall back to cost basis."""
    fake = _FakeConnectClient(
        snapshots={
            "AAPL": market_data_pb2.Snapshot(latest_trade=market_data_pb2.Trade(price=_dec("150"))),
            "GOOG": market_data_pb2.Snapshot(symbol="GOOG"),
        }
    )
    prices = await _client(fake).get_prices(["AAPL", "GOOG"])

    assert prices == {"AAPL": D("150")}
    assert "GOOG" not in prices


async def test_get_prices_empty_symbols_never_calls_the_service() -> None:
    fake = _FakeConnectClient()
    assert await _client(fake).get_prices([]) == {}
    assert fake.snapshot_requests == []


async def test_get_prices_transport_failure_returns_empty() -> None:
    assert await _client(_FakeConnectClient(fail=True)).get_prices(["AAPL"]) == {}


async def test_get_latest_price_returns_zero_on_miss() -> None:
    fake = _FakeConnectClient(
        snapshots={
            "AAPL": market_data_pb2.Snapshot(latest_trade=market_data_pb2.Trade(price=_dec("150")))
        }
    )
    client = _client(fake)
    assert await client.get_latest_price("aapl") == D("150")
    assert await client.get_latest_price("MSFT") == D("0")


# --- get_daily_closes ---------------------------------------------------------


async def test_get_daily_closes_keys_by_date() -> None:
    ts = datetime(2026, 6, 12, 20, 0, tzinfo=UTC)
    bar = _bar("480")
    bar.timestamp.CopyFrom(to_proto_timestamp(ts))
    closeless = market_data_pb2.Bar(symbol="SPY")
    closeless.timestamp.CopyFrom(to_proto_timestamp(ts))
    fake = _FakeConnectClient(bars=[bar, closeless])

    closes = await _client(fake).get_daily_closes(
        "spy", datetime(2026, 6, 1, tzinfo=UTC), datetime(2026, 6, 13, tzinfo=UTC)
    )

    assert closes == {datetime.fromtimestamp(ts.timestamp()).date(): 480.0}
    request = fake.bar_requests[0]
    assert request.symbol == "SPY"
    assert request.timeframe == market_data_pb2.TIMEFRAME_1DAY
    assert request.adjust_for_splits is True


async def test_get_daily_closes_transport_failure_returns_empty() -> None:
    closes = await _client(_FakeConnectClient(fail=True)).get_daily_closes(
        "SPY", datetime(2026, 6, 1, tzinfo=UTC), datetime(2026, 6, 13, tzinfo=UTC)
    )
    assert closes == {}


async def test_close_disposes_the_underlying_client() -> None:
    class _Closable(_FakeConnectClient):
        def __init__(self) -> None:
            super().__init__()
            self.closed = False

        async def close(self) -> None:
            self.closed = True

    fake = _Closable()
    client = _client(fake)
    await client.close()
    assert fake.closed is True
    assert client._client is None


# --- shared cache, single-flight, timeout --------------------------------------


async def test_concurrent_price_reads_share_one_fetch() -> None:
    """A dashboard fan-out (one request per strategy) makes one snapshot call, not N."""
    fake = _FakeConnectClient(snapshots=_priced(SPY="500", TLT="90"), delay=0.01)
    client = _client(fake)

    results = await asyncio.gather(*[client.get_prices(["SPY", "TLT"]) for _ in range(20)])

    assert fake.snapshot_requests == [["SPY", "TLT"]]
    assert all(r == {"SPY": D("500"), "TLT": D("90")} for r in results)


async def test_price_cache_fetches_only_new_symbols_and_expires() -> None:
    clock = _Clock()
    fake = _FakeConnectClient(snapshots=_priced(SPY="500", TLT="90"))
    client = _client(fake, clock)

    await client.get_prices(["SPY"])
    await client.get_prices(["SPY", "TLT"])
    clock.now = 14.0
    await client.get_prices(["SPY", "TLT"])
    clock.now = 16.0
    await client.get_prices(["TLT"])

    assert fake.snapshot_requests == [["SPY"], ["TLT"], ["TLT"]]


async def test_priceless_symbol_is_cached_as_a_miss() -> None:
    fake = _FakeConnectClient(snapshots=_priced(SPY="500"))
    client = _client(fake)

    assert await client.get_prices(["SPY", "GOOG"]) == {"SPY": D("500")}
    assert await client.get_prices(["GOOG"]) == {}
    assert fake.snapshot_requests == [["SPY", "GOOG"]]


async def test_failed_fetch_is_not_cached_and_reaches_every_waiter() -> None:
    fake = _FakeConnectClient(snapshots=_priced(SPY="500"), fail=True, delay=0.01)
    client = _client(fake)

    results = await asyncio.gather(*[client.get_prices(["SPY"]) for _ in range(5)])
    fake._fail = False
    retried = await client.get_prices(["SPY"])

    assert results == [{}] * 5
    assert fake.snapshot_requests == [["SPY"], ["SPY"]]
    assert retried == {"SPY": D("500")}


async def test_slow_market_data_times_out_to_empty() -> None:
    """A stalled upstream must not hold the caller (and its DB connection) past the bound."""
    fake = _FakeConnectClient(snapshots=_priced(SPY="500"), delay=1.0)
    client = _client(fake, call_timeout=0.05)

    started = asyncio.get_running_loop().time()
    prices = await client.get_prices(["SPY"])
    closes = await client.get_daily_closes(
        "SPY", datetime(2026, 6, 1, tzinfo=UTC), datetime(2026, 6, 13, tzinfo=UTC)
    )

    assert prices == {}
    assert closes == {}
    assert asyncio.get_running_loop().time() - started < 0.5


async def test_cancelled_loader_does_not_leave_waiters_hanging() -> None:
    fake = _FakeConnectClient(snapshots=_priced(SPY="500"), delay=0.2)
    client = _client(fake)

    leader = asyncio.create_task(client.get_prices(["SPY"]))
    await asyncio.sleep(0.01)
    follower = asyncio.create_task(client.get_prices(["SPY"]))
    await asyncio.sleep(0.01)
    leader.cancel()

    assert await asyncio.wait_for(follower, timeout=1.0) == {}
    assert await client.get_prices(["SPY"]) == {"SPY": D("500")}


async def test_concurrent_benchmark_reads_share_one_fetch_per_window() -> None:
    ts = datetime(2026, 6, 12, 20, 0, tzinfo=UTC)
    bar = _bar("480")
    bar.timestamp.CopyFrom(to_proto_timestamp(ts))
    fake = _FakeConnectClient(bars=[bar], delay=0.01)
    client = _client(fake)
    start, end = datetime(2026, 6, 1, 9, tzinfo=UTC), datetime(2026, 6, 13, tzinfo=UTC)
    other_start = datetime(2026, 6, 2, tzinfo=UTC)

    results = await asyncio.gather(
        *[client.get_daily_closes("SPY", start, end) for _ in range(10)],
        client.get_daily_closes("spy", start.replace(hour=15), end),
        client.get_daily_closes("SPY", other_start, end),
    )

    assert len(fake.bar_requests) == 2
    assert all(r == results[0] for r in results)
    results[0].clear()
    assert await client.get_daily_closes("SPY", start, end) != {}
