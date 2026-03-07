"""Tests for singleton client helpers."""

from unittest.mock import AsyncMock, patch

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


class TestTradingClientSingleton:
    """Tests for get_trading_client and close_trading_client."""

    def setup_method(self):
        """Reset singleton state before each test."""
        import llamatrade_alpaca.clients as clients_module

        clients_module._trading_client = None
        clients_module._client_lock = None

    def test_get_trading_client_returns_client(self):
        """Test that get_trading_client returns a TradingClient."""
        with patch.object(TradingClient, "__init__", return_value=None):
            client = get_trading_client()
            assert isinstance(client, TradingClient)

    def test_get_trading_client_returns_same_instance(self):
        """Test that get_trading_client returns the same instance."""
        with patch.object(TradingClient, "__init__", return_value=None):
            client1 = get_trading_client()
            client2 = get_trading_client()
            assert client1 is client2

    @pytest.mark.asyncio
    async def test_get_trading_client_async_returns_client(self):
        """Test that get_trading_client_async returns a TradingClient."""
        with patch.object(TradingClient, "__init__", return_value=None):
            client = await get_trading_client_async()
            assert isinstance(client, TradingClient)

    @pytest.mark.asyncio
    async def test_get_trading_client_async_returns_same_instance(self):
        """Test that get_trading_client_async returns the same instance."""
        with patch.object(TradingClient, "__init__", return_value=None):
            client1 = await get_trading_client_async()
            client2 = await get_trading_client_async()
            assert client1 is client2

    @pytest.mark.asyncio
    async def test_close_trading_client(self):
        """Test that close_trading_client closes and clears the singleton."""
        import llamatrade_alpaca.clients as clients_module

        mock_client = AsyncMock(spec=TradingClient)
        clients_module._trading_client = mock_client

        await close_trading_client()

        mock_client.close.assert_called_once()
        assert clients_module._trading_client is None

    @pytest.mark.asyncio
    async def test_close_trading_client_when_none(self):
        """Test that close_trading_client handles None gracefully."""
        import llamatrade_alpaca.clients as clients_module

        clients_module._trading_client = None

        # Should not raise
        await close_trading_client()

        assert clients_module._trading_client is None


class TestMarketDataClientSingleton:
    """Tests for get_market_data_client and close_market_data_client."""

    def setup_method(self):
        """Reset singleton state before each test."""
        import llamatrade_alpaca.clients as clients_module

        clients_module._market_data_client = None
        clients_module._client_lock = None

    def test_get_market_data_client_returns_client(self):
        """Test that get_market_data_client returns a MarketDataClient."""
        with patch.object(MarketDataClient, "__init__", return_value=None):
            client = get_market_data_client()
            assert isinstance(client, MarketDataClient)

    def test_get_market_data_client_returns_same_instance(self):
        """Test that get_market_data_client returns the same instance."""
        with patch.object(MarketDataClient, "__init__", return_value=None):
            client1 = get_market_data_client()
            client2 = get_market_data_client()
            assert client1 is client2

    @pytest.mark.asyncio
    async def test_get_market_data_client_async_returns_client(self):
        """Test that get_market_data_client_async returns a MarketDataClient."""
        with patch.object(MarketDataClient, "__init__", return_value=None):
            client = await get_market_data_client_async()
            assert isinstance(client, MarketDataClient)

    @pytest.mark.asyncio
    async def test_get_market_data_client_async_returns_same_instance(self):
        """Test that get_market_data_client_async returns the same instance."""
        with patch.object(MarketDataClient, "__init__", return_value=None):
            client1 = await get_market_data_client_async()
            client2 = await get_market_data_client_async()
            assert client1 is client2

    @pytest.mark.asyncio
    async def test_close_market_data_client(self):
        """Test that close_market_data_client closes and clears the singleton."""
        import llamatrade_alpaca.clients as clients_module

        mock_client = AsyncMock(spec=MarketDataClient)
        clients_module._market_data_client = mock_client

        await close_market_data_client()

        mock_client.close.assert_called_once()
        assert clients_module._market_data_client is None

    @pytest.mark.asyncio
    async def test_close_market_data_client_when_none(self):
        """Test that close_market_data_client handles None gracefully."""
        import llamatrade_alpaca.clients as clients_module

        clients_module._market_data_client = None

        # Should not raise
        await close_market_data_client()

        assert clients_module._market_data_client is None


class TestCloseAllClients:
    """Tests for close_all_clients helper."""

    def setup_method(self):
        """Reset singleton state before each test."""
        import llamatrade_alpaca.clients as clients_module

        clients_module._trading_client = None
        clients_module._market_data_client = None
        clients_module._client_lock = None

    @pytest.mark.asyncio
    async def test_close_all_clients_closes_both(self):
        """Test that close_all_clients closes both clients."""
        import llamatrade_alpaca.clients as clients_module

        mock_trading = AsyncMock(spec=TradingClient)
        mock_market_data = AsyncMock(spec=MarketDataClient)
        clients_module._trading_client = mock_trading
        clients_module._market_data_client = mock_market_data

        await close_all_clients()

        mock_trading.close.assert_called_once()
        mock_market_data.close.assert_called_once()
        assert clients_module._trading_client is None
        assert clients_module._market_data_client is None

    @pytest.mark.asyncio
    async def test_close_all_clients_when_none(self):
        """Test that close_all_clients handles None gracefully."""
        import llamatrade_alpaca.clients as clients_module

        clients_module._trading_client = None
        clients_module._market_data_client = None

        # Should not raise
        await close_all_clients()

        assert clients_module._trading_client is None
        assert clients_module._market_data_client is None
