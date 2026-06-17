"""Streaming infrastructure for real-time trading updates.

This module provides Redis Streams based tail fan-out for order and position
updates, enabling real-time notifications to connected clients. Updates are the
proto ``trading_pb2.OrderUpdate`` / ``trading_pb2.PositionUpdate`` messages,
carried on the bus via ``OrderEvents`` / ``PositionEvents``.

Usage:
    # Publisher (in executors/runner)
    from src.streaming import get_trading_event_publisher

    publisher = get_trading_event_publisher()
    await publisher.publish_order_submitted(session_id, ...)

    # Subscriber (in gRPC streaming endpoints)
    from src.streaming import get_trading_event_subscriber

    subscriber = get_trading_event_subscriber()
    async for cursor, update in subscriber.tail_orders(session_id):
        yield update
"""

from src.streaming.publisher import (
    TradingEventPublisher,
    get_trading_event_publisher,
)
from src.streaming.subscriber import (
    TradingEventSubscriber,
    get_trading_event_subscriber,
)

__all__ = [
    "TradingEventPublisher",
    "TradingEventSubscriber",
    "get_trading_event_publisher",
    "get_trading_event_subscriber",
]
