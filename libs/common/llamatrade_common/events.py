"""Event schemas for async messaging between services."""

from datetime import datetime
from enum import StrEnum
from typing import TypedDict, cast
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class EventData(TypedDict, total=False):
    """Base event data structure."""

    # Common fields across event types
    id: str
    email: str
    roles: list[str]
    order_id: str
    symbol: str
    side: str
    qty: float
    price: float
    order_type: str
    commission: float
    backtest_id: str
    progress_percent: float
    current_date: str
    message: str
    total_return: float
    sharpe_ratio: float
    max_drawdown: float
    total_trades: int
    strategy_id: str
    signal_type: str
    confidence: float
    timestamp: str
    volume: int
    bid: float
    ask: float


class EventMetadata(TypedDict, total=False):
    """Event metadata."""

    source_service: str
    correlation_id: str
    trace_id: str
    retry_count: int


class EventType(StrEnum):
    """Event types for inter-service communication."""

    # Auth events
    USER_CREATED = "user.created"
    USER_UPDATED = "user.updated"
    USER_DELETED = "user.deleted"
    TENANT_CREATED = "tenant.created"

    # Strategy events
    STRATEGY_CREATED = "strategy.created"
    STRATEGY_UPDATED = "strategy.updated"
    STRATEGY_DELETED = "strategy.deleted"
    STRATEGY_ACTIVATED = "strategy.activated"
    STRATEGY_DEACTIVATED = "strategy.deactivated"

    # Backtest events
    BACKTEST_STARTED = "backtest.started"
    BACKTEST_PROGRESS = "backtest.progress"
    BACKTEST_COMPLETED = "backtest.completed"
    BACKTEST_FAILED = "backtest.failed"

    # Trading events
    SESSION_STARTED = "trading.session_started"
    SESSION_STOPPED = "trading.session_stopped"
    ORDER_SUBMITTED = "trading.order_submitted"
    ORDER_FILLED = "trading.order_filled"
    ORDER_CANCELLED = "trading.order_cancelled"
    ORDER_REJECTED = "trading.order_rejected"
    SIGNAL_GENERATED = "trading.signal_generated"

    # Market data events
    PRICE_UPDATE = "market.price_update"
    BAR_UPDATE = "market.bar_update"
    QUOTE_UPDATE = "market.quote_update"
    TRADE_UPDATE = "market.trade_update"

    # Portfolio events
    POSITION_OPENED = "portfolio.position_opened"
    POSITION_CLOSED = "portfolio.position_closed"
    POSITION_UPDATED = "portfolio.position_updated"
    PNL_UPDATED = "portfolio.pnl_updated"

    # Notification events
    ALERT_TRIGGERED = "notification.alert_triggered"
    NOTIFICATION_SENT = "notification.sent"
    NOTIFICATION_FAILED = "notification.failed"

    # Billing events
    SUBSCRIPTION_CREATED = "billing.subscription_created"
    SUBSCRIPTION_UPDATED = "billing.subscription_updated"
    SUBSCRIPTION_CANCELLED = "billing.subscription_cancelled"
    PAYMENT_SUCCEEDED = "billing.payment_succeeded"
    PAYMENT_FAILED = "billing.payment_failed"


class Event(BaseModel):
    """Base event schema for all service events."""

    id: UUID = Field(default_factory=uuid4)
    type: EventType
    tenant_id: UUID | None = None
    user_id: UUID | None = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    data: EventData = Field(default_factory=lambda: cast(EventData, {}))
    metadata: EventMetadata = Field(default_factory=lambda: cast(EventMetadata, {}))

    def to_redis_stream(self) -> dict[str, str]:
        """Convert event to Redis stream format."""
        return {
            "id": str(self.id),
            "type": self.type.value,
            "tenant_id": str(self.tenant_id) if self.tenant_id else "",
            "user_id": str(self.user_id) if self.user_id else "",
            "timestamp": self.timestamp.isoformat(),
            "data": self.model_dump_json(include={"data"}).strip('{"data":').rstrip("}"),
            "metadata": self.model_dump_json(include={"metadata"})
            .strip('{"metadata":')
            .rstrip("}"),
        }

    @classmethod
    def from_redis_stream(cls, data: dict[str, str]) -> "Event":
        """Create event from Redis stream data."""
        import json

        return cls(
            id=UUID(data["id"]),
            type=EventType(data["type"]),
            tenant_id=UUID(data["tenant_id"]) if data.get("tenant_id") else None,
            user_id=UUID(data["user_id"]) if data.get("user_id") else None,
            timestamp=datetime.fromisoformat(data["timestamp"]),
            data=json.loads(data.get("data", "{}")),
            metadata=json.loads(data.get("metadata", "{}")),
        )


# Specific event data schemas
class UserCreatedData(BaseModel):
    """Data for USER_CREATED event."""

    email: str
    roles: list[str]


class OrderSubmittedData(BaseModel):
    """Data for ORDER_SUBMITTED event."""

    order_id: UUID
    symbol: str
    side: str
    qty: float
    order_type: str


class OrderFilledData(BaseModel):
    """Data for ORDER_FILLED event."""

    order_id: UUID
    symbol: str
    side: str
    qty: float
    price: float
    commission: float = 0


class BacktestProgressData(BaseModel):
    """Data for BACKTEST_PROGRESS event."""

    backtest_id: UUID
    progress_percent: float
    current_date: str
    message: str | None = None


class BacktestCompletedData(BaseModel):
    """Data for BACKTEST_COMPLETED event."""

    backtest_id: UUID
    total_return: float
    sharpe_ratio: float
    max_drawdown: float
    total_trades: int


class SignalGeneratedData(BaseModel):
    """Data for SIGNAL_GENERATED event."""

    strategy_id: UUID
    symbol: str
    signal_type: str  # buy, sell, close
    price: float
    confidence: float | None = None
    metadata: EventMetadata = Field(default_factory=lambda: cast(EventMetadata, {}))


class PriceUpdateData(BaseModel):
    """Data for PRICE_UPDATE event."""

    symbol: str
    price: float
    timestamp: datetime
    volume: int | None = None
    bid: float | None = None
    ask: float | None = None
