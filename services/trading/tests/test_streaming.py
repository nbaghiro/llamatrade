"""Tests for trading event streaming infrastructure."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.streaming.publisher import (
    OrderUpdate,
    PositionUpdate,
    TradingEventPublisher,
)
from src.streaming.subscriber import TradingEventSubscriber


@pytest.fixture
def mock_redis() -> MagicMock:
    """Create mock Redis client."""
    redis = MagicMock()
    redis.publish = AsyncMock(return_value=1)
    redis.close = AsyncMock()
    return redis


@pytest.fixture
def mock_pubsub() -> MagicMock:
    """Create mock Redis pubsub."""
    pubsub = MagicMock()
    pubsub.subscribe = AsyncMock()
    pubsub.unsubscribe = AsyncMock()
    pubsub.close = AsyncMock()
    pubsub.get_message = AsyncMock(return_value=None)
    return pubsub


class TestOrderUpdate:
    """Tests for OrderUpdate dataclass."""

    def test_to_dict(self) -> None:
        """Test conversion to dictionary."""
        update = OrderUpdate(
            session_id="session-123",
            order_id="order-456",
            alpaca_order_id="alpaca-789",
            symbol="AAPL",
            side="buy",
            qty=10.0,
            order_type="market",
            status="filled",
            filled_qty=10.0,
            filled_avg_price=150.50,
            update_type="filled",
        )

        result = update.to_dict()

        assert result["session_id"] == "session-123"
        assert result["order_id"] == "order-456"
        assert result["alpaca_order_id"] == "alpaca-789"
        assert result["symbol"] == "AAPL"
        assert result["side"] == "buy"
        assert result["qty"] == 10.0
        assert result["order_type"] == "market"
        assert result["status"] == "filled"
        assert result["filled_qty"] == 10.0
        assert result["filled_avg_price"] == 150.50
        assert result["update_type"] == "filled"
        assert "timestamp" in result

    def test_defaults(self) -> None:
        """Test default values."""
        update = OrderUpdate(
            session_id="session-123",
            order_id="order-456",
            alpaca_order_id=None,
            symbol="AAPL",
            side="buy",
            qty=10.0,
            order_type="market",
            status="submitted",
        )

        assert update.filled_qty == 0.0
        assert update.filled_avg_price is None
        assert update.update_type == "status_change"


class TestPositionUpdate:
    """Tests for PositionUpdate dataclass."""

    def test_to_dict(self) -> None:
        """Test conversion to dictionary."""
        update = PositionUpdate(
            session_id="session-123",
            symbol="AAPL",
            qty=100.0,
            side="long",
            cost_basis=15000.0,
            market_value=15500.0,
            unrealized_pnl=500.0,
            unrealized_pnl_percent=3.33,
            current_price=155.0,
            update_type="opened",
        )

        result = update.to_dict()

        assert result["session_id"] == "session-123"
        assert result["symbol"] == "AAPL"
        assert result["qty"] == 100.0
        assert result["side"] == "long"
        assert result["cost_basis"] == 15000.0
        assert result["market_value"] == 15500.0
        assert result["unrealized_pnl"] == 500.0
        assert result["update_type"] == "opened"


class TestTradingEventPublisher:
    """Tests for TradingEventPublisher."""

    async def test_publish_order_update(self, mock_redis: MagicMock) -> None:
        """Test publishing an order update."""
        with patch("src.streaming.publisher.aioredis.from_url", AsyncMock(return_value=mock_redis)):
            publisher = TradingEventPublisher()
            session_id = uuid4()

            update = OrderUpdate(
                session_id=str(session_id),
                order_id="order-123",
                alpaca_order_id="alpaca-456",
                symbol="AAPL",
                side="buy",
                qty=10.0,
                order_type="market",
                status="filled",
            )

            result = await publisher.publish_order_update(session_id, update)

            assert result == 1
            mock_redis.publish.assert_called_once()
            call_args = mock_redis.publish.call_args
            assert f"trading:orders:{session_id}" in call_args[0][0]

            await publisher.close()

    async def test_publish_position_update(self, mock_redis: MagicMock) -> None:
        """Test publishing a position update."""
        with patch("src.streaming.publisher.aioredis.from_url", AsyncMock(return_value=mock_redis)):
            publisher = TradingEventPublisher()
            session_id = uuid4()

            update = PositionUpdate(
                session_id=str(session_id),
                symbol="AAPL",
                qty=100.0,
                side="long",
                cost_basis=15000.0,
                market_value=15500.0,
                unrealized_pnl=500.0,
                unrealized_pnl_percent=3.33,
                current_price=155.0,
            )

            result = await publisher.publish_position_update(session_id, update)

            assert result == 1
            mock_redis.publish.assert_called_once()
            call_args = mock_redis.publish.call_args
            assert f"trading:positions:{session_id}" in call_args[0][0]

            await publisher.close()

    async def test_publish_order_submitted(self, mock_redis: MagicMock) -> None:
        """Test convenience method for order submitted."""
        with patch("src.streaming.publisher.aioredis.from_url", AsyncMock(return_value=mock_redis)):
            publisher = TradingEventPublisher()
            session_id = uuid4()
            order_id = uuid4()

            result = await publisher.publish_order_submitted(
                session_id=session_id,
                order_id=order_id,
                alpaca_order_id="alpaca-123",
                symbol="AAPL",
                side="buy",
                qty=10.0,
                order_type="market",
            )

            assert result == 1
            await publisher.close()

    async def test_publish_order_filled(self, mock_redis: MagicMock) -> None:
        """Test convenience method for order filled."""
        with patch("src.streaming.publisher.aioredis.from_url", AsyncMock(return_value=mock_redis)):
            publisher = TradingEventPublisher()
            session_id = uuid4()
            order_id = uuid4()

            result = await publisher.publish_order_filled(
                session_id=session_id,
                order_id=order_id,
                alpaca_order_id="alpaca-123",
                symbol="AAPL",
                side="buy",
                qty=10.0,
                order_type="market",
                filled_qty=10.0,
                filled_avg_price=150.50,
            )

            assert result == 1
            await publisher.close()

    async def test_publish_position_opened(self, mock_redis: MagicMock) -> None:
        """Test convenience method for position opened."""
        with patch("src.streaming.publisher.aioredis.from_url", AsyncMock(return_value=mock_redis)):
            publisher = TradingEventPublisher()
            session_id = uuid4()

            result = await publisher.publish_position_opened(
                session_id=session_id,
                symbol="AAPL",
                qty=100.0,
                side="long",
                entry_price=150.0,
            )

            assert result == 1
            await publisher.close()

    async def test_close_without_connection(self) -> None:
        """Test closing publisher without opening connection."""
        publisher = TradingEventPublisher()
        # Should not raise
        await publisher.close()


class TestTradingEventSubscriber:
    """Tests for TradingEventSubscriber."""

    async def test_parse_order_update(self) -> None:
        """Test parsing order update from JSON data."""
        subscriber = TradingEventSubscriber()

        data = {
            "session_id": "session-123",
            "order_id": "order-456",
            "alpaca_order_id": "alpaca-789",
            "symbol": "AAPL",
            "side": "buy",
            "qty": 10.0,
            "order_type": "market",
            "status": "filled",
            "filled_qty": 10.0,
            "filled_avg_price": 150.50,
            "update_type": "filled",
            "timestamp": "2025-01-06T12:00:00Z",
        }

        result = subscriber._parse_order_update(data)

        assert result.session_id == "session-123"
        assert result.order_id == "order-456"
        assert result.symbol == "AAPL"
        assert result.status == "filled"
        assert result.filled_qty == 10.0
        assert result.filled_avg_price == 150.50

    async def test_parse_position_update(self) -> None:
        """Test parsing position update from JSON data."""
        subscriber = TradingEventSubscriber()

        data = {
            "session_id": "session-123",
            "symbol": "AAPL",
            "qty": 100.0,
            "side": "long",
            "cost_basis": 15000.0,
            "market_value": 15500.0,
            "unrealized_pnl": 500.0,
            "unrealized_pnl_percent": 3.33,
            "current_price": 155.0,
            "update_type": "opened",
            "timestamp": "2025-01-06T12:00:00Z",
        }

        result = subscriber._parse_position_update(data)

        assert result.session_id == "session-123"
        assert result.symbol == "AAPL"
        assert result.qty == 100.0
        assert result.unrealized_pnl == 500.0

    async def test_close_without_connection(self) -> None:
        """Test closing subscriber without opening connection."""
        subscriber = TradingEventSubscriber()
        # Should not raise
        await subscriber.close()


class TestPublishSubscribeIntegration:
    """Integration tests for publish/subscribe workflow."""

    async def test_order_roundtrip(self, mock_redis: MagicMock, mock_pubsub: MagicMock) -> None:
        """Test that published order can be received by subscriber."""
        import json

        session_id = uuid4()
        order_id = uuid4()

        # Create the update that will be published
        update = OrderUpdate(
            session_id=str(session_id),
            order_id=str(order_id),
            alpaca_order_id="alpaca-123",
            symbol="AAPL",
            side="buy",
            qty=10.0,
            order_type="market",
            status="filled",
            filled_qty=10.0,
            filled_avg_price=150.50,
            update_type="filled",
        )

        # Simulate the message that pubsub would return
        message_data = json.dumps(update.to_dict())
        mock_pubsub.get_message = AsyncMock(
            side_effect=[
                {
                    "type": "message",
                    "channel": f"trading:orders:{session_id}",
                    "data": message_data,
                },
                None,  # Second call returns None to end iteration
            ]
        )

        mock_redis.pubsub = MagicMock(return_value=mock_pubsub)

        with patch(
            "src.streaming.subscriber.aioredis.from_url", AsyncMock(return_value=mock_redis)
        ):
            subscriber = TradingEventSubscriber()

            received = []
            async for order_update in subscriber.subscribe_orders(session_id, timeout=0.1):
                received.append(order_update)
                break  # Only get one message

            assert len(received) == 1
            assert received[0].order_id == str(order_id)
            assert received[0].symbol == "AAPL"
            assert received[0].status == "filled"

            await subscriber.close()

    async def test_position_roundtrip(self, mock_redis: MagicMock, mock_pubsub: MagicMock) -> None:
        """Test that published position can be received by subscriber."""
        import json

        session_id = uuid4()

        # Create the update that will be published
        update = PositionUpdate(
            session_id=str(session_id),
            symbol="AAPL",
            qty=100.0,
            side="long",
            cost_basis=15000.0,
            market_value=15500.0,
            unrealized_pnl=500.0,
            unrealized_pnl_percent=3.33,
            current_price=155.0,
            update_type="opened",
        )

        # Simulate the message that pubsub would return
        message_data = json.dumps(update.to_dict())
        mock_pubsub.get_message = AsyncMock(
            side_effect=[
                {
                    "type": "message",
                    "channel": f"trading:positions:{session_id}",
                    "data": message_data,
                },
                None,
            ]
        )

        mock_redis.pubsub = MagicMock(return_value=mock_pubsub)

        with patch(
            "src.streaming.subscriber.aioredis.from_url", AsyncMock(return_value=mock_redis)
        ):
            subscriber = TradingEventSubscriber()

            received = []
            async for position_update in subscriber.subscribe_positions(session_id, timeout=0.1):
                received.append(position_update)
                break

            assert len(received) == 1
            assert received[0].symbol == "AAPL"
            assert received[0].qty == 100.0
            assert received[0].unrealized_pnl == 500.0

            await subscriber.close()
