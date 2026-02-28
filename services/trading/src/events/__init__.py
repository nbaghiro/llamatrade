"""Event sourcing infrastructure for trading service."""

from src.events.base import TradingEvent
from src.events.store import EventStore, create_event_store
from src.events.trading_events import (
    CircuitBreakerReset,
    CircuitBreakerTriggered,
    OrderAccepted,
    OrderCancelled,
    OrderFilled,
    OrderPartiallyFilled,
    OrderRejected,
    OrderSubmitted,
    PositionClosed,
    PositionIncreased,
    PositionOpened,
    PositionReduced,
    SessionPaused,
    SessionResumed,
    SessionStarted,
    SessionStopped,
    SignalGenerated,
    SignalRejected,
)

__all__ = [
    # Base
    "TradingEvent",
    # Store
    "EventStore",
    "create_event_store",
    # Signal events
    "SignalGenerated",
    "SignalRejected",
    # Order events
    "OrderSubmitted",
    "OrderAccepted",
    "OrderFilled",
    "OrderPartiallyFilled",
    "OrderCancelled",
    "OrderRejected",
    # Position events
    "PositionOpened",
    "PositionIncreased",
    "PositionReduced",
    "PositionClosed",
    # Session events
    "SessionStarted",
    "SessionStopped",
    "SessionPaused",
    "SessionResumed",
    # Circuit breaker events
    "CircuitBreakerTriggered",
    "CircuitBreakerReset",
]
