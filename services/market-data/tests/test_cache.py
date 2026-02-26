"""Tests for Redis cache module."""

from datetime import UTC, date, datetime, timedelta

import pytest
from redis.exceptions import RedisError
from src.cache import (
    TTL_HISTORICAL_BARS,
    TTL_LATEST_BAR,
    TTL_LATEST_QUOTE,
    TTL_SNAPSHOT,
    TTL_TODAY_BARS,
    MarketDataCache,
)
from src.models import Bar, Quote, Snapshot, Timeframe


class TestKeyGeneration:
    """Tests for cache key generation methods."""

    def test_bars_key_with_end(self):
        """Test bars key generation with end date."""
        start = datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC)
        end = datetime(2024, 1, 31, 0, 0, 0, tzinfo=UTC)

        key = MarketDataCache.bars_key("AAPL", Timeframe.DAY_1, start, end, 1000)

        assert (
            key == "market:bars:AAPL:1Day:2024-01-01T00:00:00+00:00:2024-01-31T00:00:00+00:00:1000"
        )
        assert "AAPL" in key
        assert "1Day" in key

    def test_bars_key_without_end(self):
        """Test bars key generation without end date."""
        start = datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC)

        key = MarketDataCache.bars_key("TSLA", Timeframe.HOUR_1, start, None, 500)

        assert key == "market:bars:TSLA:1Hour:2024-01-01T00:00:00+00:00:none:500"
        assert ":none:" in key

    def test_latest_bar_key(self):
        """Test latest bar key generation."""
        key = MarketDataCache.latest_bar_key("MSFT")
        assert key == "market:bar:latest:MSFT"

    def test_latest_quote_key(self):
        """Test latest quote key generation."""
        key = MarketDataCache.latest_quote_key("GOOGL")
        assert key == "market:quote:GOOGL"

    def test_snapshot_key(self):
        """Test snapshot key generation."""
        key = MarketDataCache.snapshot_key("AMZN")
        assert key == "market:snapshot:AMZN"


class TestTTLCalculation:
    """Tests for TTL calculation logic."""

    def test_historical_bars_ttl(self):
        """Test TTL for historical data (before today)."""
        start = datetime(2024, 1, 1, tzinfo=UTC)
        end = datetime(2024, 1, 31, tzinfo=UTC)

        ttl = MarketDataCache.calculate_bars_ttl(start, end)

        assert ttl == TTL_HISTORICAL_BARS
        assert ttl == 24 * 60 * 60  # 24 hours

    def test_today_bars_ttl_with_today_end(self):
        """Test TTL for data ending today."""
        start = datetime(2024, 1, 1, tzinfo=UTC)
        today = datetime.combine(date.today(), datetime.min.time(), tzinfo=UTC)

        ttl = MarketDataCache.calculate_bars_ttl(start, today)

        assert ttl == TTL_TODAY_BARS
        assert ttl == 5 * 60  # 5 minutes

    def test_today_bars_ttl_with_none_end(self):
        """Test TTL for data with no end date (current)."""
        start = datetime(2024, 1, 1, tzinfo=UTC)

        ttl = MarketDataCache.calculate_bars_ttl(start, None)

        assert ttl == TTL_TODAY_BARS
        assert ttl == 5 * 60  # 5 minutes

    def test_today_bars_ttl_with_future_end(self):
        """Test TTL for data with future end date."""
        start = datetime(2024, 1, 1, tzinfo=UTC)
        future = datetime.now(UTC) + timedelta(days=1)

        ttl = MarketDataCache.calculate_bars_ttl(start, future)

        assert ttl == TTL_TODAY_BARS


