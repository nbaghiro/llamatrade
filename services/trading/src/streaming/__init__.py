"""Streaming infrastructure for real-time trading updates.

This module provides Redis pub/sub based streaming for order and position
updates, enabling real-time notifications to connected clients.

Usage:
    # Publisher (in executors/runner)
    from src.streaming import get_trading_event_publisher, OrderUpdate

    publisher = get_trading_event_publisher()
    await publisher.publish_order_update(session_id, order_update)

    # Subscriber (in gRPC streaming endpoints)
    from src.streaming import get_trading_event_subscriber

    subscriber = get_trading_event_subscriber()
    async for update in subscriber.subscribe_orders(session_id):
        yield update
"""

from src.streaming.publisher import (
    OrderUpdate,
    PositionUpdate,
    TradingEventPublisher,
    get_trading_event_publisher,
)
from src.streaming.subscriber import (
    TradingEventSubscriber,
    get_trading_event_subscriber,
)

__all__ = [
    "OrderUpdate",
    "PositionUpdate",
    "TradingEventPublisher",
    "TradingEventSubscriber",
    "get_trading_event_publisher",
    "get_trading_event_subscriber",
]
