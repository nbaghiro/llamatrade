"""Tests for singleton client helpers.

Clients are constructed for real (construction makes no network calls), so the
caching, sharing, and close-then-clear behavior is asserted on honest objects.
"""

import pytest

from llamatrade_alpaca import (
    MarketDataClient,
    TradingClient,
    close_all_clients,
    close_market_data_client,
    close_trading_client,
    get_market_data_client,
    get_market_data_client_async,
    get_trading_client,
    get_trading_client_async,
)


@pytest.fixture(autouse=True)
def reset_singletons() -> None:
    """Reset singleton state before each test."""
    import llamatrade_alpaca.clients as clients_module

    clients_module._trading_client = None
    clients_module._market_data_client = None
    clients_module._client_lock = None


class TestTradingClientSingleton:
    """Tests for get_trading_client and close_trading_client."""

    async def test_get_trading_client_creates_and_caches(self) -> None:
        client = get_trading_client()
        try:
            assert isinstance(client, TradingClient)
            assert get_trading_client() is client
        finally:
            await close_trading_client()

    async def test_get_trading_client_async_creates_and_caches(self) -> None:
        client = await get_trading_client_async()
        try:
            assert isinstance(client, TradingClient)
            assert await get_trading_client_async() is client
            assert get_trading_client() is client  # sync and async share the singleton
        finally:
            await close_trading_client()

    async def test_close_trading_client(self) -> None:
        import llamatrade_alpaca.clients as clients_module

        client = get_trading_client()

        await close_trading_client()

        assert client._client.is_closed
        assert clients_module._trading_client is None

    async def test_close_trading_client_when_none(self) -> None:
        import llamatrade_alpaca.clients as clients_module

        await close_trading_client()

        assert clients_module._trading_client is None


class TestMarketDataClientSingleton:
    """Tests for get_market_data_client and close_market_data_client."""

    async def test_get_market_data_client_creates_and_caches(self) -> None:
        client = get_market_data_client()
        try:
            assert isinstance(client, MarketDataClient)
            assert get_market_data_client() is client
        finally:
            await close_market_data_client()

    async def test_get_market_data_client_async_creates_and_caches(self) -> None:
        client = await get_market_data_client_async()
        try:
            assert isinstance(client, MarketDataClient)
            assert await get_market_data_client_async() is client
            assert get_market_data_client() is client  # sync and async share the singleton
        finally:
            await close_market_data_client()

    async def test_close_market_data_client(self) -> None:
        import llamatrade_alpaca.clients as clients_module

        client = get_market_data_client()

        await close_market_data_client()

        assert client._client.is_closed
        assert clients_module._market_data_client is None

    async def test_close_market_data_client_when_none(self) -> None:
        import llamatrade_alpaca.clients as clients_module

        await close_market_data_client()

        assert clients_module._market_data_client is None


class TestCloseAllClients:
    """Tests for close_all_clients helper."""

    async def test_close_all_clients_closes_both(self) -> None:
        import llamatrade_alpaca.clients as clients_module

        trading = get_trading_client()
        market_data = get_market_data_client()

        await close_all_clients()

        assert trading._client.is_closed
        assert market_data._client.is_closed
        assert clients_module._trading_client is None
        assert clients_module._market_data_client is None

    async def test_close_all_clients_when_none(self) -> None:
        import llamatrade_alpaca.clients as clients_module

        await close_all_clients()

        assert clients_module._trading_client is None
        assert clients_module._market_data_client is None
