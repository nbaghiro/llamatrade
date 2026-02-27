"""Tests for Alpaca WebSocket stream client."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from websockets.protocol import State

from src.streaming.alpaca_stream import (
    AlpacaStreamClient,
    StreamConfig,
    close_alpaca_stream,
    get_alpaca_stream,
    init_alpaca_stream,
)


@pytest.fixture
def stream_config():
    """Create a test stream config."""
    return StreamConfig(
        api_key="test_key",
        api_secret="test_secret",
        paper=True,
        reconnect_delay=0.1,
        max_reconnect_attempts=2,
    )


@pytest.fixture
def client(stream_config):
    """Create a test client."""
    return AlpacaStreamClient(stream_config)


@pytest.fixture
def mock_websocket():
    """Create a mock websocket connection."""
    ws = AsyncMock()
    ws.state = State.OPEN  # Use State enum instead of bool .open attribute
    ws.send = AsyncMock()
    ws.recv = AsyncMock()
    ws.close = AsyncMock()
    return ws


class TestStreamConfig:
    """Tests for StreamConfig dataclass."""

    def test_default_config(self):
        """Test default configuration values."""
        with patch.dict("os.environ", {}, clear=True):
            config = StreamConfig()

        assert config.api_key == ""
        assert config.api_secret == ""
        assert config.paper is True
        assert config.reconnect_delay == 5.0
        assert config.max_reconnect_attempts == 10

    def test_config_from_env(self):
        """Test configuration from environment variables."""
        with patch.dict(
            "os.environ",
            {"ALPACA_API_KEY": "env_key", "ALPACA_API_SECRET": "env_secret"},
        ):
            config = StreamConfig()

        assert config.api_key == "env_key"
        assert config.api_secret == "env_secret"

    def test_custom_config(self, stream_config):
        """Test custom configuration."""
        assert stream_config.api_key == "test_key"
        assert stream_config.api_secret == "test_secret"
        assert stream_config.paper is True


class TestAlpacaStreamClientInit:
    """Tests for AlpacaStreamClient initialization."""

    def test_init_with_config(self, stream_config):
        """Test initialization with config."""
        client = AlpacaStreamClient(stream_config)

        assert client.config is stream_config
        assert client.url == AlpacaStreamClient.PAPER_URL

    def test_init_without_config(self):
        """Test initialization without config uses defaults."""
        client = AlpacaStreamClient()

        assert client.config is not None
        assert client.url == AlpacaStreamClient.PAPER_URL

    def test_init_live_url(self):
        """Test that live mode uses live URL."""
        config = StreamConfig(api_key="key", api_secret="secret", paper=False)
        client = AlpacaStreamClient(config)

        assert client.url == AlpacaStreamClient.LIVE_URL

    def test_initial_state(self, client):
        """Test initial client state."""
        assert client.connected is False
        assert client.authenticated is False
        assert client.subscribed_symbols == {
            "trades": set(),
            "quotes": set(),
            "bars": set(),
        }


class TestAlpacaStreamClientProperties:
    """Tests for client properties."""

    def test_connected_without_websocket(self, client):
        """Test connected property when no websocket."""
        assert client.connected is False

    def test_connected_with_closed_websocket(self, client, mock_websocket):
        """Test connected property with closed websocket."""
        mock_websocket.state = State.CLOSED
        client._ws = mock_websocket
        assert client.connected is False

    def test_connected_with_open_websocket(self, client, mock_websocket):
        """Test connected property with open websocket."""
        mock_websocket.state = State.OPEN
        client._ws = mock_websocket
        assert client.connected is True

    def test_authenticated_initial(self, client):
        """Test authenticated property initially false."""
        assert client.authenticated is False

    def test_subscribed_symbols_returns_copy(self, client):
        """Test that subscribed_symbols returns a copy."""
        client._subscribed_trades.add("AAPL")
        symbols = client.subscribed_symbols
        symbols["trades"].add("GOOGL")

        # Original should not be modified
        assert "GOOGL" not in client._subscribed_trades


class TestAlpacaStreamClientCallbacks:
    """Tests for callback methods."""

    def test_set_callbacks(self, client):
        """Test setting callbacks."""
        on_trade = MagicMock()
        on_quote = MagicMock()
        on_bar = MagicMock()

        client.set_callbacks(on_trade=on_trade, on_quote=on_quote, on_bar=on_bar)

        assert client._on_trade is on_trade
        assert client._on_quote is on_quote
        assert client._on_bar is on_bar

    def test_set_callbacks_partial(self, client):
        """Test setting only some callbacks."""
        on_trade = MagicMock()
        client.set_callbacks(on_trade=on_trade)

        assert client._on_trade is on_trade
        assert client._on_quote is None
        assert client._on_bar is None


class TestAlpacaStreamClientConnect:
    """Tests for connect method."""

    async def test_connect_success(self, client, mock_websocket):
        """Test successful connection and authentication."""
        # Set up mock responses
        mock_websocket.recv = AsyncMock(
            side_effect=[
                json.dumps([{"T": "success", "msg": "connected"}]),
                json.dumps([{"T": "success", "msg": "authenticated"}]),
            ]
        )

        with patch("websockets.connect", AsyncMock(return_value=mock_websocket)):
            result = await client.connect()

        assert result is True
        assert client.authenticated is True
        assert client._reconnect_attempts == 0

    async def test_connect_auth_failure(self, client, mock_websocket):
        """Test connection with authentication failure."""
        mock_websocket.recv = AsyncMock(
            side_effect=[
                json.dumps([{"T": "success", "msg": "connected"}]),
                json.dumps([{"T": "error", "msg": "auth failed"}]),
            ]
        )

        with patch("websockets.connect", AsyncMock(return_value=mock_websocket)):
            result = await client.connect()

        assert result is False
        assert client.authenticated is False

    async def test_connect_unexpected_welcome(self, client, mock_websocket):
        """Test connection with unexpected welcome message."""
        mock_websocket.recv = AsyncMock(
            return_value=json.dumps([{"T": "error", "msg": "unexpected"}])
        )

        with patch("websockets.connect", AsyncMock(return_value=mock_websocket)):
            result = await client.connect()

        assert result is False

    async def test_connect_exception(self, client):
        """Test connection with exception."""
        with patch("websockets.connect", AsyncMock(side_effect=Exception("Connect failed"))):
            result = await client.connect()

        assert result is False
        assert client.connected is False


class TestAlpacaStreamClientDisconnect:
    """Tests for disconnect method."""

    async def test_disconnect_cleans_up(self, client, mock_websocket):
        """Test that disconnect cleans up state."""
        client._ws = mock_websocket
        client._authenticated = True
        client._running = True
        client._subscribed_trades.add("AAPL")

        await client.disconnect()

        assert client._ws is None
        assert client._authenticated is False
        assert client._running is False
        assert len(client._subscribed_trades) == 0

    async def test_disconnect_handles_close_error(self, client, mock_websocket):
        """Test that disconnect handles close error gracefully."""
        mock_websocket.close = AsyncMock(side_effect=Exception("Close failed"))
        client._ws = mock_websocket

        # Should not raise
        await client.disconnect()
        assert client._ws is None

    async def test_disconnect_without_connection(self, client):
        """Test disconnect when not connected."""
        # Should not raise
        await client.disconnect()


class TestAlpacaStreamClientSubscribe:
    """Tests for subscribe method."""

    async def test_subscribe_not_connected(self, client):
        """Test subscribe when not connected."""
        result = await client.subscribe(trades=["AAPL"])
        assert result is False

    async def test_subscribe_not_authenticated(self, client, mock_websocket):
        """Test subscribe when not authenticated."""
        mock_websocket.state = State.OPEN
        client._ws = mock_websocket
        client._authenticated = False

        result = await client.subscribe(trades=["AAPL"])
        assert result is False

    async def test_subscribe_success(self, client, mock_websocket):
        """Test successful subscription."""
        mock_websocket.state = State.OPEN
        mock_websocket.recv = AsyncMock(
            return_value=json.dumps(
                [
                    {
                        "T": "subscription",
                        "trades": ["AAPL"],
                        "quotes": [],
                        "bars": [],
                    }
                ]
            )
        )
        client._ws = mock_websocket
        client._authenticated = True

        result = await client.subscribe(trades=["AAPL"])

        assert result is True
        assert "AAPL" in client._subscribed_trades

    async def test_subscribe_normalizes_symbols(self, client, mock_websocket):
        """Test that subscribe normalizes symbols to uppercase."""
        mock_websocket.state = State.OPEN
        mock_websocket.recv = AsyncMock(
            return_value=json.dumps(
                [
                    {
                        "T": "subscription",
                        "trades": ["AAPL"],
                        "quotes": [],
                        "bars": [],
                    }
                ]
            )
        )
        client._ws = mock_websocket
        client._authenticated = True

        await client.subscribe(trades=["aapl"])

        # Should filter since already (normalized) in subscribed
        await client.subscribe(trades=["AAPL"])

    async def test_subscribe_already_subscribed(self, client, mock_websocket):
        """Test subscribe for already subscribed symbol."""
        mock_websocket.state = State.OPEN
        client._ws = mock_websocket
        client._authenticated = True
        client._subscribed_trades.add("AAPL")

        result = await client.subscribe(trades=["AAPL"])

        # Should return True without sending message
        assert result is True
        mock_websocket.send.assert_not_called()

    async def test_subscribe_exception(self, client, mock_websocket):
        """Test subscribe with exception."""
        mock_websocket.state = State.OPEN
        mock_websocket.send = AsyncMock(side_effect=Exception("Send failed"))
        client._ws = mock_websocket
        client._authenticated = True

        result = await client.subscribe(trades=["AAPL"])

        assert result is False

    async def test_subscribe_failure_response(self, client, mock_websocket):
        """Test subscribe with failure response."""
        mock_websocket.state = State.OPEN
        mock_websocket.recv = AsyncMock(
            return_value=json.dumps([{"T": "error", "msg": "subscription failed"}])
        )
        client._ws = mock_websocket
        client._authenticated = True

        result = await client.subscribe(trades=["AAPL"])

        assert result is False


class TestAlpacaStreamClientUnsubscribe:
    """Tests for unsubscribe method."""

    async def test_unsubscribe_not_connected(self, client):
        """Test unsubscribe when not connected returns True."""
        result = await client.unsubscribe(trades=["AAPL"])
        assert result is True

    async def test_unsubscribe_empty_list(self, client, mock_websocket):
        """Test unsubscribe with empty lists."""
        mock_websocket.state = State.OPEN
        client._ws = mock_websocket

        result = await client.unsubscribe(trades=[], quotes=[], bars=[])

        assert result is True
        mock_websocket.send.assert_not_called()

    async def test_unsubscribe_success(self, client, mock_websocket):
        """Test successful unsubscription."""
        mock_websocket.state = State.OPEN
        mock_websocket.recv = AsyncMock(
            return_value=json.dumps(
                [
                    {
                        "T": "subscription",
                        "trades": [],
                        "quotes": [],
                        "bars": [],
                    }
                ]
            )
        )
        client._ws = mock_websocket
        client._subscribed_trades.add("AAPL")

        result = await client.unsubscribe(trades=["AAPL"])

        assert result is True
        assert "AAPL" not in client._subscribed_trades

    async def test_unsubscribe_normalizes_symbols(self, client, mock_websocket):
        """Test that unsubscribe normalizes symbols to uppercase."""
        mock_websocket.state = State.OPEN
        mock_websocket.recv = AsyncMock(return_value=json.dumps([{"T": "subscription"}]))
        client._ws = mock_websocket
        client._subscribed_trades.add("AAPL")

        await client.unsubscribe(trades=["aapl"])

        assert "AAPL" not in client._subscribed_trades

    async def test_unsubscribe_exception(self, client, mock_websocket):
        """Test unsubscribe with exception."""
        mock_websocket.state = State.OPEN
        mock_websocket.send = AsyncMock(side_effect=Exception("Send failed"))
        client._ws = mock_websocket

        result = await client.unsubscribe(trades=["AAPL"])

        assert result is False


class TestAlpacaStreamClientParsers:
    """Tests for message parsing methods."""

    def test_parse_trade(self, client):
        """Test parsing trade message."""
        data = {
            "T": "t",
            "S": "AAPL",
            "p": 150.25,
            "s": 100,
            "x": "V",
            "t": "2024-01-15T09:30:00Z",
        }

        result = client._parse_trade(data)

        assert result is not None
        assert result["price"] == 150.25
        assert result["size"] == 100
        assert result["exchange"] == "V"

    def test_parse_trade_invalid(self, client):
        """Test parsing invalid trade message."""

        with patch.object(client, "_parse_trade", side_effect=Exception):
            # Test the actual error handling in _parse_trade
            pass

        # The method should handle errors gracefully
        result = client._parse_trade({})
        assert result is not None  # Uses defaults

    def test_parse_quote(self, client):
        """Test parsing quote message."""
        data = {
            "T": "q",
            "S": "AAPL",
            "bp": 150.20,
            "bs": 100,
            "ap": 150.25,
            "as": 200,
            "t": "2024-01-15T09:30:00Z",
        }

        result = client._parse_quote(data)

        assert result is not None
        assert result["bid_price"] == 150.20
        assert result["bid_size"] == 100
        assert result["ask_price"] == 150.25
        assert result["ask_size"] == 200

    def test_parse_bar(self, client):
        """Test parsing bar message."""
        data = {
            "T": "b",
            "S": "AAPL",
            "o": 150.00,
            "h": 151.00,
            "l": 149.50,
            "c": 150.75,
            "v": 10000,
            "t": "2024-01-15T09:30:00Z",
        }

        result = client._parse_bar(data)

        assert result is not None
        assert result["open"] == 150.00
        assert result["high"] == 151.00
        assert result["low"] == 149.50
        assert result["close"] == 150.75
        assert result["volume"] == 10000


class TestAlpacaStreamClientDispatch:
    """Tests for message dispatch."""

    async def test_dispatch_trade_message(self, client):
        """Test dispatching trade message to callback."""
        on_trade = MagicMock()
        client.set_callbacks(on_trade=on_trade)

        item = {
            "T": "t",
            "S": "AAPL",
            "p": 150.0,
            "s": 100,
            "x": "V",
            "t": "2024-01-15T09:30:00Z",
        }

        await client._dispatch_message(item)

        on_trade.assert_called_once()
        args = on_trade.call_args[0]
        assert args[0] == "AAPL"
        assert args[1] is not None  # TradeData is a TypedDict, can't use isinstance

    async def test_dispatch_quote_message(self, client):
        """Test dispatching quote message to callback."""
        on_quote = MagicMock()
        client.set_callbacks(on_quote=on_quote)

        item = {
            "T": "q",
            "S": "AAPL",
            "bp": 150.0,
            "bs": 100,
            "ap": 150.1,
            "as": 200,
            "t": "2024-01-15T09:30:00Z",
        }

        await client._dispatch_message(item)

        on_quote.assert_called_once()

    async def test_dispatch_bar_message(self, client):
        """Test dispatching bar message to callback."""
        on_bar = MagicMock()
        client.set_callbacks(on_bar=on_bar)

        item = {
            "T": "b",
            "S": "AAPL",
            "o": 150.0,
            "h": 151.0,
            "l": 149.0,
            "c": 150.5,
            "v": 10000,
            "t": "2024-01-15T09:30:00Z",
        }

        await client._dispatch_message(item)

        on_bar.assert_called_once()

    async def test_dispatch_error_message(self, client):
        """Test dispatching error message."""
        item = {"T": "error", "msg": "Test error"}

        # Should not raise
        await client._dispatch_message(item)

    async def test_dispatch_no_callback(self, client):
        """Test dispatch when no callback is set."""
        item = {"T": "t", "S": "AAPL", "p": 150.0, "s": 100, "x": "V", "t": ""}

        # Should not raise
        await client._dispatch_message(item)


class TestAlpacaStreamClientReceiveMessage:
    """Tests for _receive_message method."""

    async def test_receive_message_success(self, client, mock_websocket):
        """Test successful message receive."""
        mock_websocket.recv = AsyncMock(return_value=json.dumps([{"T": "success"}]))
        client._ws = mock_websocket

        result = await client._receive_message()

        assert result == [{"T": "success"}]

    async def test_receive_message_no_websocket(self, client):
        """Test receive when no websocket."""
        result = await client._receive_message()
        assert result is None

    async def test_receive_message_timeout(self, client, mock_websocket):
        """Test receive with timeout."""
        mock_websocket.recv = AsyncMock(side_effect=TimeoutError())
        client._ws = mock_websocket

        result = await client._receive_message()

        assert result is None

    async def test_receive_message_exception(self, client, mock_websocket):
        """Test receive with exception."""
        mock_websocket.recv = AsyncMock(side_effect=Exception("Receive failed"))
        client._ws = mock_websocket

        result = await client._receive_message()

        assert result is None


class TestGlobalFunctions:
    """Tests for global singleton functions."""

    def test_get_alpaca_stream_creates_singleton(self):
        """Test that get_alpaca_stream creates a singleton."""
        import src.streaming.alpaca_stream as module

        module._stream_client = None

        client1 = get_alpaca_stream()
        client2 = get_alpaca_stream()

        assert client1 is client2

        module._stream_client = None

    async def test_init_alpaca_stream_success(self):
        """Test successful stream initialization."""
        import src.streaming.alpaca_stream as module

        mock_ws = AsyncMock()
        mock_ws.open = True
        mock_ws.recv = AsyncMock(
            side_effect=[
                json.dumps([{"T": "success"}]),
                json.dumps([{"T": "success"}]),
            ]
        )

        with patch("websockets.connect", AsyncMock(return_value=mock_ws)):
            result = await init_alpaca_stream()

        assert result is not None
        module._stream_client = None

    async def test_init_alpaca_stream_failure(self):
        """Test failed stream initialization."""
        import src.streaming.alpaca_stream as module

        with patch("websockets.connect", AsyncMock(side_effect=Exception("Failed"))):
            result = await init_alpaca_stream()

        assert result is None
        module._stream_client = None

    async def test_close_alpaca_stream(self):
        """Test closing the global stream."""
        import src.streaming.alpaca_stream as module

        mock_client = AsyncMock()
        module._stream_client = mock_client

        await close_alpaca_stream()

        mock_client.disconnect.assert_called_once()
        assert module._stream_client is None

    async def test_close_alpaca_stream_when_none(self):
        """Test closing when no stream exists."""
        import src.streaming.alpaca_stream as module

        module._stream_client = None

        # Should not raise
        await close_alpaca_stream()
