"""Notification business logic: in-app reads, webhook CRUD, preferences."""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from llamatrade_db.models.notification import (
    Alert,
    Notification,
    NotificationChannel,
    Webhook,
)
from llamatrade_proto.generated import events_pb2, notification_pb2

_ALLOWED_SCHEMES = ("https://", "http://")


class WebhookValidationError(ValueError):
    pass


class NotFoundError(LookupError):
    pass


@dataclass(frozen=True)
class NotificationPage:
    items: list[Notification]
    total: int
    unread_count: int


@dataclass(frozen=True)
class ChannelPrefState:
    channel: notification_pb2.ChannelType.ValueType
    enabled: bool
    categories: list[events_pb2.NotificationCategory.ValueType]


PREFERENCE_CHANNELS = (
    notification_pb2.CHANNEL_TYPE_EMAIL,
    notification_pb2.CHANNEL_TYPE_WEBHOOK,
)


class NotificationService:
    """Tenant-scoped operations over the notification tables."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    # --- in-app notifications ---

    async def list_notifications(
        self,
        tenant_id: UUID,
        *,
        unread_only: bool,
        page: int,
        page_size: int,
    ) -> NotificationPage:
        base = select(Notification).where(Notification.tenant_id == tenant_id)
        if unread_only:
            base = base.where(Notification.read_at.is_(None))
        total = await self._db.scalar(select(func.count()).select_from(base.subquery()))
        unread = await self._db.scalar(
            select(func.count())
            .select_from(Notification)
            .where(Notification.tenant_id == tenant_id, Notification.read_at.is_(None))
        )
        rows = await self._db.scalars(
            base.order_by(Notification.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return NotificationPage(
            items=list(rows), total=int(total or 0), unread_count=int(unread or 0)
        )

    async def mark_as_read(self, tenant_id: UUID, *, notification_id: str, mark_all: bool) -> int:
        now = datetime.now(UTC)
        query = select(Notification).where(
            Notification.tenant_id == tenant_id, Notification.read_at.is_(None)
        )
        if not mark_all:
            query = query.where(Notification.id == UUID(notification_id))
        rows = list(await self._db.scalars(query))
        for row in rows:
            row.read_at = now
        return len(rows)

    # --- webhooks ---

    async def list_webhooks(self, tenant_id: UUID) -> list[Webhook]:
        rows = await self._db.scalars(
            select(Webhook)
            .where(Webhook.tenant_id == tenant_id)
            .order_by(Webhook.created_at.desc())
        )
        return list(rows)

    async def create_webhook(
        self,
        tenant_id: UUID,
        user_id: UUID,
        *,
        name: str,
        url: str,
        events: list[int],
    ) -> tuple[Webhook, str]:
        self._validate_webhook(name, url)
        secret = secrets.token_urlsafe(32)
        webhook = Webhook(
            tenant_id=tenant_id,
            name=name.strip(),
            url=url.strip(),
            secret=secret,
            events=list(events),
            created_by=user_id,
        )
        self._db.add(webhook)
        await self._db.flush()
        return webhook, secret

    async def update_webhook(
        self,
        tenant_id: UUID,
        *,
        webhook_id: str,
        name: str,
        url: str,
        events: list[int],
        is_active: bool,
    ) -> Webhook:
        webhook = await self._get_webhook(tenant_id, webhook_id)
        self._validate_webhook(name, url)
        webhook.name = name.strip()
        webhook.url = url.strip()
        webhook.events = list(events)
        if is_active and not webhook.is_active:
            webhook.failure_count = 0
        webhook.is_active = is_active
        return webhook

    async def delete_webhook(self, tenant_id: UUID, *, webhook_id: str) -> None:
        webhook = await self._get_webhook(tenant_id, webhook_id)
        await self._db.delete(webhook)

    async def get_webhook(self, tenant_id: UUID, webhook_id: str) -> Webhook:
        return await self._get_webhook(tenant_id, webhook_id)

    async def _get_webhook(self, tenant_id: UUID, webhook_id: str) -> Webhook:
        try:
            wh_id = UUID(webhook_id)
        except ValueError as e:
            raise WebhookValidationError("webhook_id must be a UUID") from e
        webhook = await self._db.scalar(
            select(Webhook).where(Webhook.tenant_id == tenant_id, Webhook.id == wh_id)
        )
        if webhook is None:
            raise NotFoundError(f"webhook {webhook_id} not found")
        return webhook

    @staticmethod
    def _validate_webhook(name: str, url: str) -> None:
        if not name.strip():
            raise WebhookValidationError("name is required")
        if not url.strip().startswith(_ALLOWED_SCHEMES):
            raise WebhookValidationError("url must be http(s)")

    # --- price alerts ---

    async def list_alerts(self, tenant_id: UUID, *, active_only: bool) -> list[Alert]:
        stmt = select(Alert).where(Alert.tenant_id == tenant_id).order_by(Alert.created_at.desc())
        if active_only:
            stmt = stmt.where(Alert.status == notification_pb2.ALERT_STATUS_ACTIVE)
        return list(await self._db.scalars(stmt))

    async def create_alert(
        self,
        tenant_id: UUID,
        user_id: UUID,
        *,
        name: str,
        description: str,
        condition_type: int,
        symbol: str,
        threshold: str,
        strategy_id: str,
        channels: list[int],
        cooldown_minutes: int,
    ) -> Alert:
        if not name.strip():
            raise WebhookValidationError("name is required")
        if condition_type == notification_pb2.ALERT_CONDITION_TYPE_UNSPECIFIED:
            raise WebhookValidationError("condition type is required")
        condition: dict[str, str] = {"threshold": threshold or "0"}
        if description:
            condition["description"] = description
        if strategy_id:
            condition["strategy_id"] = strategy_id
        alert = Alert(
            tenant_id=tenant_id,
            name=name.strip(),
            alert_type=condition_type,
            symbol=symbol or None,
            condition=condition,
            channels=[int(c) for c in channels],
            cooldown_minutes=cooldown_minutes or 60,
            created_by=user_id,
        )
        self._db.add(alert)
        await self._db.flush()
        return alert

    async def delete_alert(self, tenant_id: UUID, *, alert_id: str) -> None:
        alert = await self._get_alert(tenant_id, alert_id)
        await self._db.delete(alert)

    async def toggle_alert(self, tenant_id: UUID, *, alert_id: str, is_active: bool) -> Alert:
        alert = await self._get_alert(tenant_id, alert_id)
        alert.status = (
            notification_pb2.ALERT_STATUS_ACTIVE
            if is_active
            else notification_pb2.ALERT_STATUS_DISABLED
        )
        return alert

    async def _get_alert(self, tenant_id: UUID, alert_id: str) -> Alert:
        try:
            parsed = UUID(alert_id)
        except ValueError as e:
            raise WebhookValidationError("alert_id must be a UUID") from e
        alert = await self._db.scalar(
            select(Alert).where(Alert.tenant_id == tenant_id, Alert.id == parsed)
        )
        if alert is None:
            raise NotFoundError(f"alert {alert_id} not found")
        return alert

    # --- preferences ---

    async def get_preferences(self, tenant_id: UUID) -> list[ChannelPrefState]:
        rows = {
            int(row.channel_type): row
            for row in await self._db.scalars(
                select(NotificationChannel).where(NotificationChannel.tenant_id == tenant_id)
            )
        }
        states = []
        for channel in PREFERENCE_CHANNELS:
            row = rows.get(int(channel))
            if row is None:
                states.append(ChannelPrefState(channel=channel, enabled=True, categories=[]))
                continue
            prefs = row.preferences or {}
            categories = prefs.get("categories")
            values = categories if isinstance(categories, list) else []
            states.append(
                ChannelPrefState(
                    channel=channel,
                    enabled=row.is_enabled,
                    categories=[events_pb2.NotificationCategory.ValueType(int(c)) for c in values],
                )
            )
        return states

    async def update_preferences(
        self, tenant_id: UUID, user_id: UUID, states: list[ChannelPrefState]
    ) -> list[ChannelPrefState]:
        for state in states:
            if state.channel not in PREFERENCE_CHANNELS:
                continue
            row = await self._db.scalar(
                select(NotificationChannel).where(
                    NotificationChannel.tenant_id == tenant_id,
                    NotificationChannel.channel_type == state.channel,
                )
            )
            preferences = (
                {"categories": [int(c) for c in state.categories]} if state.categories else None
            )
            if row is None:
                self._db.add(
                    NotificationChannel(
                        tenant_id=tenant_id,
                        user_id=user_id,
                        channel_type=state.channel,
                        destination="",
                        is_enabled=state.enabled,
                        preferences=preferences,
                    )
                )
            else:
                row.is_enabled = state.enabled
                row.preferences = preferences
        await self._db.flush()
        return await self.get_preferences(tenant_id)
