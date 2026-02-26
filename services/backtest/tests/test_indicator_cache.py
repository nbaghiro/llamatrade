"""Tests for indicator cache module."""

from datetime import date
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from src.cache.indicator_cache import (
    CacheStats,
    IndicatorCache,
    get_indicator_cache,
)


class TestIndicatorCache:
    """Tests for IndicatorCache class."""

    @pytest.fixture
    def cache(self):
        """Create a cache instance with mocked Redis."""
        with patch("src.cache.indicator_cache.redis") as mock_redis:
            mock_client = MagicMock()
            mock_redis.from_url.return_value = mock_client
            cache = IndicatorCache(redis_url="redis://localhost:6379/0", ttl=3600)
            cache._redis = mock_client
            yield cache

    def test_build_key(self, cache):
        """Test cache key building."""
        key = cache._build_key(
            symbol="AAPL",
            indicator="sma",
            params=(20,),
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31),
        )

        assert "bt:ind" in key
        assert "AAPL" in key
        assert "sma" in key
        assert "2024-01-01" in key
        assert "2024-12-31" in key

    def test_serialize_deserialize(self, cache):
        """Test serialization and deserialization."""
        original = np.array([1.0, 2.0, 3.0, 4.0, 5.0])

        serialized = cache._serialize(original)
        assert isinstance(serialized, bytes)

        deserialized = cache._deserialize(serialized)
        np.testing.assert_array_almost_equal(original, deserialized)

    def test_serialize_2d_array(self, cache):
        """Test serialization of 2D array."""
        original = np.array([[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]])

        serialized = cache._serialize(original)
        deserialized = cache._deserialize(serialized)

        np.testing.assert_array_almost_equal(original, deserialized)

    def test_get_cache_hit(self, cache):
        """Test cache hit."""
        test_data = np.array([1.0, 2.0, 3.0])
        serialized = cache._serialize(test_data)
        cache._redis.get.return_value = serialized

        result = cache.get(
            symbol="AAPL",
            indicator="sma",
            params=(20,),
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31),
        )

        assert result is not None
        np.testing.assert_array_almost_equal(result, test_data)
        assert cache._hits == 1
        assert cache._misses == 0

    def test_get_cache_miss(self, cache):
        """Test cache miss."""
        cache._redis.get.return_value = None

        result = cache.get(
            symbol="AAPL",
            indicator="sma",
            params=(20,),
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31),
        )

        assert result is None
        assert cache._hits == 0
        assert cache._misses == 1

    def test_get_redis_error(self, cache):
        """Test cache get with Redis error."""
        cache._redis.get.side_effect = Exception("Redis error")

        result = cache.get(
            symbol="AAPL",
            indicator="sma",
            params=(20,),
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31),
        )

        assert result is None
        assert cache._misses == 1

    def test_set_success(self, cache):
        """Test cache set."""
        test_data = np.array([1.0, 2.0, 3.0])
        cache._redis.setex.return_value = True

        result = cache.set(
            symbol="AAPL",
            indicator="sma",
            params=(20,),
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31),
            values=test_data,
        )

        assert result is True
        cache._redis.setex.assert_called_once()

    def test_set_with_custom_ttl(self, cache):
        """Test cache set with custom TTL."""
        test_data = np.array([1.0, 2.0, 3.0])
        cache._redis.setex.return_value = True

        cache.set(
            symbol="AAPL",
            indicator="sma",
            params=(20,),
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31),
            values=test_data,
            ttl=7200,
        )

        # Check that custom TTL was used
        call_args = cache._redis.setex.call_args
        assert call_args[0][1] == 7200

    def test_set_redis_error(self, cache):
        """Test cache set with Redis error."""
        cache._redis.setex.side_effect = Exception("Redis error")

        result = cache.set(
            symbol="AAPL",
            indicator="sma",
            params=(20,),
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31),
            values=np.array([1.0, 2.0, 3.0]),
        )

        assert result is False

    def test_get_or_compute_cache_hit(self, cache):
        """Test get_or_compute with cache hit."""
        test_data = np.array([1.0, 2.0, 3.0])
        serialized = cache._serialize(test_data)
        cache._redis.get.return_value = serialized

        compute_fn = MagicMock(return_value=np.array([4.0, 5.0, 6.0]))

        result = cache.get_or_compute(
            symbol="AAPL",
            indicator="sma",
            params=(20,),
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31),
            compute_fn=compute_fn,
        )

        np.testing.assert_array_almost_equal(result, test_data)
        compute_fn.assert_not_called()

    def test_get_or_compute_cache_miss(self, cache):
        """Test get_or_compute with cache miss."""
        cache._redis.get.return_value = None
        cache._redis.setex.return_value = True

        computed_data = np.array([4.0, 5.0, 6.0])
        compute_fn = MagicMock(return_value=computed_data)

        result = cache.get_or_compute(
            symbol="AAPL",
            indicator="sma",
            params=(20,),
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31),
            compute_fn=compute_fn,
        )

        np.testing.assert_array_almost_equal(result, computed_data)
        compute_fn.assert_called_once()
        cache._redis.setex.assert_called_once()

    def test_invalidate_specific_symbol(self, cache):
        """Test invalidating cache for specific symbol."""
        cache._redis.scan_iter.return_value = ["key1", "key2"]
        cache._redis.delete.return_value = 2

        count = cache.invalidate(symbol="AAPL")

        assert count == 2

    def test_invalidate_specific_indicator(self, cache):
        """Test invalidating cache for specific indicator."""
        cache._redis.scan_iter.return_value = ["key1"]
        cache._redis.delete.return_value = 1

        count = cache.invalidate(indicator="sma")

        assert count == 1

    def test_invalidate_all(self, cache):
        """Test invalidating all cache entries."""
        cache._redis.scan_iter.return_value = ["key1", "key2", "key3"]
        cache._redis.delete.return_value = 3

        count = cache.invalidate()

        assert count == 3

    def test_invalidate_no_matches(self, cache):
        """Test invalidating when no keys match."""
        cache._redis.scan_iter.return_value = []

        count = cache.invalidate(symbol="NONEXISTENT")

        assert count == 0

    def test_get_stats(self, cache):
        """Test getting cache statistics."""
        cache._hits = 10
        cache._misses = 5

        stats = cache.get_stats()

        assert stats["hits"] == 10
        assert stats["misses"] == 5
        assert stats["hit_rate"] == pytest.approx(0.6667, rel=0.01)

    def test_get_stats_no_requests(self, cache):
        """Test getting stats with no requests."""
        stats = cache.get_stats()

        assert stats["hits"] == 0
        assert stats["misses"] == 0
        assert stats["hit_rate"] == 0.0

    def test_reset_stats(self, cache):
        """Test resetting statistics."""
        cache._hits = 10
        cache._misses = 5

        cache.reset_stats()

        assert cache._hits == 0
        assert cache._misses == 0

    def test_close(self, cache):
        """Test closing cache connection."""
        mock_redis = cache._redis  # Save reference before close
        cache.close()

        mock_redis.close.assert_called_once()
        assert cache._redis is None


class TestGetIndicatorCache:
    """Tests for get_indicator_cache singleton function."""

    def test_returns_cache_instance(self):
        """Test that function returns cache instance."""
        with patch("src.cache.indicator_cache._cache_instance", None):
            with patch("src.cache.indicator_cache.IndicatorCache") as mock_cache_cls:
                mock_instance = MagicMock()
                mock_cache_cls.return_value = mock_instance

                result = get_indicator_cache()

                assert result == mock_instance


class TestCacheStats:
    """Tests for CacheStats TypedDict."""

    def test_cache_stats_structure(self):
        """Test CacheStats has correct structure."""
        stats: CacheStats = {
            "hits": 10,
            "misses": 5,
            "hit_rate": 0.667,
        }

        assert stats["hits"] == 10
        assert stats["misses"] == 5
        assert stats["hit_rate"] == 0.667
