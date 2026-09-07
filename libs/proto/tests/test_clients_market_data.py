"""Tests for llamatrade_proto.clients.market_data against real generated messages."""

from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from llamatrade_proto.clients.market_data import (
    MarketDataClient,
    _timeframe_to_proto,
    _window_bound,
)
from llamatrade_proto.generated import common_pb2, market_data_pb2

# 2024-01-15T12:00:00Z; decoded bar timestamps must be UTC-aware.
BAR_SECONDS = 1705320000
BAR_DT = datetime(2024, 1, 15, 12, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _service_token() -> Iterator[None]:
    """Stub the minted service token; header assembly itself stays real."""
    with patch("llamatrade_common.auth.mint_service_token", return_value="svc-token"):
        yield


def _pb_bar(symbol: str = "AAPL", close: str = "151.00") -> market_data_pb2.Bar:
    return market_data_pb2.Bar(
        symbol=symbol,
        timestamp=common_pb2.Timestamp(seconds=BAR_SECONDS),
        open=common_pb2.Decimal(value="150.00"),
        high=common_pb2.Decimal(value="152.50"),
        low=common_pb2.Decimal(value="149.50"),
        close=common_pb2.Decimal(value=close),
        volume=1000,
    )


def _pb_quote(bid: str = "150.00", ask: str = "150.05") -> market_data_pb2.Quote:
    return market_data_pb2.Quote(
        symbol="AAPL",
        timestamp=common_pb2.Timestamp(seconds=BAR_SECONDS),
        bid_price=common_pb2.Decimal(value=bid),
        bid_size=100,
        ask_price=common_pb2.Decimal(value=ask),
        ask_size=200,
    )


def _pb_trade(price: str = "150.50", exchange: str = "") -> market_data_pb2.Trade:
    return market_data_pb2.Trade(
        symbol="AAPL",
        timestamp=common_pb2.Timestamp(seconds=BAR_SECONDS),
        price=common_pb2.Decimal(value=price),
        size=100,
        exchange=exchange,
    )


def _connect_client(client: MarketDataClient) -> MagicMock:
    """Attach a mock Connect client; return the mock."""
    conn = MagicMock()
    conn.close = AsyncMock()
    client._client = conn
    return conn


class TestWindowBound:
    """Tests for the _window_bound timestamp encoder."""

    def test_aware_utc_input_encodes_exact_instant(self) -> None:
        assert _window_bound(datetime(2024, 1, 1, tzinfo=UTC)).seconds == 1704067200

    def test_naive_input_is_host_local_wall_time(self) -> None:
        naive = datetime(2024, 1, 15, 12, 0, 0)
        assert _window_bound(naive).seconds == int(naive.astimezone().timestamp())


class TestTimeframeToProto:
    """Tests for the timeframe string mapping."""

    @pytest.mark.parametrize(
        ("timeframe", "expected"),
        [
            ("1MIN", market_data_pb2.TIMEFRAME_1MIN),
            ("1min", market_data_pb2.TIMEFRAME_1MIN),
            ("15MIN", market_data_pb2.TIMEFRAME_15MIN),
            ("1HOUR", market_data_pb2.TIMEFRAME_1HOUR),
            ("1DAY", market_data_pb2.TIMEFRAME_1DAY),
            ("1D", market_data_pb2.TIMEFRAME_1DAY),
            ("1WEEK", market_data_pb2.TIMEFRAME_1WEEK),
        ],
    )
    def test_known_values(
        self, timeframe: str, expected: market_data_pb2.Timeframe.ValueType
    ) -> None:
        assert _timeframe_to_proto(timeframe) == expected

    def test_unknown_value_falls_back_to_daily(self) -> None:
        assert _timeframe_to_proto("2SEC") == market_data_pb2.TIMEFRAME_1DAY


class TestMarketDataClientInit:
    """Tests for MarketDataClient initialization (Connect client)."""

    def test_init_with_defaults(self) -> None:
        """Bare host:port is normalized to an absolute URL; lazy client."""
        client = MarketDataClient()
        assert client.target == "http://market-data:8840"
        assert client._service_name == "internal"
        assert client._client is None

    def test_init_with_custom_target(self) -> None:
        client = MarketDataClient("localhost:9000")
        assert client.target == "http://localhost:9000"

    def test_init_preserves_absolute_url(self) -> None:
        client = MarketDataClient("https://market-data.internal")
        assert client.target == "https://market-data.internal"

    def test_init_with_service_name(self) -> None:
        client = MarketDataClient(service_name="backtest")
        assert client._service_name == "backtest"


class TestMarketDataClientLifecycle:
    """Tests for lazy client creation and close."""

    async def test_get_client_is_lazy_and_cached(self) -> None:
        client = MarketDataClient()
        conn = client._get_client()
        assert client._get_client() is conn
        await client.close()
        assert client._client is None

    async def test_close_closes_underlying_client(self) -> None:
        client = MarketDataClient()
        conn = _connect_client(client)

        await client.close()

        conn.close.assert_awaited_once()
        assert client._client is None

    async def test_close_without_client_is_safe(self) -> None:
        await MarketDataClient().close()

    async def test_context_manager_closes(self) -> None:
        client = MarketDataClient()
        conn = _connect_client(client)

        async with client as entered:
            assert entered is client

        conn.close.assert_awaited_once()


class TestGetHistoricalBars:
    """Tests for MarketDataClient.get_historical_bars (Connect)."""

    async def test_success_decodes_bars(self) -> None:
        client = MarketDataClient()
        conn = _connect_client(client)
        conn.get_historical_bars = AsyncMock(
            return_value=market_data_pb2.GetHistoricalBarsResponse(bars=[_pb_bar("AAPL", "151.00")])
        )

        result = await client.get_historical_bars(
            symbol="AAPL",
            start=datetime(2024, 1, 1, tzinfo=UTC),
            end=datetime(2024, 1, 31, tzinfo=UTC),
            timeframe="1D",
        )

        assert len(result) == 1
        assert result[0].symbol == "AAPL"
        assert result[0].close == Decimal("151.00")
        assert result[0].timestamp == BAR_DT
        conn.get_historical_bars.assert_awaited_once()

    async def test_request_encoding_and_auth_header(self) -> None:
        client = MarketDataClient()
        conn = _connect_client(client)
        conn.get_historical_bars = AsyncMock(
            return_value=market_data_pb2.GetHistoricalBarsResponse()
        )
        start = datetime(2024, 1, 1, tzinfo=UTC)
        end = datetime(2024, 1, 31, 12, 30, tzinfo=UTC)

        result = await client.get_historical_bars(symbol="AAPL", start=start, end=end)

        assert result == []
        request = conn.get_historical_bars.call_args[0][0]
        assert request.symbol == "AAPL"
        assert request.start.seconds == int(start.timestamp())
        assert request.end.seconds == int(end.timestamp())
        assert request.timeframe == market_data_pb2.TIMEFRAME_1DAY
        assert request.adjust_for_splits is True
        assert request.pagination.page_size == 1000
        kwargs = conn.get_historical_bars.call_args.kwargs
        assert kwargs["headers"]["Authorization"] == "Bearer svc-token"
        assert kwargs["timeout_ms"] == 30000

    async def test_naive_window_bounds_encode_host_local_instant(self) -> None:
        client = MarketDataClient()
        conn = _connect_client(client)
        conn.get_historical_bars = AsyncMock(
            return_value=market_data_pb2.GetHistoricalBarsResponse()
        )
        naive_start = datetime(2024, 1, 1, 9, 30)
        naive_end = datetime(2024, 1, 2, 16, 0)

        await client.get_historical_bars(symbol="AAPL", start=naive_start, end=naive_end)

        request = conn.get_historical_bars.call_args[0][0]
        assert request.start.seconds == int(naive_start.astimezone().timestamp())
        assert request.end.seconds == int(naive_end.astimezone().timestamp())


class TestGetMultiBars:
    """Tests for MarketDataClient.get_multi_bars (batched fetch, 16B)."""

    async def test_success_decodes_per_symbol_lists(self) -> None:
        client = MarketDataClient()
        conn = _connect_client(client)
        conn.get_multi_bars = AsyncMock(
            return_value=market_data_pb2.GetMultiBarsResponse(
                bars={
                    "AAPL": market_data_pb2.BarList(bars=[_pb_bar("AAPL", "150.00")]),
                    "SPY": market_data_pb2.BarList(bars=[_pb_bar("SPY", "400.00")]),
                }
            )
        )

        result = await client.get_multi_bars(
            symbols=["AAPL", "SPY"],
            start=datetime(2024, 1, 1, tzinfo=UTC),
            end=datetime(2024, 1, 31, tzinfo=UTC),
            timeframe="1D",
            limit=5000,
        )

        assert set(result) == {"AAPL", "SPY"}
        assert result["AAPL"][0].close == Decimal("150.00")
        assert result["SPY"][0].close == Decimal("400.00")
        request = conn.get_multi_bars.call_args[0][0]
        assert list(request.symbols) == ["AAPL", "SPY"]
        assert request.limit == 5000
        assert request.start.seconds == 1704067200


class TestStreamHistoricalBars:
    """Tests for MarketDataClient.stream_historical_bars (streamed batch, 13B)."""

    async def test_yields_bars_and_encodes_request(self) -> None:
        client = MarketDataClient()
        conn = _connect_client(client)
        captured: list[market_data_pb2.StreamHistoricalBarsRequest] = []

        def fake_stream(
            request: market_data_pb2.StreamHistoricalBarsRequest,
            *,
            headers: dict[str, str] | None = None,
        ) -> AsyncIterator[market_data_pb2.Bar]:
            captured.append(request)

            async def _gen() -> AsyncIterator[market_data_pb2.Bar]:
                yield _pb_bar("AAPL", "150.00")
                yield _pb_bar("SPY", "400.00")

            return _gen()

        conn.stream_historical_bars = fake_stream

        out = [
            bar
            async for bar in client.stream_historical_bars(
                symbols=["AAPL", "SPY"],
                start=datetime(2024, 1, 1, tzinfo=UTC),
                end=datetime(2024, 1, 31, tzinfo=UTC),
                timeframe="1D",
                limit=100,
            )
        ]

        assert [bar.symbol for bar in out] == ["AAPL", "SPY"]
        assert out[0].close == Decimal("150.00")
        assert list(captured[0].symbols) == ["AAPL", "SPY"]
        assert captured[0].limit == 100
        assert captured[0].start.seconds == 1704067200
        assert captured[0].timeframe == market_data_pb2.TIMEFRAME_1DAY


class TestRealtimeStreams:
    """Tests for the real-time stream_bars/stream_quotes/stream_trades wrappers."""

    async def test_stream_bars_maps_timeframe_and_yields(self) -> None:
        client = MarketDataClient()
        conn = _connect_client(client)
        captured: list[market_data_pb2.StreamBarsRequest] = []

        def fake_stream(
            request: market_data_pb2.StreamBarsRequest,
            *,
            headers: dict[str, str] | None = None,
        ) -> AsyncIterator[market_data_pb2.Bar]:
            captured.append(request)

            async def _gen() -> AsyncIterator[market_data_pb2.Bar]:
                yield _pb_bar("AAPL", "151.00")

            return _gen()

        conn.stream_bars = fake_stream

        out = [bar async for bar in client.stream_bars(["AAPL"], timeframe="5MIN")]

        assert out[0].symbol == "AAPL"
        assert out[0].timestamp == BAR_DT
        assert captured[0].timeframe == market_data_pb2.TIMEFRAME_5MIN

    async def test_stream_bars_unknown_timeframe_falls_back_to_1min(self) -> None:
        client = MarketDataClient()
        conn = _connect_client(client)
        captured: list[market_data_pb2.StreamBarsRequest] = []

        def fake_stream(
            request: market_data_pb2.StreamBarsRequest,
            *,
            headers: dict[str, str] | None = None,
        ) -> AsyncIterator[market_data_pb2.Bar]:
            captured.append(request)

            async def _gen() -> AsyncIterator[market_data_pb2.Bar]:
                return
                yield

            return _gen()

        conn.stream_bars = fake_stream

        assert [bar async for bar in client.stream_bars(["AAPL"], timeframe="1DAY")] == []
        assert captured[0].timeframe == market_data_pb2.TIMEFRAME_1MIN

    async def test_stream_quotes_yields_quotes(self) -> None:
        client = MarketDataClient()
        conn = _connect_client(client)

        def fake_stream(
            request: market_data_pb2.StreamQuotesRequest,
            *,
            headers: dict[str, str] | None = None,
        ) -> AsyncIterator[market_data_pb2.Quote]:
            async def _gen() -> AsyncIterator[market_data_pb2.Quote]:
                yield _pb_quote()

            return _gen()

        conn.stream_quotes = fake_stream

        out = [quote async for quote in client.stream_quotes(["AAPL"])]

        assert out[0].bid_price == Decimal("150.00")
        assert out[0].ask_price == Decimal("150.05")

    async def test_stream_trades_yields_trades(self) -> None:
        client = MarketDataClient()
        conn = _connect_client(client)

        def fake_stream(
            request: market_data_pb2.StreamTradesRequest,
            *,
            headers: dict[str, str] | None = None,
        ) -> AsyncIterator[market_data_pb2.Trade]:
            async def _gen() -> AsyncIterator[market_data_pb2.Trade]:
                yield _pb_trade(exchange="NASDAQ")

            return _gen()

        conn.stream_trades = fake_stream

        out = [trade async for trade in client.stream_trades(["AAPL"])]

        assert out[0].price == Decimal("150.50")
        assert out[0].exchange == "NASDAQ"


class TestSnapshots:
    """Tests for get_snapshot(s) and the latest-price extraction."""

    async def test_get_snapshot_decodes_and_uses_read_timeout(self) -> None:
        client = MarketDataClient()
        conn = _connect_client(client)
        conn.get_snapshot = AsyncMock(
            return_value=market_data_pb2.Snapshot(symbol="AAPL", latest_trade=_pb_trade("150.50"))
        )

        snapshot = await client.get_snapshot("AAPL")

        assert snapshot.symbol == "AAPL"
        assert snapshot.latest_price == Decimal("150.50")
        assert conn.get_snapshot.call_args[0][0].symbol == "AAPL"
        assert conn.get_snapshot.call_args.kwargs["timeout_ms"] == 5000

    async def test_get_snapshots_decodes_map(self) -> None:
        client = MarketDataClient()
        conn = _connect_client(client)
        conn.get_snapshots = AsyncMock(
            return_value=market_data_pb2.GetSnapshotsResponse(
                snapshots={
                    "AAPL": market_data_pb2.Snapshot(
                        symbol="AAPL", latest_trade=_pb_trade("150.50")
                    ),
                    "SPY": market_data_pb2.Snapshot(
                        symbol="SPY", latest_quote=_pb_quote("400.00", "400.10")
                    ),
                }
            )
        )

        snapshots = await client.get_snapshots(["AAPL", "SPY"])

        assert snapshots["AAPL"].latest_price == Decimal("150.50")
        assert snapshots["SPY"].latest_price == Decimal("400.05")
        assert list(conn.get_snapshots.call_args[0][0].symbols) == ["AAPL", "SPY"]

    async def test_get_latest_price(self) -> None:
        client = MarketDataClient()
        conn = _connect_client(client)
        conn.get_snapshot = AsyncMock(
            return_value=market_data_pb2.Snapshot(symbol="AAPL", latest_trade=_pb_trade("150.50"))
        )

        assert await client.get_latest_price("AAPL") == Decimal("150.50")

    async def test_get_latest_prices(self) -> None:
        client = MarketDataClient()
        conn = _connect_client(client)
        conn.get_snapshots = AsyncMock(
            return_value=market_data_pb2.GetSnapshotsResponse(
                snapshots={
                    "AAPL": market_data_pb2.Snapshot(
                        symbol="AAPL", latest_trade=_pb_trade("150.50")
                    )
                }
            )
        )

        assert await client.get_latest_prices(["AAPL"]) == {"AAPL": Decimal("150.50")}


class TestProtoToSnapshot:
    """Preference order: trade price, then quote midpoint, then bar close."""

    def test_trade_price_wins_over_quote_and_bar(self) -> None:
        snapshot = MarketDataClient()._proto_to_snapshot(
            market_data_pb2.Snapshot(
                symbol="AAPL",
                latest_trade=_pb_trade("150.50"),
                latest_quote=_pb_quote("150.00", "150.10"),
                latest_bar=_pb_bar("AAPL", "149.00"),
            )
        )

        assert snapshot.latest_price == Decimal("150.50")
        assert snapshot.bid_price == Decimal("150.00")
        assert snapshot.ask_price == Decimal("150.10")

    def test_quote_midpoint_when_no_trade(self) -> None:
        snapshot = MarketDataClient()._proto_to_snapshot(
            market_data_pb2.Snapshot(
                symbol="AAPL",
                latest_quote=_pb_quote("150.00", "150.10"),
                latest_bar=_pb_bar("AAPL", "149.00"),
            )
        )

        assert snapshot.latest_price == Decimal("150.05")

    def test_bar_close_when_quote_is_one_sided(self) -> None:
        quote = market_data_pb2.Quote(
            symbol="AAPL",
            timestamp=common_pb2.Timestamp(seconds=BAR_SECONDS),
            bid_price=common_pb2.Decimal(value="150.00"),
            bid_size=100,
        )
        snapshot = MarketDataClient()._proto_to_snapshot(
            market_data_pb2.Snapshot(
                symbol="AAPL", latest_quote=quote, latest_bar=_pb_bar("AAPL", "149.00")
            )
        )

        assert snapshot.latest_price == Decimal("149.00")
        assert snapshot.bid_price == Decimal("150.00")
        assert snapshot.ask_price is None

    def test_bar_close_when_no_trade_or_quote(self) -> None:
        snapshot = MarketDataClient()._proto_to_snapshot(
            market_data_pb2.Snapshot(symbol="AAPL", latest_bar=_pb_bar("AAPL", "149.00"))
        )

        assert snapshot.latest_price == Decimal("149.00")
        assert snapshot.latest_bar is not None
        assert snapshot.latest_bar.close == Decimal("149.00")

    def test_empty_snapshot_defaults(self) -> None:
        snapshot = MarketDataClient()._proto_to_snapshot(market_data_pb2.Snapshot(symbol="AAPL"))

        assert snapshot.latest_price == Decimal(0)
        assert snapshot.bid_price is None
        assert snapshot.ask_price is None
        assert snapshot.latest_bar is None
        assert snapshot.change is None
        assert snapshot.change_percent is None

    def test_change_fields_decoded(self) -> None:
        snapshot = MarketDataClient()._proto_to_snapshot(
            market_data_pb2.Snapshot(
                symbol="AAPL",
                latest_trade=_pb_trade("150.50"),
                change=common_pb2.Decimal(value="1.25"),
                change_percent=common_pb2.Decimal(value="0.84"),
            )
        )

        assert snapshot.change == Decimal("1.25")
        assert snapshot.change_percent == Decimal("0.84")


class TestProtoToBar:
    """Tests for _proto_to_bar conversion."""

    def test_full_bar_with_vwap_and_trade_count(self) -> None:
        proto_bar = _pb_bar("AAPL", "151.00")
        proto_bar.trade_count = 5000
        proto_bar.vwap.CopyFrom(common_pb2.Decimal(value="150.50"))

        bar = MarketDataClient()._proto_to_bar(proto_bar)

        assert bar.symbol == "AAPL"
        assert bar.timestamp == BAR_DT
        assert bar.timestamp.tzinfo is UTC
        assert bar.open == Decimal("150.00")
        assert bar.close == Decimal("151.00")
        assert bar.volume == 1000
        assert bar.trade_count == 5000
        assert bar.vwap == Decimal("150.50")

    def test_unset_fields_default(self) -> None:
        proto_bar = market_data_pb2.Bar(
            symbol="AAPL", timestamp=common_pb2.Timestamp(seconds=BAR_SECONDS), volume=0
        )

        bar = MarketDataClient()._proto_to_bar(proto_bar)

        assert bar.open == Decimal(0)
        assert bar.high == Decimal(0)
        assert bar.low == Decimal(0)
        assert bar.close == Decimal(0)
        assert bar.volume == 0
        assert bar.trade_count is None
        assert bar.vwap is None


class TestProtoToQuote:
    """Tests for _proto_to_quote conversion."""

    def test_decodes_quote(self) -> None:
        quote = MarketDataClient()._proto_to_quote(_pb_quote())

        assert quote.symbol == "AAPL"
        assert quote.timestamp == BAR_DT
        assert quote.bid_price == Decimal("150.00")
        assert quote.bid_size == 100
        assert quote.ask_price == Decimal("150.05")
        assert quote.ask_size == 200


class TestProtoToTrade:
    """Tests for _proto_to_trade conversion."""

    def test_with_exchange(self) -> None:
        trade = MarketDataClient()._proto_to_trade(_pb_trade(exchange="NASDAQ"))

        assert trade.price == Decimal("150.50")
        assert trade.size == 100
        assert trade.timestamp == BAR_DT
        assert trade.exchange == "NASDAQ"

    def test_without_exchange(self) -> None:
        trade = MarketDataClient()._proto_to_trade(_pb_trade())

        assert trade.exchange is None
