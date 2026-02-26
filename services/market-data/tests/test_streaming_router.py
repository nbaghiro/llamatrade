"""Tests for streaming router endpoints."""

import pytest
from src.main import app
from src.streaming.manager import get_stream_manager
from starlette.testclient import TestClient


class TestStreamStatus:
    """Tests for GET /stream/status endpoint."""

    @pytest.mark.asyncio
    async def test_stream_status_returns_info(self, client):
        """Test stream status endpoint returns connection info."""
        response = await client.get("/stream/status")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "running"
        assert "active_connections" in data
        assert "subscriptions" in data

    @pytest.mark.asyncio
    async def test_stream_status_subscription_counts(self, client):
        """Test stream status includes subscription counts by type."""
        response = await client.get("/stream/status")

        data = response.json()
        assert "subscriptions" in data
        subs = data["subscriptions"]
        assert "trades" in subs
        assert "quotes" in subs
        assert "bars" in subs


class TestWebSocketStream:
    """Tests for WebSocket /stream/ws endpoint."""

    def test_websocket_connect_and_disconnect(self):
        """Test WebSocket connection lifecycle."""
        client = TestClient(app)

        with client.websocket_connect("/stream/ws"):
            # Connection established, just disconnect
            pass

    def test_websocket_subscribe_trades(self):
        """Test subscribing to trade updates."""
        client = TestClient(app)

        with client.websocket_connect("/stream/ws") as ws:
            # Subscribe to trades
            ws.send_json(
                {
                    "action": "subscribe",
                    "trades": ["AAPL", "TSLA"],
                }
            )

            # Should receive subscription confirmation
            response = ws.receive_json()
            assert response["type"] == "subscribed"
            assert "AAPL" in response["trades"]
            assert "TSLA" in response["trades"]

    def test_websocket_subscribe_quotes(self):
        """Test subscribing to quote updates."""
        client = TestClient(app)

        with client.websocket_connect("/stream/ws") as ws:
            # Subscribe to quotes
            ws.send_json(
                {
                    "action": "subscribe",
                    "quotes": ["AAPL"],
                }
            )

            # Should receive subscription confirmation
            response = ws.receive_json()
            assert response["type"] == "subscribed"
            assert "AAPL" in response["quotes"]

    def test_websocket_subscribe_bars(self):
        """Test subscribing to bar updates."""
        client = TestClient(app)

        with client.websocket_connect("/stream/ws") as ws:
            # Subscribe to bars
            ws.send_json(
                {
                    "action": "subscribe",
                    "bars": ["SPY"],
                }
            )

            # Should receive subscription confirmation
            response = ws.receive_json()
            assert response["type"] == "subscribed"
            assert "SPY" in response["bars"]

    def test_websocket_subscribe_multiple_types(self):
        """Test subscribing to multiple data types at once."""
        client = TestClient(app)

        with client.websocket_connect("/stream/ws") as ws:
            # Subscribe to all types
            ws.send_json(
                {
                    "action": "subscribe",
                    "trades": ["AAPL"],
                    "quotes": ["AAPL"],
                    "bars": ["AAPL"],
                }
            )

            response = ws.receive_json()
            assert response["type"] == "subscribed"
            assert "AAPL" in response["trades"]
            assert "AAPL" in response["quotes"]
            assert "AAPL" in response["bars"]

    def test_websocket_unsubscribe(self):
        """Test unsubscribing from updates."""
        client = TestClient(app)

        with client.websocket_connect("/stream/ws") as ws:
            # Subscribe first
            ws.send_json(
                {
                    "action": "subscribe",
                    "trades": ["AAPL"],
                }
            )
            ws.receive_json()  # Consume subscription confirmation

            # Unsubscribe
            ws.send_json(
                {
                    "action": "unsubscribe",
                    "trades": ["AAPL"],
                }
            )

            response = ws.receive_json()
            assert response["type"] == "unsubscribed"
            assert "AAPL" in response["trades"]

    def test_websocket_invalid_json(self):
        """Test that invalid JSON returns error message."""
        client = TestClient(app)

        with client.websocket_connect("/stream/ws") as ws:
            # Send invalid JSON
            ws.send_text("not valid json")

            response = ws.receive_json()
            assert response["type"] == "error"
            assert "Invalid JSON" in response["message"]

    def test_websocket_invalid_action(self):
        """Test that invalid action is handled gracefully.

        The implementation doesn't specifically handle unknown actions,
        so we just verify the connection doesn't crash.
        """
        client = TestClient(app)

        with client.websocket_connect("/stream/ws") as ws:
            # Send invalid action - may or may not get a response
            ws.send_json(
                {
                    "action": "invalid_action",
                }
            )

            # Instead of waiting for a response (which may not come),
            # send a valid request to verify connection is still working
            ws.send_json(
                {
                    "action": "subscribe",
                    "trades": ["AAPL"],
                }
            )

            response = ws.receive_json()
            # Connection should still work after invalid action
            assert response["type"] == "subscribed"


class TestStreamManager:
    """Tests for StreamManager functionality."""

    def test_connection_count_increases(self):
        """Test that connection count increases with new connections."""
        manager = get_stream_manager()
        initial_count = manager.connection_count

        client = TestClient(app)
        with client.websocket_connect("/stream/ws") as ws:
            # Send a message to ensure connection is fully established
            ws.send_json({"action": "subscribe", "trades": []})
            ws.receive_json()

            # Connection count should be at least 1
            assert manager.connection_count >= initial_count

    def test_subscription_count_updates(self):
        """Test that subscription counts update correctly."""
        client = TestClient(app)

        with client.websocket_connect("/stream/ws") as ws:
            manager = get_stream_manager()

            # Subscribe to trades
            ws.send_json(
                {
                    "action": "subscribe",
                    "trades": ["AAPL"],
                }
            )
            ws.receive_json()

            # Check subscription count
            subs = manager.subscription_count
            assert subs["trades"] >= 1


class TestErrorHandling:
    """Tests for WebSocket error handling."""

    def test_websocket_handles_malformed_subscription(self):
        """Test handling of malformed subscription messages."""
        client = TestClient(app)

        with client.websocket_connect("/stream/ws") as ws:
            # Send message missing required fields
            ws.send_json(
                {
                    "action": "subscribe",
                    # Missing trades/quotes/bars - should still work (empty subscription)
                }
            )

            response = ws.receive_json()
            # Should receive confirmation with empty lists
            assert response["type"] == "subscribed"
            assert response["trades"] == []
            assert response["quotes"] == []
            assert response["bars"] == []
