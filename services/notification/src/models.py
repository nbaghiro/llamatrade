"""Notification Service - Pydantic schemas."""

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class ChannelType(StrEnum):
    EMAIL = "email"
    SMS = "sms"
    PUSH = "push"
    WEBHOOK = "webhook"
    SLACK = "slack"


class NotificationPriority(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class NotificationStatus(StrEnum):
    PENDING = "pending"
    SENT = "sent"
    DELIVERED = "delivered"
    FAILED = "failed"


class AlertType(StrEnum):
    PRICE_ABOVE = "price_above"
    PRICE_BELOW = "price_below"
    PRICE_CHANGE_PERCENT = "price_change_percent"
    ORDER_FILLED = "order_filled"
    POSITION_OPENED = "position_opened"
    POSITION_CLOSED = "position_closed"
    DAILY_LOSS_LIMIT = "daily_loss_limit"
    STRATEGY_SIGNAL = "strategy_signal"


class AlertCreate(BaseModel):
    type: AlertType
    symbol: str | None = None
    threshold: float | None = None
    channels: list[ChannelType] = Field(default_factory=lambda: [ChannelType.EMAIL])
    message_template: str | None = None


class AlertResponse(BaseModel):
    id: UUID
    type: AlertType
    symbol: str | None
    threshold: float | None
    channels: list[ChannelType]
    is_active: bool
    triggered_count: int
    last_triggered_at: datetime | None
    created_at: datetime


class NotificationResponse(BaseModel):
    id: UUID
    channel: ChannelType
    priority: NotificationPriority
    subject: str
    message: str
    status: NotificationStatus
    sent_at: datetime | None
    delivered_at: datetime | None
    created_at: datetime


class ChannelConfig(BaseModel):
    type: ChannelType
    is_enabled: bool
    config: dict[str, Any] = Field(default_factory=dict)


class WebhookConfig(BaseModel):
    url: str
    secret: str | None = None
    headers: dict[str, str] = Field(default_factory=dict)
    events: list[str] = Field(default_factory=list)
