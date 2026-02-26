"""Tests for progress tracking module."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from src.progress import ProgressPublisher, ProgressSubscriber, ProgressUpdate


class TestProgressUpdate:
    """Tests for ProgressUpdate dataclass."""

    def test_basic_creation(self):
        """Test creating a progress update."""
        update = ProgressUpdate(
            backtest_id="bt-123",
            progress=50.0,
            message="Processing...",
        )

        assert update.backtest_id == "bt-123"
        assert update.progress == 50.0
        assert update.message == "Processing..."
        assert update.eta_seconds is None

    def test_with_eta(self):
        """Test creating with ETA."""
        update = ProgressUpdate(
            backtest_id="bt-123",
            progress=25.0,
            message="Loading data",
            eta_seconds=120,
        )

        assert update.eta_seconds == 120

    def test_with_timestamp(self):
        """Test creating with timestamp."""
        ts = "2024-01-01T12:00:00+00:00"
        update = ProgressUpdate(
            backtest_id="bt-123",
            progress=100.0,
            message="Complete",
            timestamp=ts,
        )

        assert update.timestamp == ts

    def test_to_dict_basic(self):
        """Test converting to dict."""
        update = ProgressUpdate(
            backtest_id="bt-123",
            progress=75.0,
            message="Calculating metrics",
        )

        result = update.to_dict()

        assert result["backtest_id"] == "bt-123"
        assert result["progress"] == 75.0
        assert result["message"] == "Calculating metrics"
        assert result["eta_seconds"] is None
        assert "timestamp" in result  # Auto-generated

    def test_to_dict_with_provided_timestamp(self):
        """Test to_dict uses provided timestamp."""
        ts = "2024-01-01T12:00:00+00:00"
        update = ProgressUpdate(
            backtest_id="bt-123",
            progress=100.0,
            message="Done",
            timestamp=ts,
        )

        result = update.to_dict()

        assert result["timestamp"] == ts

    def test_to_dict_auto_timestamp(self):
        """Test to_dict generates timestamp when not provided."""
        update = ProgressUpdate(
            backtest_id="bt-123",
            progress=50.0,
            message="Working",
        )

        result = update.to_dict()

        # Should be an ISO format timestamp
        assert "T" in result["timestamp"]


class TestProgressPublisher:
    """Tests for ProgressPublisher class."""

    def test_init_default_url(self):
        """Test initialization with default URL."""
        publisher = ProgressPublisher()
        assert publisher.redis_url == "redis://localhost:47379/0"
        assert publisher._redis is None

    def test_init_custom_url(self):
        """Test initialization with custom URL."""
        publisher = ProgressPublisher(redis_url="redis://custom:6379/1")
        assert publisher.redis_url == "redis://custom:6379/1"

    @pytest.mark.asyncio
    async def test_get_redis_creates_connection(self):
        """Test that _get_redis creates connection on first call."""
        with patch("src.progress.aioredis") as mock_aioredis:
            mock_redis = AsyncMock()
            mock_aioredis.from_url = AsyncMock(return_value=mock_redis)

            publisher = ProgressPublisher()
            result = await publisher._get_redis()

            assert result == mock_redis
            mock_aioredis.from_url.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_redis_reuses_connection(self):
        """Test that _get_redis reuses existing connection."""
        with patch("src.progress.aioredis") as mock_aioredis:
            mock_redis = AsyncMock()
            mock_aioredis.from_url = AsyncMock(return_value=mock_redis)

            publisher = ProgressPublisher()
            await publisher._get_redis()
            await publisher._get_redis()

            # Should only create connection once
            mock_aioredis.from_url.assert_called_once()

    @pytest.mark.asyncio
    async def test_publish(self):
        """Test publishing progress update."""
        with patch("src.progress.aioredis") as mock_aioredis:
            mock_redis = AsyncMock()
            mock_redis.publish = AsyncMock()
            mock_aioredis.from_url = AsyncMock(return_value=mock_redis)

            publisher = ProgressPublisher()
            await publisher.publish(
                backtest_id="bt-123",
                progress=50.0,
                message="Halfway there",
                eta_seconds=60,
            )

            mock_redis.publish.assert_called_once()
            call_args = mock_redis.publish.call_args
            assert call_args[0][0] == "backtest:progress:bt-123"

            # Verify published data
            published_data = json.loads(call_args[0][1])
            assert published_data["backtest_id"] == "bt-123"
            assert published_data["progress"] == 50.0
            assert published_data["message"] == "Halfway there"
            assert published_data["eta_seconds"] == 60

    @pytest.mark.asyncio
    async def test_close(self):
        """Test closing publisher."""
        with patch("src.progress.aioredis") as mock_aioredis:
            mock_redis = AsyncMock()
            mock_redis.close = AsyncMock()
            mock_aioredis.from_url = AsyncMock(return_value=mock_redis)

            publisher = ProgressPublisher()
            await publisher._get_redis()  # Create connection
            await publisher.close()

            mock_redis.close.assert_called_once()
            assert publisher._redis is None

    @pytest.mark.asyncio
    async def test_close_without_connection(self):
        """Test closing without connection is safe."""
        publisher = ProgressPublisher()
        await publisher.close()  # Should not raise


class TestProgressSubscriber:
    """Tests for ProgressSubscriber class."""

    def test_init_default_url(self):
        """Test initialization with default URL."""
        subscriber = ProgressSubscriber()
        assert subscriber.redis_url == "redis://localhost:47379/0"
        assert subscriber._redis is None
        assert subscriber._pubsub is None

    def test_init_custom_url(self):
        """Test initialization with custom URL."""
        subscriber = ProgressSubscriber(redis_url="redis://custom:6379/1")
        assert subscriber.redis_url == "redis://custom:6379/1"

    @pytest.mark.asyncio
    async def test_get_redis_creates_connection(self):
        """Test that _get_redis creates connection on first call."""
        with patch("src.progress.aioredis") as mock_aioredis:
            mock_redis = AsyncMock()
            mock_aioredis.from_url = AsyncMock(return_value=mock_redis)

            subscriber = ProgressSubscriber()
            result = await subscriber._get_redis()

            assert result == mock_redis
            mock_aioredis.from_url.assert_called_once()

    @pytest.mark.asyncio
    async def test_close(self):
        """Test closing subscriber."""
        with patch("src.progress.aioredis") as mock_aioredis:
            mock_redis = AsyncMock()
            mock_redis.close = AsyncMock()
            mock_pubsub = AsyncMock()
            mock_pubsub.close = AsyncMock()
            mock_aioredis.from_url = AsyncMock(return_value=mock_redis)

            subscriber = ProgressSubscriber()
            subscriber._redis = mock_redis
            subscriber._pubsub = mock_pubsub

            await subscriber.close()

            mock_pubsub.close.assert_called_once()
            mock_redis.close.assert_called_once()
            assert subscriber._redis is None
            assert subscriber._pubsub is None

    @pytest.mark.asyncio
    async def test_close_without_connections(self):
        """Test closing without connections is safe."""
        subscriber = ProgressSubscriber()
        await subscriber.close()  # Should not raise


class TestProgressIntegration:
    """Integration-style tests for progress module."""

    @pytest.mark.asyncio
    async def test_publisher_subscriber_flow(self):
        """Test publisher and subscriber work together."""
        with patch("src.progress.aioredis") as mock_aioredis:
            # Set up mock Redis
            mock_redis = AsyncMock()
            mock_pubsub = AsyncMock()

            # Mock pubsub listen to yield messages
            async def mock_listen():
                yield {
                    "type": "message",
                    "data": json.dumps(
                        {
                            "backtest_id": "bt-123",
                            "progress": 50.0,
                            "message": "Processing",
                            "eta_seconds": 30,
                            "timestamp": "2024-01-01T12:00:00Z",
                        }
                    ),
                }
                yield {
                    "type": "message",
                    "data": json.dumps(
                        {
                            "backtest_id": "bt-123",
                            "progress": 100.0,
                            "message": "Complete",
                            "eta_seconds": 0,
                            "timestamp": "2024-01-01T12:01:00Z",
                        }
                    ),
                }

            mock_pubsub.listen = mock_listen
            mock_pubsub.subscribe = AsyncMock()
            mock_pubsub.unsubscribe = AsyncMock()
            mock_redis.pubsub = MagicMock(return_value=mock_pubsub)
            mock_aioredis.from_url = AsyncMock(return_value=mock_redis)

            subscriber = ProgressSubscriber()

            updates = []
            async for update in subscriber.subscribe("bt-123"):
                updates.append(update)

            assert len(updates) == 2
            assert updates[0].progress == 50.0
            assert updates[1].progress == 100.0
            assert updates[1].message == "Complete"

    @pytest.mark.asyncio
    async def test_subscribe_stops_at_100_percent(self):
        """Test that subscribe stops when progress reaches 100%."""
        with patch("src.progress.aioredis") as mock_aioredis:
            mock_redis = AsyncMock()
            mock_pubsub = AsyncMock()

            # Mock pubsub listen with 100% progress
            async def mock_listen():
                yield {
                    "type": "message",
                    "data": json.dumps(
                        {
                            "backtest_id": "bt-123",
                            "progress": 100.0,
                            "message": "Done",
                        }
                    ),
                }
                # This should not be yielded
                yield {
                    "type": "message",
                    "data": json.dumps(
                        {
                            "backtest_id": "bt-123",
                            "progress": 100.0,
                            "message": "Still done",
                        }
                    ),
                }

            mock_pubsub.listen = mock_listen
            mock_pubsub.subscribe = AsyncMock()
            mock_pubsub.unsubscribe = AsyncMock()
            mock_redis.pubsub = MagicMock(return_value=mock_pubsub)
            mock_aioredis.from_url = AsyncMock(return_value=mock_redis)

            subscriber = ProgressSubscriber()

            updates = []
            async for update in subscriber.subscribe("bt-123"):
                updates.append(update)

            # Should only get one update (stops at 100%)
            assert len(updates) == 1

    @pytest.mark.asyncio
    async def test_subscribe_ignores_non_message_types(self):
        """Test that subscribe ignores non-message type events."""
        with patch("src.progress.aioredis") as mock_aioredis:
            mock_redis = AsyncMock()
            mock_pubsub = AsyncMock()

            async def mock_listen():
                yield {"type": "subscribe", "channel": "backtest:progress:bt-123"}
                yield {
                    "type": "message",
                    "data": json.dumps(
                        {
                            "backtest_id": "bt-123",
                            "progress": 100.0,
                            "message": "Done",
                        }
                    ),
                }

            mock_pubsub.listen = mock_listen
            mock_pubsub.subscribe = AsyncMock()
            mock_pubsub.unsubscribe = AsyncMock()
            mock_redis.pubsub = MagicMock(return_value=mock_pubsub)
            mock_aioredis.from_url = AsyncMock(return_value=mock_redis)

            subscriber = ProgressSubscriber()

            updates = []
            async for update in subscriber.subscribe("bt-123"):
                updates.append(update)

            # Should only get message type events
            assert len(updates) == 1
            assert updates[0].progress == 100.0
