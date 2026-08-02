"""The consumer pipeline: envelope -> persist (durable floor) -> deliver.

Runs as the handler of a ``StreamConsumer`` on the ``notifications`` stream:
decode failures are poison (DLQ), transient DB errors raise and redeliver, and
the unique ``event_id`` index makes redelivered persists no-ops. External
delivery happens after the row is committed and never raises into the
consumer, so a slow webhook or SMTP outage cannot stall ingestion.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from llamatrade_db import tenant_session
from llamatrade_db.models.auth import User
from llamatrade_db.models.notification import (
    Notification,
    NotificationChannel,
    NotificationDelivery,
    Webhook,
)
from llamatrade_events import EventEnvelope, PoisonError, UnknownEventTypeError
from llamatrade_events.catalog.notifications import NotificationEvents
from llamatrade_proto.generated import events_pb2, notification_pb2

from src.preferences import (
    EMAIL,
    PINNED_SEVERITIES,
    WEBHOOK,
    channels_for,
    effective_severity,
    spec_for,
)
from src.templates import Rendered, render

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PendingDelivery:
    delivery_id: UUID
    tenant_id: UUID
    channel: int
    destination: str
    rendered: Rendered
    category: int
    severity: int


@dataclass(frozen=True)
class PersistResult:
    notification_id: UUID | None  # None = event_id conflict (already persisted)
    deliveries: list[PendingDelivery]


NotificationHandler = Callable[[EventEnvelope], Awaitable[None]]


class AlertMatcher:
    """Seam for event-driven user alerts (implemented by src/alerts/engine.py)."""

    async def match(
        self, tenant_id: UUID, event: events_pb2.NotificationEvent
    ) -> None:  # pragma: no cover
        raise NotImplementedError


class Dispatcher:
    """Delivery seam the pipeline hands committed work to (see delivery.py)."""

    async def dispatch(self, pending: list[PendingDelivery]) -> None:  # pragma: no cover
        raise NotImplementedError


async def email_recipients(
    db: AsyncSession, tenant_id: UUID, *, ignore_disabled: bool = False
) -> list[str]:
    """Email targets: the enabled EMAIL channel override, else the tenant's users.

    ``ignore_disabled`` serves pinned severities: a disabled email channel must
    not silence critical or security notifications.
    """
    row = await db.scalar(
        select(NotificationChannel).where(
            NotificationChannel.tenant_id == tenant_id,
            NotificationChannel.channel_type == notification_pb2.CHANNEL_TYPE_EMAIL,
        )
    )
    if row is not None:
        if not row.is_enabled and not ignore_disabled:
            return []
        if row.destination:
            return [row.destination]
    emails = await db.scalars(
        select(User.email).where(User.tenant_id == tenant_id, User.is_active.is_(True))
    )
    return [e for e in emails if e]


async def _channel_prefs(db: AsyncSession, tenant_id: UUID) -> dict[int, dict[str, object] | None]:
    rows = await db.scalars(
        select(NotificationChannel).where(NotificationChannel.tenant_id == tenant_id)
    )
    return {
        int(row.channel_type): (dict(row.preferences or {}) if row.is_enabled else None)
        for row in rows
    }


async def _webhook_targets(db: AsyncSession, tenant_id: UUID, category: int) -> list[UUID]:
    rows = await db.scalars(
        select(Webhook).where(Webhook.tenant_id == tenant_id, Webhook.is_active.is_(True))
    )
    targets = []
    for wh in rows:
        events = wh.events or []
        if not events or category in events:
            targets.append(wh.id)
    return targets


async def persist_and_plan(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    user_id: UUID | None,
    event_id: str,
    event: events_pb2.NotificationEvent,
    channel_override: frozenset[int] | None = None,
) -> PersistResult:
    """Insert the in-app row and its delivery plan.

    ``channel_override`` (price alerts) replaces the category/preference
    matrix with the alert's own channel list. A dedup conflict returns
    ``notification_id=None`` with no deliveries.
    """
    severity = effective_severity(event.category, event.severity)
    rendered = render(event)
    data = {k: v for k, v in _event_data(event).items() if v}

    result = await db.execute(
        pg_insert(Notification)
        .values(
            tenant_id=tenant_id,
            user_id=user_id,
            event_id=event_id,
            category=event.category,
            severity=severity,
            notification_type=spec_for(event.category).notification_type,
            title=rendered.title,
            message=rendered.message,
            data=data or None,
        )
        .on_conflict_do_nothing(index_elements=["event_id"])
        .returning(Notification.id)
    )
    notification_id = result.scalar()
    if notification_id is None:
        return PersistResult(notification_id=None, deliveries=[])

    if channel_override is not None:
        targets: frozenset[int] = channel_override
    else:
        prefs = await _channel_prefs(db, tenant_id)
        targets = channels_for(event.category, severity, prefs)
    pending: list[PendingDelivery] = []

    destinations: list[tuple[int, str]] = []
    if EMAIL in targets:
        pinned = severity in PINNED_SEVERITIES
        addresses = await email_recipients(db, tenant_id, ignore_disabled=pinned)
        destinations += [(EMAIL, addr) for addr in addresses]
    if WEBHOOK in targets:
        destinations += [
            (WEBHOOK, str(wh_id)) for wh_id in await _webhook_targets(db, tenant_id, event.category)
        ]

    for channel, destination in destinations:
        delivery = NotificationDelivery(
            tenant_id=tenant_id,
            notification_id=notification_id,
            channel=channel,
            destination=destination,
        )
        db.add(delivery)
        await db.flush()
        pending.append(
            PendingDelivery(
                delivery_id=delivery.id,
                tenant_id=tenant_id,
                channel=channel,
                destination=destination,
                rendered=rendered,
                category=event.category,
                severity=severity,
            )
        )
    return PersistResult(notification_id=notification_id, deliveries=pending)


def _event_data(event: events_pb2.NotificationEvent) -> dict[str, str]:
    return {
        "execution_id": event.execution_id,
        "strategy_id": event.strategy_id,
        "session_id": event.session_id,
        "account_id": event.account_id,
        "sleeve_id": event.sleeve_id,
        "backtest_id": event.backtest_id,
        "symbol": event.symbol,
        "amount": event.amount,
        "reason": event.reason,
        **dict(event.extra),
    }


def make_notification_handler(
    session_factory: async_sessionmaker[AsyncSession],
    dispatcher: Dispatcher,
    *,
    alert_matcher: AlertMatcher | None = None,
) -> NotificationHandler:
    """The StreamConsumer handler: persist inside a tenant session, then deliver."""

    async def handle(envelope: EventEnvelope) -> None:
        try:
            event = NotificationEvents.payload(envelope)
        except UnknownEventTypeError as e:
            raise PoisonError(str(e)) from e
        if not envelope.tenant_id:
            raise PoisonError("notification envelope without tenant_id")
        tenant_id = UUID(envelope.tenant_id)
        user_id = UUID(envelope.user_id) if envelope.user_id else None

        async with tenant_session(tenant_id, session_factory) as db:
            result = await persist_and_plan(
                db,
                tenant_id=tenant_id,
                user_id=user_id,
                event_id=envelope.id,
                event=event,
            )
            await db.commit()

        if alert_matcher is not None and result.notification_id is not None:
            await alert_matcher.match(tenant_id, event)
        if result.deliveries:
            await dispatcher.dispatch(result.deliveries)

    return handle
