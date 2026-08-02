"""External-channel delivery: send, track, and auto-disable failing webhooks.

Runs after the in-app row is committed; every path is best-effort and never
raises into the consumer. Webhook delivery updates the endpoint's tracking
columns, and ``failure_count`` crossing the disable threshold flips the
endpoint off and persists a WEBHOOK_DISABLED notification so the tenant can
see why their integration went quiet.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from llamatrade_db import tenant_session
from llamatrade_db.models.notification import NotificationDelivery, Webhook
from llamatrade_events.idempotency import derive_event_id
from llamatrade_proto.generated import events_pb2, notification_pb2

from src.channels.email import EmailChannel
from src.channels.webhook import WebhookChannel, WebhookResult
from src.email_render import build_html
from src.pipeline import Dispatcher, PendingDelivery, persist_and_plan

logger = logging.getLogger(__name__)

WEBHOOK_DISABLE_THRESHOLD = 25


class DeliveryDispatcher(Dispatcher):
    """Sends pending deliveries over email and webhooks with per-row tracking."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        email: EmailChannel | None = None,
        webhook: WebhookChannel | None = None,
        disable_threshold: int = WEBHOOK_DISABLE_THRESHOLD,
    ) -> None:
        self._session_factory = session_factory
        self._email = email or EmailChannel()
        self._webhook = webhook or WebhookChannel()
        self._disable_threshold = disable_threshold

    async def dispatch(self, pending: list[PendingDelivery]) -> None:
        for item in pending:
            try:
                if item.channel == notification_pb2.CHANNEL_TYPE_EMAIL:
                    await self._dispatch_email(item)
                elif item.channel == notification_pb2.CHANNEL_TYPE_WEBHOOK:
                    await self._dispatch_webhook(item)
                else:
                    await self._mark(item, ok=False, error="unsupported channel")
            except Exception:
                logger.exception(
                    "delivery %s (channel %s) failed unexpectedly",
                    item.delivery_id,
                    item.channel,
                )

    async def _dispatch_email(self, item: PendingDelivery) -> None:
        ok = await self._email.send(
            item.destination,
            item.rendered.subject,
            item.rendered.text_body,
            html_body=build_html(item.rendered, item.severity),
        )
        await self._mark(item, ok=ok, error=None if ok else "smtp send failed")

    async def _dispatch_webhook(self, item: PendingDelivery) -> None:
        async with tenant_session(item.tenant_id, self._session_factory) as db:
            webhook = await db.get(Webhook, UUID(item.destination))
            if webhook is None or not webhook.is_active:
                await self._mark_in(db, item, ok=False, error="webhook missing or inactive")
                await db.commit()
                return
            payload: dict[str, object] = {
                "category": item.category,
                "title": item.rendered.title,
                "message": item.rendered.message,
                "timestamp": datetime.now(UTC).isoformat(),
            }
            result = await self._webhook.send(
                webhook.url,
                payload,
                secret=webhook.secret,
                headers=dict(webhook.headers) if webhook.headers else None,
            )
            disabled = self._track_webhook(webhook, result)
            await self._mark_in(
                db,
                item,
                ok=result.ok,
                error=None if result.ok else (result.error or f"http_{result.status_code}"),
            )
            if disabled:
                await self._persist_disabled_notice(db, webhook)
            await db.commit()

    def _track_webhook(self, webhook: Webhook, result: WebhookResult) -> bool:
        webhook.last_triggered_at = datetime.now(UTC)
        webhook.last_status_code = result.status_code
        if result.ok:
            webhook.failure_count = 0
            return False
        webhook.failure_count += 1
        if webhook.failure_count >= self._disable_threshold and webhook.is_active:
            webhook.is_active = False
            logger.warning(
                "webhook %s disabled after %d consecutive failures",
                webhook.id,
                webhook.failure_count,
            )
            return True
        return False

    async def _persist_disabled_notice(self, db: AsyncSession, webhook: Webhook) -> None:
        event = events_pb2.NotificationEvent(
            category=events_pb2.NOTIFICATION_CATEGORY_WEBHOOK_DISABLED,
            severity=events_pb2.NOTIFICATION_SEVERITY_ACTIONABLE,
            reason=f"endpoint {webhook.name} ({webhook.url})",
        )
        event_id = derive_event_id(
            str(event.category), str(webhook.tenant_id), str(webhook.id), "disabled"
        )
        result = await persist_and_plan(
            db,
            tenant_id=webhook.tenant_id,
            user_id=None,
            event_id=event_id,
            event=event,
        )
        # Email-only by category spec; recursion is impossible for webhook targets.
        for item in result.deliveries:
            if item.channel == notification_pb2.CHANNEL_TYPE_EMAIL:
                await self._dispatch_email(item)

    async def _mark(self, item: PendingDelivery, *, ok: bool, error: str | None) -> None:
        async with tenant_session(item.tenant_id, self._session_factory) as db:
            await self._mark_in(db, item, ok=ok, error=error)
            await db.commit()

    async def _mark_in(
        self, db: AsyncSession, item: PendingDelivery, *, ok: bool, error: str | None
    ) -> None:
        delivery = await db.scalar(
            select(NotificationDelivery).where(NotificationDelivery.id == item.delivery_id)
        )
        if delivery is None:
            return
        delivery.attempts += 1
        if ok:
            delivery.status = notification_pb2.NOTIFICATION_STATUS_SENT
            delivery.delivered_at = datetime.now(UTC)
            delivery.last_error = None
        else:
            delivery.status = notification_pb2.NOTIFICATION_STATUS_FAILED
            delivery.last_error = error