class TestSerialization:
    """Tests for serialization/deserialization."""

    def test_serialize_deserialize_bar(self, sample_bar):
        """Test Bar roundtrip serialization."""
        serialized = MarketDataCache.serialize_model(sample_bar)
        deserialized = MarketDataCache.deserialize_model(serialized, Bar)

        assert deserialized.timestamp == sample_bar.timestamp
        assert deserialized.open == sample_bar.open
        assert deserialized.high == sample_bar.high
        assert deserialized.low == sample_bar.low
        assert deserialized.close == sample_bar.close
        assert deserialized.volume == sample_bar.volume

    def test_serialize_deserialize_bar_list(self, sample_bars):
        """Test Bar list roundtrip serialization."""
        serialized = MarketDataCache.serialize_model_list(sample_bars)
        deserialized = MarketDataCache.deserialize_model_list(serialized, Bar)

        assert len(deserialized) == len(sample_bars)
        for orig, deser in zip(sample_bars, deserialized):
            assert deser.timestamp == orig.timestamp
            assert deser.close == orig.close

    def test_serialize_deserialize_quote(self, sample_quote):
        """Test Quote roundtrip serialization."""
        serialized = MarketDataCache.serialize_model(sample_quote)
        deserialized = MarketDataCache.deserialize_model(serialized, Quote)

        assert deserialized.symbol == sample_quote.symbol
        assert deserialized.bid_price == sample_quote.bid_price
        assert deserialized.ask_price == sample_quote.ask_price

    def test_serialize_deserialize_snapshot(self, sample_snapshot):
        """Test Snapshot roundtrip serialization."""
        serialized = MarketDataCache.serialize_model(sample_snapshot)
        deserialized = MarketDataCache.deserialize_model(serialized, Snapshot)

        assert deserialized.symbol == sample_snapshot.symbol
        assert deserialized.latest_quote.bid_price == sample_snapshot.latest_quote.bid_price
        assert deserialized.daily_bar.close == sample_snapshot.daily_bar.close

    def test_serialize_deserialize_bars_dict(self, sample_bars):
        """Test multi-symbol bars dict roundtrip serialization."""
        bars_dict = {
            "AAPL": sample_bars,
            "TSLA": sample_bars[:2],
        }
        serialized = MarketDataCache.serialize_bars_dict(bars_dict)
        deserialized = MarketDataCache.deserialize_bars_dict(serialized, Bar)

        assert len(deserialized["AAPL"]) == 3
        assert len(deserialized["TSLA"]) == 2
        assert deserialized["AAPL"][0].close == sample_bars[0].close


class TestCacheOperations:
    """Tests for cache operations."""

    @pytest.mark.asyncio
    async def test_get_cache_hit(self, mock_cache, mock_redis):
        """Test cache get with hit."""
        mock_redis.get.return_value = b'{"test": "data"}'

        result = await mock_cache.get("test:key")

        assert result == '{"test": "data"}'
        mock_redis.get.assert_called_once_with("test:key")

    @pytest.mark.asyncio
    async def test_get_cache_miss(self, mock_cache, mock_redis):
        """Test cache get with miss."""
        mock_redis.get.return_value = None

        result = await mock_cache.get("test:key")

        assert result is None

    @pytest.mark.asyncio
    async def test_get_handles_redis_error(self, mock_cache, mock_redis):
        """Test cache get gracefully handles Redis errors."""
        mock_redis.get.side_effect = RedisError("Connection failed")

        result = await mock_cache.get("test:key")

        assert result is None  # Fails gracefully

    @pytest.mark.asyncio
    async def test_set_success(self, mock_cache, mock_redis):
        """Test cache set success."""
        result = await mock_cache.set("test:key", '{"test": "data"}', 300)

        assert result is True
        mock_redis.setex.assert_called_once()

    @pytest.mark.asyncio
    async def test_set_handles_redis_error(self, mock_cache, mock_redis):
        """Test cache set gracefully handles Redis errors."""
        mock_redis.setex.side_effect = RedisError("Connection failed")

        result = await mock_cache.set("test:key", '{"test": "data"}', 300)

        assert result is False  # Fails gracefully

    @pytest.mark.asyncio
    async def test_delete_success(self, mock_cache, mock_redis):
        """Test cache delete success."""
        result = await mock_cache.delete("test:key")

        assert result is True
        mock_redis.delete.assert_called_once_with("test:key")

    @pytest.mark.asyncio
    async def test_delete_handles_redis_error(self, mock_cache, mock_redis):
        """Test cache delete gracefully handles Redis errors."""
        mock_redis.delete.side_effect = RedisError("Connection failed")

        result = await mock_cache.delete("test:key")

        assert result is False

    @pytest.mark.asyncio
    async def test_health_check_healthy(self, mock_cache, mock_redis):
        """Test health check when Redis is healthy."""
        mock_redis.ping.return_value = True

        result = await mock_cache.health_check()

        assert result is True

    @pytest.mark.asyncio
    async def test_health_check_unhealthy(self, mock_cache, mock_redis):
        """Test health check when Redis is unhealthy."""
        mock_redis.ping.side_effect = RedisError("Connection failed")

        result = await mock_cache.health_check()

        assert result is False


class TestTTLConstants:
    """Test TTL constant values."""

    def test_ttl_historical_bars(self):
        """Test historical bars TTL is 24 hours."""
        assert TTL_HISTORICAL_BARS == 86400

    def test_ttl_today_bars(self):
        """Test today bars TTL is 5 minutes."""
        assert TTL_TODAY_BARS == 300

    def test_ttl_latest_bar(self):
        """Test latest bar TTL is 2 minutes."""
        assert TTL_LATEST_BAR == 120

    def test_ttl_latest_quote(self):
        """Test latest quote TTL is 10 seconds."""
        assert TTL_LATEST_QUOTE == 10

    def test_ttl_snapshot(self):
        """Test snapshot TTL is 15 seconds."""
        assert TTL_SNAPSHOT == 15
