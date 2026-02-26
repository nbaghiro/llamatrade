"""Tests for MarketDataService with caching."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest
from src.cache import MarketDataCache
from src.models import Snapshot, Timeframe
from src.services.market_data_service import MarketDataService


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
        """Test that only uncached symbols are fetched from Alpaca."""

        # AAPL is cached, TSLA is not
        def mock_get(key):
            if "AAPL" in key:
                return MarketDataCache.serialize_model_list(sample_bars).encode()
            return None

        mock_redis.get = AsyncMock(side_effect=mock_get)
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


class TestGetLatestBar:
    """Tests for get_latest_bar method."""

    @pytest.mark.asyncio
    async def test_cache_hit(self, mock_alpaca_client, mock_cache, mock_redis, sample_bar):
        """Test cache hit for latest bar."""
        cached_data = MarketDataCache.serialize_model(sample_bar)
        mock_redis.get.return_value = cached_data.encode()

        service = MarketDataService(alpaca=mock_alpaca_client, cache=mock_cache)

        result = await service.get_latest_bar(symbol="AAPL")

        assert result.close == sample_bar.close
        mock_alpaca_client.get_latest_bar.assert_not_called()

    @pytest.mark.asyncio
    async def test_cache_miss(self, mock_alpaca_client, mock_cache, sample_bar):
        """Test cache miss for latest bar."""
        mock_alpaca_client.get_latest_bar.return_value = sample_bar

        service = MarketDataService(alpaca=mock_alpaca_client, cache=mock_cache)

        result = await service.get_latest_bar(symbol="AAPL")

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

        assert result.bid_price == sample_quote.bid_price
        mock_alpaca_client.get_latest_quote.assert_not_called()

    @pytest.mark.asyncio
    async def test_cache_miss(self, mock_alpaca_client, mock_cache, sample_quote):
        """Test cache miss for latest quote."""
        mock_alpaca_client.get_latest_quote.return_value = sample_quote

        service = MarketDataService(alpaca=mock_alpaca_client, cache=mock_cache)

        result = await service.get_latest_quote(symbol="AAPL")

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

        assert result.symbol == sample_snapshot.symbol
        mock_alpaca_client.get_snapshot.assert_not_called()

    @pytest.mark.asyncio
    async def test_cache_miss(self, mock_alpaca_client, mock_cache, sample_snapshot):
        """Test cache miss for snapshot."""
        mock_alpaca_client.get_snapshot.return_value = sample_snapshot

        service = MarketDataService(alpaca=mock_alpaca_client, cache=mock_cache)

        result = await service.get_snapshot(symbol="AAPL")

        assert result.symbol == sample_snapshot.symbol
        mock_alpaca_client.get_snapshot.assert_called_once()


class TestGetMultiSnapshots:
    """Tests for get_multi_snapshots method."""

    @pytest.mark.asyncio
    async def test_fetches_uncached_symbols_only(
        self, mock_alpaca_client, mock_cache, mock_redis, sample_snapshot
    ):
        """Test that only uncached symbols are fetched from Alpaca."""

        def mock_get(key):
            if "AAPL" in key:
                return MarketDataCache.serialize_model(sample_snapshot).encode()
            return None

        mock_redis.get = AsyncMock(side_effect=mock_get)

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
