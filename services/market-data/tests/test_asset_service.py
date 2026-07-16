"""Tests for AssetService (asset reference data with caching)."""

from unittest.mock import AsyncMock

import pytest
from llamatrade_alpaca import Asset

from src.cache import MarketDataCache
from src.services.asset_service import AssetService


def make_asset(symbol: str, name: str) -> Asset:
    return Asset(
        id=f"id-{symbol}",
        symbol=symbol,
        name=name,
        asset_class="us_equity",
        exchange="ARCA",
        status="active",
        tradable=True,
        fractionable=True,
    )


@pytest.fixture
def trading_client():
    client = AsyncMock()
    client.get_asset = AsyncMock(return_value=None)
    return client


class TestGetAssets:
    """Tests for AssetService.get_assets."""

    @pytest.mark.asyncio
    async def test_cache_miss_fetches_and_caches(self, trading_client, mock_cache, mock_redis):
        """Cache miss fetches from Alpaca and writes through to the cache."""
        mock_redis.mget.return_value = [None]
        trading_client.get_asset.return_value = make_asset("XLE", "Energy Select Sector SPDR Fund")

        service = AssetService(alpaca=trading_client, cache=mock_cache)
        result = await service.get_assets(["XLE"])

        assert result["XLE"].name == "Energy Select Sector SPDR Fund"
        trading_client.get_asset.assert_awaited_once_with("XLE")
        mock_redis.setex.assert_awaited()

    @pytest.mark.asyncio
    async def test_cache_hit_skips_alpaca(self, trading_client, mock_cache, mock_redis):
        """A cached asset is returned without calling Alpaca."""
        asset = make_asset("XLB", "Materials Select Sector SPDR Fund")
        mock_redis.mget.return_value = [MarketDataCache.serialize_model(asset)]

        service = AssetService(alpaca=trading_client, cache=mock_cache)
        result = await service.get_assets(["XLB"])

        assert result["XLB"].name == "Materials Select Sector SPDR Fund"
        trading_client.get_asset.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_unknown_symbol_is_omitted(self, trading_client):
        """A 404 from Alpaca (None) drops the symbol rather than erroring."""
        trading_client.get_asset.return_value = None

        service = AssetService(alpaca=trading_client, cache=None)

        assert await service.get_assets(["NOPE"]) == {}

    @pytest.mark.asyncio
    async def test_one_failure_does_not_break_the_batch(self, trading_client):
        """A per-symbol fetch error is logged and skipped; siblings still resolve."""

        async def side_effect(symbol: str) -> Asset:
            if symbol == "BAD":
                raise RuntimeError("alpaca down")
            return make_asset(symbol, "SPDR S&P 500 ETF")

        trading_client.get_asset.side_effect = side_effect

        service = AssetService(alpaca=trading_client, cache=None)
        result = await service.get_assets(["SPY", "BAD"])

        assert set(result) == {"SPY"}

    @pytest.mark.asyncio
    async def test_normalizes_and_dedupes_symbols(self, trading_client):
        """Symbols are upper-cased and de-duplicated before fetching."""
        trading_client.get_asset.return_value = make_asset("QQQ", "Invesco QQQ Trust")

        service = AssetService(alpaca=trading_client, cache=None)
        result = await service.get_assets(["qqq", "QQQ"])

        assert list(result) == ["QQQ"]
        assert trading_client.get_asset.await_count == 1

    @pytest.mark.asyncio
    async def test_empty_symbols_short_circuits(self, trading_client):
        """No symbols → no Alpaca call."""
        service = AssetService(alpaca=trading_client, cache=None)

        assert await service.get_assets([]) == {}
        trading_client.get_asset.assert_not_awaited()
