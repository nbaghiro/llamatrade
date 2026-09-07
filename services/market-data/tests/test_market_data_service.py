"""Tests for MarketDataService with caching."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import cast
from unittest.mock import AsyncMock

import pytest

from llamatrade_alpaca import MarketDataClient
from tests.fakes import FakeMarketDataClient

from src.cache import MarketDataCache
from src.models import Snapshot, Timeframe, Trade
from src.services.market_data_service import MarketDataService
from src.store.models import BarRow
from src.store.repository import BarStore


class TestGetBars:
    """Tests for get_bars method."""

    @pytest.mark.asyncio
    async def test_cache_miss_fetches_from_alpaca(
        self, mock_alpaca_client, mock_cache, sample_bars
    ):
        """Test that cache miss fetches from Alpaca and caches result."""
        mock_alpaca_client.get_bars.return_value = sample_bars
        service = MarketDataService(alpaca=mock_alpaca_client, cache=mock_cache)

        result = await service.get_bars(
            symbol="AAPL",
            timeframe=Timeframe.DAY_1,
            start=datetime(2024, 1, 1, tzinfo=UTC),
            end=datetime(2024, 1, 31, tzinfo=UTC),
            limit=1000,
        )

        assert len(result) == 3
        mock_alpaca_client.get_bars.assert_called_once()

    @pytest.mark.asyncio
    async def test_cache_hit_skips_alpaca(
        self, mock_alpaca_client, mock_cache, mock_redis, sample_bars
    ):
        """Test that cache hit returns cached data without calling Alpaca."""
        # Setup cache to return data
        cached_data = MarketDataCache.serialize_model_list(sample_bars)
        mock_redis.get.return_value = cached_data.encode()

        service = MarketDataService(alpaca=mock_alpaca_client, cache=mock_cache)

        result = await service.get_bars(
            symbol="AAPL",
            timeframe=Timeframe.DAY_1,
            start=datetime(2024, 1, 1, tzinfo=UTC),
            end=datetime(2024, 1, 31, tzinfo=UTC),
            limit=1000,
        )

        assert len(result) == 3
        mock_alpaca_client.get_bars.assert_not_called()

    @pytest.mark.asyncio
    async def test_refresh_bypasses_cache(
        self, mock_alpaca_client, mock_cache, mock_redis, sample_bars
    ):
        """Test that refresh=True bypasses cache."""
        # Setup cache with data
        cached_data = MarketDataCache.serialize_model_list(sample_bars)
        mock_redis.get.return_value = cached_data.encode()
        mock_alpaca_client.get_bars.return_value = sample_bars

        service = MarketDataService(alpaca=mock_alpaca_client, cache=mock_cache)

        await service.get_bars(
            symbol="AAPL",
            timeframe=Timeframe.DAY_1,
            start=datetime(2024, 1, 1, tzinfo=UTC),
            end=datetime(2024, 1, 31, tzinfo=UTC),
            limit=1000,
            refresh=True,
        )

        # Should call Alpaca even with cache populated
        mock_alpaca_client.get_bars.assert_called_once()
        # Should NOT check cache
        mock_redis.get.assert_not_called()

    @pytest.mark.asyncio
    async def test_works_without_cache(self, mock_alpaca_client, sample_bars):
        """Test that service works when cache is None."""
        mock_alpaca_client.get_bars.return_value = sample_bars
        service = MarketDataService(alpaca=mock_alpaca_client, cache=None)

        result = await service.get_bars(
            symbol="AAPL",
            timeframe=Timeframe.DAY_1,
            start=datetime(2024, 1, 1, tzinfo=UTC),
            limit=1000,
        )

        assert len(result) == 3
        mock_alpaca_client.get_bars.assert_called_once()


class TestGetMultiBars:
    """Tests for get_multi_bars method."""

    @pytest.mark.asyncio
    async def test_fetches_uncached_symbols_only(
        self, mock_alpaca_client, mock_cache, mock_redis, sample_bars
    ):
        """Test that only uncached symbols are fetched from Alpaca (using batch mget)."""

        # AAPL is cached, TSLA is not - use mget for batch lookup
        def mock_mget(keys):
            result = []
            for key in keys:
                if "AAPL" in key:
                    result.append(MarketDataCache.serialize_model_list(sample_bars).encode())
                else:
                    result.append(None)
            return result

        mock_redis.mget = AsyncMock(side_effect=mock_mget)
        mock_alpaca_client.get_multi_bars.return_value = {"TSLA": sample_bars[:2]}

        service = MarketDataService(alpaca=mock_alpaca_client, cache=mock_cache)

        result = await service.get_multi_bars(
            symbols=["AAPL", "TSLA"],
            timeframe=Timeframe.DAY_1,
            start=datetime(2024, 1, 1, tzinfo=UTC),
            limit=1000,
        )

        assert "AAPL" in result
        assert "TSLA" in result
        assert len(result["AAPL"]) == 3  # From cache
        assert len(result["TSLA"]) == 2  # From Alpaca

        # Alpaca should only be called for TSLA
        mock_alpaca_client.get_multi_bars.assert_called_once()
        call_args = mock_alpaca_client.get_multi_bars.call_args
        assert call_args.kwargs["symbols"] == ["TSLA"]

        # Should use mget (batch) instead of individual get calls
        mock_redis.mget.assert_called_once()


class TestGetLatestBar:
    """Tests for get_latest_bar method."""

    @pytest.mark.asyncio
    async def test_cache_hit(self, mock_alpaca_client, mock_cache, mock_redis, sample_bar):
        """Test cache hit for latest bar."""
        cached_data = MarketDataCache.serialize_model(sample_bar)
        mock_redis.get.return_value = cached_data.encode()

        service = MarketDataService(alpaca=mock_alpaca_client, cache=mock_cache)

        result = await service.get_latest_bar(symbol="AAPL")

        assert result is not None
        assert result.close == sample_bar.close
        mock_alpaca_client.get_latest_bar.assert_not_called()

    @pytest.mark.asyncio
    async def test_cache_miss(self, mock_alpaca_client, mock_cache, sample_bar):
        """Test cache miss for latest bar."""
        mock_alpaca_client.get_latest_bar.return_value = sample_bar

        service = MarketDataService(alpaca=mock_alpaca_client, cache=mock_cache)

        result = await service.get_latest_bar(symbol="AAPL")

        assert result is not None
        assert result.close == sample_bar.close
        mock_alpaca_client.get_latest_bar.assert_called_once()


class TestGetLatestQuote:
    """Tests for get_latest_quote method."""

    @pytest.mark.asyncio
    async def test_cache_hit(self, mock_alpaca_client, mock_cache, mock_redis, sample_quote):
        """Test cache hit for latest quote."""
        cached_data = MarketDataCache.serialize_model(sample_quote)
        mock_redis.get.return_value = cached_data.encode()

        service = MarketDataService(alpaca=mock_alpaca_client, cache=mock_cache)

        result = await service.get_latest_quote(symbol="AAPL")

        assert result is not None
        assert result.bid_price == sample_quote.bid_price
        mock_alpaca_client.get_latest_quote.assert_not_called()

    @pytest.mark.asyncio
    async def test_cache_miss(self, mock_alpaca_client, mock_cache, sample_quote):
        """Test cache miss for latest quote."""
        mock_alpaca_client.get_latest_quote.return_value = sample_quote

        service = MarketDataService(alpaca=mock_alpaca_client, cache=mock_cache)

        result = await service.get_latest_quote(symbol="AAPL")

        assert result is not None
        assert result.bid_price == sample_quote.bid_price
        mock_alpaca_client.get_latest_quote.assert_called_once()


class TestGetSnapshot:
    """Tests for get_snapshot method."""

    @pytest.mark.asyncio
    async def test_cache_hit(self, mock_alpaca_client, mock_cache, mock_redis, sample_snapshot):
        """Test cache hit for snapshot."""
        cached_data = MarketDataCache.serialize_model(sample_snapshot)
        mock_redis.get.return_value = cached_data.encode()

        service = MarketDataService(alpaca=mock_alpaca_client, cache=mock_cache)

        result = await service.get_snapshot(symbol="AAPL")

        assert result is not None
        assert result.symbol == sample_snapshot.symbol
        mock_alpaca_client.get_snapshot.assert_not_called()

    @pytest.mark.asyncio
    async def test_cache_miss(self, mock_alpaca_client, mock_cache, sample_snapshot):
        """Test cache miss for snapshot."""
        mock_alpaca_client.get_snapshot.return_value = sample_snapshot

        service = MarketDataService(alpaca=mock_alpaca_client, cache=mock_cache)

        result = await service.get_snapshot(symbol="AAPL")

        assert result is not None
        assert result.symbol == sample_snapshot.symbol
        mock_alpaca_client.get_snapshot.assert_called_once()

    @pytest.mark.asyncio
    async def test_concurrent_misses_coalesce_to_one_fetch(
        self, mock_alpaca_client, sample_snapshot
    ):
        """Concurrent cache misses for one symbol coalesce into a single upstream call."""
        import asyncio

        gate = asyncio.Event()
        calls = 0

        async def slow_snapshot(*, symbol: str) -> Snapshot:
            nonlocal calls
            calls += 1
            await gate.wait()
            return sample_snapshot

        mock_alpaca_client.get_snapshot = slow_snapshot
        service = MarketDataService(alpaca=mock_alpaca_client, cache=None)

        tasks = [asyncio.create_task(service.get_snapshot(symbol="AAPL")) for _ in range(5)]
        await asyncio.sleep(0.01)  # let every task register on the in-flight fill
        gate.set()
        results = await asyncio.gather(*tasks)

        assert calls == 1
        assert all(r is sample_snapshot for r in results)


class TestGetMultiSnapshots:
    """Tests for get_multi_snapshots method."""

    @pytest.mark.asyncio
    async def test_fetches_uncached_symbols_only(
        self, mock_alpaca_client, mock_cache, mock_redis, sample_snapshot
    ):
        """Test that only uncached symbols are fetched from Alpaca (using batch mget)."""

        # AAPL is cached, TSLA is not - use mget for batch lookup
        def mock_mget(keys):
            result = []
            for key in keys:
                if "AAPL" in key:
                    result.append(MarketDataCache.serialize_model(sample_snapshot).encode())
                else:
                    result.append(None)
            return result

        mock_redis.mget = AsyncMock(side_effect=mock_mget)

        tsla_snapshot = Snapshot(symbol="TSLA")
        mock_alpaca_client.get_multi_snapshots.return_value = {"TSLA": tsla_snapshot}

        service = MarketDataService(alpaca=mock_alpaca_client, cache=mock_cache)

        result = await service.get_multi_snapshots(symbols=["AAPL", "TSLA"])

        assert "AAPL" in result
        assert "TSLA" in result
        assert result["AAPL"].symbol == "AAPL"
        assert result["TSLA"].symbol == "TSLA"

        # Alpaca should only be called for TSLA
        mock_alpaca_client.get_multi_snapshots.assert_called_once()
        call_args = mock_alpaca_client.get_multi_snapshots.call_args
        assert call_args.kwargs["symbols"] == ["TSLA"]

        # Should use mget (batch) instead of individual get calls
        mock_redis.mget.assert_called_once()


def _daily_row(symbol: str, day: int, close: float) -> BarRow:
    return BarRow(
        symbol=symbol,
        time=datetime.now(UTC) - timedelta(days=day),
        open=Decimal("100"),
        high=Decimal("101"),
        low=Decimal("99"),
        close=Decimal(str(close)),
        volume=1000,
        vwap=None,
        trade_count=None,
    )


class SnapshotStore:
    """Store double serving canned daily rows for the snapshot fallback path."""

    def __init__(
        self, rows_by_symbol: dict[str, list[BarRow]] | None = None, *, fails: bool = False
    ) -> None:
        self.rows_by_symbol = rows_by_symbol or {}
        self.fails = fails
        self.selects: list[str] = []

    async def select_bars(
        self, symbol: str, timeframe: str, start: datetime, end: datetime
    ) -> list[BarRow]:
        self.selects.append(symbol)
        if self.fails:
            raise RuntimeError("store down")
        return list(self.rows_by_symbol.get(symbol, []))


def _service(
    alpaca: FakeMarketDataClient, store: SnapshotStore, cache: MarketDataCache | None = None
) -> MarketDataService:
    return MarketDataService(
        alpaca=cast(MarketDataClient, alpaca), cache=cache, store=cast(BarStore, store)
    )


class TestSnapshotStoreFallback:
    """Alpaca-failure tier: snapshots degrade to the last stored daily bars."""

    async def test_alpaca_failure_falls_back_to_store(self) -> None:
        alpaca = FakeMarketDataClient(fail_snapshot_symbols={"AAPL"})
        store = SnapshotStore(
            {"AAPL": [_daily_row("AAPL", 2, 150.0), _daily_row("AAPL", 1, 151.0)]}
        )

        result = await _service(alpaca, store).get_snapshot("AAPL")

        assert result is not None
        assert result.symbol == "AAPL"
        assert result.latest_trade is not None
        assert result.latest_trade.price == 151.0  # last stored close
        assert result.daily_bar is not None and result.daily_bar.close == 151.0
        assert result.prev_daily_bar is not None and result.prev_daily_bar.close == 150.0
        assert store.selects == ["AAPL"]

    async def test_alpaca_none_result_also_falls_back_to_store(self) -> None:
        alpaca = FakeMarketDataClient()  # no snapshots configured -> returns None
        store = SnapshotStore({"AAPL": [_daily_row("AAPL", 1, 151.0)]})

        result = await _service(alpaca, store).get_snapshot("AAPL")

        assert result is not None
        assert result.latest_trade is not None and result.latest_trade.price == 151.0
        assert result.prev_daily_bar is None  # single stored row

    async def test_empty_store_yields_none(self) -> None:
        alpaca = FakeMarketDataClient(fail_snapshot_symbols={"AAPL"})
        result = await _service(alpaca, SnapshotStore()).get_snapshot("AAPL")
        assert result is None

    async def test_store_failure_yields_none_not_exception(self) -> None:
        alpaca = FakeMarketDataClient(fail_snapshot_symbols={"AAPL"})
        result = await _service(alpaca, SnapshotStore(fails=True)).get_snapshot("AAPL")
        assert result is None

    async def test_no_store_configured_yields_none_on_alpaca_failure(self) -> None:
        alpaca = FakeMarketDataClient(fail_snapshot_symbols={"AAPL"})
        service = MarketDataService(alpaca=cast(MarketDataClient, alpaca), cache=None, store=None)
        assert await service.get_snapshot("AAPL") is None

    async def test_store_snapshot_is_cached(self, mock_cache, mock_redis) -> None:
        alpaca = FakeMarketDataClient(fail_snapshot_symbols={"AAPL"})
        store = SnapshotStore({"AAPL": [_daily_row("AAPL", 1, 151.0)]})

        result = await _service(alpaca, store, cache=mock_cache).get_snapshot("AAPL")

        assert result is not None
        mock_redis.setex.assert_called_once()
        assert "market:snapshot:AAPL" in mock_redis.setex.call_args.args[0]


class TestMultiSnapshotDegradation:
    """get_multi_snapshots: per-symbol store fallback when the live feed degrades."""

    async def test_multi_fetch_failure_serves_all_from_store(self) -> None:
        alpaca = FakeMarketDataClient(fail_multi_snapshots=True)
        store = SnapshotStore(
            {
                "AAPL": [_daily_row("AAPL", 1, 151.0)],
                "MSFT": [_daily_row("MSFT", 1, 320.0)],
            }
        )

        result = await _service(alpaca, store).get_multi_snapshots(["AAPL", "MSFT"])

        assert set(result) == {"AAPL", "MSFT"}
        assert result["AAPL"].latest_trade is not None
        assert result["AAPL"].latest_trade.price == 151.0
        assert result["MSFT"].latest_trade is not None
        assert result["MSFT"].latest_trade.price == 320.0

    async def test_symbols_missing_from_live_feed_come_from_store(self) -> None:
        live = Snapshot(
            symbol="AAPL",
            latest_trade=Trade(symbol="AAPL", price=200.0, size=1, timestamp=datetime.now(UTC)),
        )
        alpaca = FakeMarketDataClient(snapshots={"AAPL": live})
        store = SnapshotStore({"MSFT": [_daily_row("MSFT", 1, 320.0)]})

        result = await _service(alpaca, store).get_multi_snapshots(["AAPL", "MSFT"])

        assert result["AAPL"] is live  # live feed wins where it answered
        assert result["MSFT"].latest_trade is not None
        assert result["MSFT"].latest_trade.price == 320.0
        assert store.selects == ["MSFT"]  # store consulted only for the gap

    async def test_symbol_absent_everywhere_is_omitted(self) -> None:
        alpaca = FakeMarketDataClient(fail_multi_snapshots=True)
        store = SnapshotStore({"AAPL": [_daily_row("AAPL", 1, 151.0)]})

        result = await _service(alpaca, store).get_multi_snapshots(["AAPL", "UNKNOWN"])

        assert set(result) == {"AAPL"}

    async def test_store_fallback_snapshots_are_cached(self, mock_cache, mock_redis) -> None:
        alpaca = FakeMarketDataClient(fail_multi_snapshots=True)
        store = SnapshotStore({"AAPL": [_daily_row("AAPL", 1, 151.0)]})
        service = _service(alpaca, store, cache=mock_cache)
        mock_redis.mget = AsyncMock(return_value=[None])

        result = await service.get_multi_snapshots(["AAPL"])

        assert set(result) == {"AAPL"}
        mock_redis.setex.assert_called_once()
        assert "market:snapshot:AAPL" in mock_redis.setex.call_args.args[0]


class TestStoreLimitSemantics:
    """Tests for limit truncation on the store-first read path."""

    @pytest.mark.asyncio
    async def test_limit_keeps_most_recent_bars(self, mock_alpaca_client):
        """A limit smaller than the merged range keeps the bars closest to `end`."""
        from decimal import Decimal

        from src.store.models import BarRow

        start = datetime(2024, 1, 1, tzinfo=UTC)
        end = datetime(2024, 1, 6, tzinfo=UTC)
        rows = [
            BarRow(
                symbol="AAPL",
                time=datetime(2024, 1, day, tzinfo=UTC),
                open=Decimal(100 + day),
                high=Decimal(101 + day),
                low=Decimal(99 + day),
                close=Decimal(100 + day),
                volume=1000,
            )
            for day in range(1, 6)
        ]
        store = AsyncMock()
        store.select_bars.return_value = rows
        # Fully covered range -> no Alpaca gap fetches.
        store.covered_interval.return_value = (rows[0].time, rows[-1].time)

        service = MarketDataService(alpaca=mock_alpaca_client, cache=None, store=store)

        result = await service.get_bars(
            symbol="AAPL",
            timeframe=Timeframe.DAY_1,
            start=start,
            end=end,
            limit=2,
        )

        assert [b.timestamp for b in result] == [rows[-2].time, rows[-1].time]
        mock_alpaca_client.get_bars.assert_not_called()


class TestSymbolNormalization:
    """Tests for symbol normalization (uppercase)."""

    @pytest.mark.asyncio
    async def test_symbol_uppercased(self, mock_alpaca_client, sample_bars):
        """Test that symbols are converted to uppercase."""
        mock_alpaca_client.get_bars.return_value = sample_bars
        service = MarketDataService(alpaca=mock_alpaca_client, cache=None)

        await service.get_bars(
            symbol="aapl",  # lowercase
            timeframe=Timeframe.DAY_1,
            start=datetime(2024, 1, 1, tzinfo=UTC),
            limit=1000,
        )

        call_args = mock_alpaca_client.get_bars.call_args
        assert call_args.kwargs["symbol"] == "AAPL"  # Should be uppercase


class TestGracefulDegradation:
    """Tests for graceful degradation when cache fails."""

    @pytest.mark.asyncio
    async def test_cache_failure_falls_back_to_alpaca(
        self, mock_alpaca_client, mock_cache, mock_redis, sample_bars
    ):
        """Test that cache failure falls back to Alpaca."""
        from redis.exceptions import RedisError

        # Cache get fails
        mock_redis.get.side_effect = RedisError("Connection failed")
        mock_alpaca_client.get_bars.return_value = sample_bars

        service = MarketDataService(alpaca=mock_alpaca_client, cache=mock_cache)

        result = await service.get_bars(
            symbol="AAPL",
            timeframe=Timeframe.DAY_1,
            start=datetime(2024, 1, 1, tzinfo=UTC),
            limit=1000,
        )

        # Should still return data from Alpaca
        assert len(result) == 3
        mock_alpaca_client.get_bars.assert_called_once()
