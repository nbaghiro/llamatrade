"""Notification and alert models.

Enum columns use PostgreSQL native ENUM types with TypeDecorators for transparent
conversion between proto int values and DB enum strings.

See libs/db/llamatrade_db/models/enum_types.py for TypeDecorator implementations.
"""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Boolean, DateTime, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from llamatrade_db.base import Base, TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin
from llamatrade_db.models._enum_types import (
    AlertConditionTypeType,
    AlertStatusType,
    ChannelTypeType,
    NotificationStatusType,
    NotificationTypeType,
)
from llamatrade_proto.generated import notification_pb2


class Alert(Base, UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin):
    """User-defined price/condition alerts."""

    __tablename__ = "alerts"
    __table_args__ = (
        Index("ix_alerts_tenant_status", "tenant_id", "status"),
        Index("ix_alerts_symbol", "symbol"),
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    alert_type: Mapped[notification_pb2.AlertConditionType.ValueType] = mapped_column(
        AlertConditionTypeType(), nullable=False
    )
    symbol: Mapped[str | None] = mapped_column(String(20), nullable=True)
    condition: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    status: Mapped[int] = mapped_column(AlertStatusType(), default=1, nullable=False)  # ACTIVE=1
    channels: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list
    )  # email, sms, push, webhook
    cooldown_minutes: Mapped[int] = mapped_column(Integer, default=60, nullable=False)
    last_triggered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    trigger_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)


class Notification(Base, UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin):
    """The logical in-app notification row — the durable floor of every flow.

    ``event_id`` is the envelope's deterministic id; the unique index makes the
    consumer's persist idempotent under redelivery. External-channel attempts
    live in ``notification_deliveries``, one row per (notification, target).
    """

    __tablename__ = "notifications"
    __table_args__ = (
        Index("ix_notifications_tenant_created", "tenant_id", "created_at"),
        Index("ix_notifications_user", "user_id"),
        Index("ix_notifications_event_id", "event_id", unique=True),
    )

    event_id: Mapped[str] = mapped_column(String(64), nullable=False)
    user_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    alert_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    category: Mapped[int] = mapped_column(Integer, nullable=False)  # proto NotificationCategory
    severity: Mapped[int] = mapped_column(Integer, nullable=False)  # proto NotificationSeverity
    notification_type: Mapped[notification_pb2.NotificationType.ValueType] = mapped_column(
        NotificationTypeType(), nullable=False
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    data: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class NotificationDelivery(Base, UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin):
    """One external-channel delivery attempt target for a notification."""

    __tablename__ = "notification_deliveries"
    __table_args__ = (
        Index("ix_notification_deliveries_notification", "notification_id"),
        Index("ix_notification_deliveries_tenant_status", "tenant_id", "status"),
    )

    notification_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    channel: Mapped[notification_pb2.ChannelType.ValueType] = mapped_column(
        ChannelTypeType(), nullable=False
    )
    destination: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[int] = mapped_column(
        NotificationStatusType(), default=1, nullable=False
    )  # PENDING=1
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class NotificationChannel(Base, UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin):
    """User's notification channel configuration."""

    __tablename__ = "notification_channels"
    __table_args__ = (Index("ix_notification_channels_tenant_user", "tenant_id", "user_id"),)

    user_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    channel_type: Mapped[notification_pb2.ChannelType.ValueType] = mapped_column(
        ChannelTypeType(), nullable=False
    )
    destination: Mapped[str] = mapped_column(
        String(320), nullable=False
    )  # email address, phone, device token
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    preferences: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, nullable=True
    )  # notification type preferences


class Webhook(Base, UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin):
    """Webhook endpoint for external integrations."""

    __tablename__ = "webhooks"
    __table_args__ = (Index("ix_webhooks_tenant_active", "tenant_id", "is_active"),)

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    secret: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )  # For signature verification
    events: Mapped[list[int]] = mapped_column(
        JSONB, nullable=False, default=list
    )  # NotificationCategory ints; empty = all categories
    headers: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)  # Custom headers
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_triggered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    failure_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_by: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
