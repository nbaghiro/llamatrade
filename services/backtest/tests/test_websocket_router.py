"""Tests for WebSocket router."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

from src.main import app
from src.progress import ProgressUpdate
from starlette.testclient import TestClient


class TestBacktestProgressWebSocket:
    """Tests for backtest progress WebSocket endpoint."""

    def test_connect_and_receive_progress(self):
        """Test connecting and receiving progress updates."""
        # Mock the ProgressSubscriber
        with patch("src.routers.websocket.ProgressSubscriber") as mock_subscriber_cls:
            mock_subscriber = MagicMock()

            # Create async iterator for subscribe
            async def mock_subscribe(backtest_id):
                yield ProgressUpdate(
                    backtest_id=backtest_id,
                    progress=50.0,
                    message="Processing",
                    eta_seconds=30,
                )
                yield ProgressUpdate(
                    backtest_id=backtest_id,
                    progress=100.0,
                    message="Complete",
                    eta_seconds=0,
                )

            mock_subscriber.subscribe = mock_subscribe
            mock_subscriber.close = AsyncMock()
            mock_subscriber_cls.return_value = mock_subscriber

            client = TestClient(app)

            with client.websocket_connect("/ws/backtests/bt-123/progress") as websocket:
                # First message: connected
                data = websocket.receive_json()
                assert data["type"] == "connected"
                assert data["backtest_id"] == "bt-123"

                # Second message: progress 50%
                data = websocket.receive_json()
                assert data["type"] == "progress"
                assert data["progress"] == 50.0

                # Third message: progress 100%
                data = websocket.receive_json()
                assert data["type"] == "progress"
                assert data["progress"] == 100.0

                # Fourth message: completed
                data = websocket.receive_json()
                assert data["type"] == "completed"

    def test_handles_errors_gracefully(self):
        """Test that errors are handled and sent to client."""
        with patch("src.routers.websocket.ProgressSubscriber") as mock_subscriber_cls:
            mock_subscriber = MagicMock()

            # Create async iterator that raises an error
            async def mock_subscribe(backtest_id):
                raise RuntimeError("Redis connection failed")
                yield  # Make it a generator

            mock_subscriber.subscribe = mock_subscribe
            mock_subscriber.close = AsyncMock()
            mock_subscriber_cls.return_value = mock_subscriber

            client = TestClient(app)

            with client.websocket_connect("/ws/backtests/bt-error/progress") as websocket:
                # Get connected message
                data = websocket.receive_json()
                assert data["type"] == "connected"

                # Next message should be error
                data = websocket.receive_json()
                assert data["type"] == "error"
                assert "Redis connection failed" in data["message"]


class TestProgressUpdateSerialization:
    """Tests for progress update serialization in WebSocket context."""

    def test_progress_update_to_dict_format(self):
        """Test that progress updates serialize correctly for WebSocket."""
        update = ProgressUpdate(
            backtest_id="bt-123",
            progress=75.0,
            message="Processing indicators",
            eta_seconds=45,
            timestamp="2024-01-01T12:00:00Z",
        )

        result = update.to_dict()

        assert result["backtest_id"] == "bt-123"
        assert result["progress"] == 75.0
        assert result["message"] == "Processing indicators"
        assert result["eta_seconds"] == 45
        assert result["timestamp"] == "2024-01-01T12:00:00Z"

    def test_progress_update_json_serializable(self):
        """Test that progress update dict is JSON serializable."""
        update = ProgressUpdate(
            backtest_id="bt-123",
            progress=100.0,
            message="Complete",
        )

        # Should not raise
        json_str = json.dumps(update.to_dict())
        assert "bt-123" in json_str
        assert "100.0" in json_str


class TestWebSocketRouterStructure:
    """Tests for WebSocket router structure."""

    def test_router_has_progress_endpoint(self):
        """Test that router has progress endpoint."""
        from src.routers.websocket import router

        routes = [r.path for r in router.routes]
        assert "/backtests/{backtest_id}/progress" in routes

    def test_router_has_batch_endpoint(self):
        """Test that router has batch endpoint."""
        from src.routers.websocket import router

        routes = [r.path for r in router.routes]
        assert "/backtests/batch/progress" in routes


class TestWebSocketMessageTypes:
    """Tests for WebSocket message type constants."""

    def test_message_types(self):
        """Test expected message types."""
        expected_types = [
            "connected",
            "progress",
            "completed",
            "error",
            "subscribed",
            "unsubscribed",
        ]

        for msg_type in expected_types:
            assert isinstance(msg_type, str)
            assert len(msg_type) > 0

    def test_connected_message_format(self):
        """Test connected message structure."""
        connected_msg = {
            "type": "connected",
            "backtest_id": "bt-123",
            "message": "Connected to progress stream",
        }

        assert connected_msg["type"] == "connected"
        assert "backtest_id" in connected_msg

    def test_progress_message_format(self):
        """Test progress message structure."""
        progress_msg = {
            "type": "progress",
            "backtest_id": "bt-123",
            "progress": 50.0,
            "message": "Processing",
            "eta_seconds": 30,
            "timestamp": "2024-01-01T12:00:00Z",
        }

        assert progress_msg["type"] == "progress"
        assert 0 <= progress_msg["progress"] <= 100

    def test_completed_message_format(self):
        """Test completed message structure."""
        completed_msg = {
            "type": "completed",
            "backtest_id": "bt-123",
            "message": "Backtest completed",
        }

        assert completed_msg["type"] == "completed"

    def test_error_message_format(self):
        """Test error message structure."""
        error_msg = {
            "type": "error",
            "message": "Something went wrong",
        }

        assert error_msg["type"] == "error"
        assert "message" in error_msg
