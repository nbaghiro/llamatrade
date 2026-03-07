"""Notification Service - Pydantic schemas."""

from datetime import datetime
from enum import StrEnum
from typing import TypedDict, cast
from uuid import UUID

from pydantic import BaseModel, Field

from llamatrade_proto.generated.notification_pb2 import (
    CHANNEL_TYPE_EMAIL,
)
from llamatrade_proto.generated.notification_pb2 import (
    AlertConditionType as AlertConditionTypeEnum,
)
from llamatrade_proto.generated.notification_pb2 import (
    ChannelType as ChannelTypeEnum,
)
from llamatrade_proto.generated.notification_pb2 import (
    NotificationType as NotificationTypeEnum,
)

# ===================
# DB-only status constants (no proto definition)
# ===================

# AlertStatus - used for tracking alert state
ALERT_STATUS_ACTIVE = 1
ALERT_STATUS_TRIGGERED = 2
ALERT_STATUS_DISABLED = 3

# NotificationStatus - used for tracking notification delivery
NOTIFICATION_STATUS_PENDING = 1
NOTIFICATION_STATUS_SENT = 2
NOTIFICATION_STATUS_FAILED = 3
NOTIFICATION_STATUS_READ = 4

# ===================
# Conversion helpers: proto int -> str (for display/API)
# ===================

_CHANNEL_TYPE_PREFIX = "CHANNEL_TYPE_"
_NOTIFICATION_TYPE_PREFIX = "NOTIFICATION_TYPE_"
_ALERT_CONDITION_TYPE_PREFIX = "ALERT_CONDITION_TYPE_"

_ALERT_STATUS_TO_STR: dict[int, str] = {
    ALERT_STATUS_ACTIVE: "active",
    ALERT_STATUS_TRIGGERED: "triggered",
    ALERT_STATUS_DISABLED: "disabled",
}

_NOTIFICATION_STATUS_TO_STR: dict[int, str] = {
    NOTIFICATION_STATUS_PENDING: "pending",
    NOTIFICATION_STATUS_SENT: "sent",
    NOTIFICATION_STATUS_FAILED: "failed",
    NOTIFICATION_STATUS_READ: "read",
}


def channel_type_to_str(value: int) -> str:
    """Convert ChannelType proto int to string."""
    name = ChannelTypeEnum.Name(value)
    if name.startswith(_CHANNEL_TYPE_PREFIX):
        return name[len(_CHANNEL_TYPE_PREFIX) :].lower()
    return name.lower()


def notification_type_to_str(value: int) -> str:
    """Convert NotificationType proto int to string."""
    name = NotificationTypeEnum.Name(value)
    if name.startswith(_NOTIFICATION_TYPE_PREFIX):
        return name[len(_NOTIFICATION_TYPE_PREFIX) :].lower()
    return name.lower()


def alert_condition_type_to_str(value: int) -> str:
    """Convert AlertConditionType proto int to string."""
    name = AlertConditionTypeEnum.Name(value)
    if name.startswith(_ALERT_CONDITION_TYPE_PREFIX):
        return name[len(_ALERT_CONDITION_TYPE_PREFIX) :].lower()
    return name.lower()


def alert_status_to_str(value: int) -> str:
    """Convert AlertStatus int to string."""
    return _ALERT_STATUS_TO_STR.get(value, "unknown")


def notification_status_to_str(value: int) -> str:
    """Convert NotificationStatus int to string."""
    return _NOTIFICATION_STATUS_TO_STR.get(value, "unknown")


class EmailConfig(TypedDict, total=False):
    """Email channel configuration."""

    smtp_host: str
    smtp_port: int
    from_address: str
    reply_to: str


class SMSConfig(TypedDict, total=False):
    """SMS channel configuration."""

    provider: str  # twilio, etc.
    from_number: str


class PushConfig(TypedDict, total=False):
    """Push notification configuration."""

    provider: str  # firebase, apns
    device_token: str


class WebhookChannelConfig(TypedDict, total=False):
    """Webhook channel configuration."""

    url: str
    secret: str
    headers: dict[str, str]


class SlackConfig(TypedDict, total=False):
    """Slack channel configuration."""

    webhook_url: str
    channel: str


# Union of all channel configs
ChannelConfigUnion = EmailConfig | SMSConfig | PushConfig | WebhookChannelConfig | SlackConfig


class NotificationPriority(StrEnum):
    """Notification priority (service-specific, not proto-defined)."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AlertCreate(BaseModel):
    type: int  # AlertConditionType proto value
    symbol: str | None = None
    threshold: float | None = None
    channels: list[int] = Field(
        default_factory=lambda: [CHANNEL_TYPE_EMAIL]
    )  # ChannelType proto values
    message_template: str | None = None


class AlertResponse(BaseModel):
    id: UUID
    type: int  # AlertConditionType proto value
    symbol: str | None
    threshold: float | None
    channels: list[int]  # ChannelType proto values
    is_active: bool
    triggered_count: int
    last_triggered_at: datetime | None
    created_at: datetime


class NotificationResponse(BaseModel):
    id: UUID
    channel: int  # ChannelType proto value
    priority: NotificationPriority
    subject: str
    message: str
    status: int  # NotificationStatus value (DB-only)
    sent_at: datetime | None
    delivered_at: datetime | None
    created_at: datetime


class ChannelConfig(BaseModel):
    type: int  # ChannelType proto value
    is_enabled: bool
    config: ChannelConfigUnion = Field(default_factory=lambda: cast(ChannelConfigUnion, {}))


class WebhookConfig(BaseModel):
    url: str
    secret: str | None = None
    headers: dict[str, str] = Field(default_factory=dict)
    events: list[str] = Field(default_factory=list)
