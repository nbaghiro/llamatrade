"""Notification Service - Pydantic schemas."""

from datetime import datetime
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
    AlertStatus as AlertStatusEnum,
)
from llamatrade_proto.generated.notification_pb2 import (
    ChannelType as ChannelTypeEnum,
)
from llamatrade_proto.generated.notification_pb2 import (
    NotificationPriority as NotificationPriorityEnum,
)
from llamatrade_proto.generated.notification_pb2 import (
    NotificationStatus as NotificationStatusEnum,
)
from llamatrade_proto.generated.notification_pb2 import (
    NotificationType as NotificationTypeEnum,
)

# ===================
# Conversion helpers: proto int -> str (for display/API)
# ===================

_CHANNEL_TYPE_PREFIX = "CHANNEL_TYPE_"
_NOTIFICATION_TYPE_PREFIX = "NOTIFICATION_TYPE_"
_ALERT_CONDITION_TYPE_PREFIX = "ALERT_CONDITION_TYPE_"
_ALERT_STATUS_PREFIX = "ALERT_STATUS_"
_NOTIFICATION_STATUS_PREFIX = "NOTIFICATION_STATUS_"
_NOTIFICATION_PRIORITY_PREFIX = "NOTIFICATION_PRIORITY_"


def channel_type_to_str(value: int) -> str:
    """Convert ChannelType proto int to string."""
    name = ChannelTypeEnum.Name(cast(ChannelTypeEnum.ValueType, value))
    if name.startswith(_CHANNEL_TYPE_PREFIX):
        return name[len(_CHANNEL_TYPE_PREFIX) :].lower()
    return name.lower()


def notification_type_to_str(value: int) -> str:
    """Convert NotificationType proto int to string."""
    name = NotificationTypeEnum.Name(cast(NotificationTypeEnum.ValueType, value))
    if name.startswith(_NOTIFICATION_TYPE_PREFIX):
        return name[len(_NOTIFICATION_TYPE_PREFIX) :].lower()
    return name.lower()


def alert_condition_type_to_str(value: int) -> str:
    """Convert AlertConditionType proto int to string."""
    name = AlertConditionTypeEnum.Name(cast(AlertConditionTypeEnum.ValueType, value))
    if name.startswith(_ALERT_CONDITION_TYPE_PREFIX):
        return name[len(_ALERT_CONDITION_TYPE_PREFIX) :].lower()
    return name.lower()


def alert_status_to_str(value: int) -> str:
    """Convert AlertStatus proto int to string."""
    name = AlertStatusEnum.Name(cast(AlertStatusEnum.ValueType, value))
    if name.startswith(_ALERT_STATUS_PREFIX):
        return name[len(_ALERT_STATUS_PREFIX) :].lower()
    return name.lower()


def notification_status_to_str(value: int) -> str:
    """Convert NotificationStatus proto int to string."""
    name = NotificationStatusEnum.Name(cast(NotificationStatusEnum.ValueType, value))
    if name.startswith(_NOTIFICATION_STATUS_PREFIX):
        return name[len(_NOTIFICATION_STATUS_PREFIX) :].lower()
    return name.lower()


def notification_priority_to_str(value: int) -> str:
    """Convert NotificationPriority proto int to string."""
    name = NotificationPriorityEnum.Name(cast(NotificationPriorityEnum.ValueType, value))
    if name.startswith(_NOTIFICATION_PRIORITY_PREFIX):
        return name[len(_NOTIFICATION_PRIORITY_PREFIX) :].lower()
    return name.lower()


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


# NotificationPriority is now imported from proto as NotificationPriorityEnum


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
    priority: int  # NotificationPriority proto value
    subject: str
    message: str
    status: int  # NotificationStatus proto value
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
