"""Notification events — any service → notification (durable consumer group).

One global stream (``notifications``) partitioned by ``tenant_id``: each
tenant's notifications stay ordered while delivery runs parallel across
tenants. Producers publish fire-and-forget (never raised into the calling
path); the notification service persists the in-app row before committing the
offset, so the envelope's deterministic id is the platform-wide dedup key.

Producer: every service via :meth:`NotificationEvents.publish`. Consumer: the
notification service's delivery pipeline, via a :class:`StreamConsumer`.
"""

from __future__ import annotations

import asyncio
import logging
from typing import cast

from llamatrade_events.bus import EventBus
from llamatrade_events.channels import NOTIFICATIONS
from llamatrade_events.codec import EventEnvelope, make_envelope, parse_payload, register_payload
from llamatrade_events.consumer import StreamConsumer
from llamatrade_events.idempotency import DedupStore, derive_event_id
from llamatrade_events.transport.base import CURSOR_BEGIN, Cursor
from llamatrade_events.transport.factory import get_default_transport
from llamatrade_proto.generated import events_pb2

logger = logging.getLogger(__name__)

NotificationEvent = events_pb2.NotificationEvent

register_payload(events_pb2.EVENT_TYPE_NOTIFICATION, NotificationEvent)

# The notification service's durable consumer group.
NOTIFICATION_GROUP = "notification-delivery"

# publish_safe ceiling: a producer must not stall on a dead broker.
PUBLISH_SAFE_TIMEOUT_SECONDS = 5.0


class NotificationEvents:
    """Durable any-service→notification stream (produce + consumer factory)."""

    def __init__(self, *, bus: EventBus | None = None) -> None:
        self._bus = bus or EventBus(get_default_transport())
        self._stream = NOTIFICATIONS.key()

    @property
    def bus(self) -> EventBus:
        return self._bus

    async def publish(
        self,
        event: NotificationEvent,
        *,
        tenant_id: str,
        user_id: str = "",
        event_id: str | None = None,
        dedup_parts: tuple[str, ...] = (),
    ) -> Cursor:
        """Publish one notification event, keyed and deduplicated per tenant.

        ``dedup_parts`` extends the deterministic id seed beyond
        ``(category, tenant)`` for flows that recur per entity or episode
        (e.g. ``(client_order_id,)`` or ``(sleeve_id, reason)``).
        """
        env = make_envelope(
            events_pb2.EVENT_TYPE_NOTIFICATION,
            event,
            event_id=event_id or derive_event_id(str(event.category), tenant_id, *dedup_parts),
            tenant_id=tenant_id,
            user_id=user_id,
        )
        return await self._bus.publish_envelope(self._stream, env, key=tenant_id)

    async def publish_safe(
        self,
        event: NotificationEvent,
        *,
        tenant_id: str,
        user_id: str = "",
        event_id: str | None = None,
        dedup_parts: tuple[str, ...] = (),
    ) -> Cursor | None:
        """Fire-and-forget publish: never raises into the producing path.

        The money-path posture (see Eventing): a notification publish must not
        block or fail an order, a fill fold, or a webhook handler. Returns the
        cursor on success, ``None`` on failure (logged).
        """
        try:
            return await asyncio.wait_for(
                self.publish(
                    event,
                    tenant_id=tenant_id,
                    user_id=user_id,
                    event_id=event_id,
                    dedup_parts=dedup_parts,
                ),
                timeout=PUBLISH_SAFE_TIMEOUT_SECONDS,
            )
        except Exception:
            logger.warning(
                "notification publish failed (category=%s tenant=%s); dropping",
                event.category,
                tenant_id,
                exc_info=True,
            )
            return None

    def consumer(
        self,
        *,
        consumer_name: str,
        group: str = NOTIFICATION_GROUP,
        dedup: DedupStore | None = None,
        group_start: str = CURSOR_BEGIN,
    ) -> StreamConsumer:
        """A durable consumer for the notification stream.

        Defaults to ``group_start=CURSOR_BEGIN`` (a fresh group replays the
        retained stream — safe given the persist-side event-id dedupe).
        """
        return StreamConsumer(
            self._bus,
            self._stream,
            group,
            consumer_name=consumer_name,
            dedup=dedup,
            group_start=group_start,
        )

    @staticmethod
    def payload(envelope: EventEnvelope) -> NotificationEvent:
        """Parse a consumed envelope into its notification event."""
        return cast("NotificationEvent", parse_payload(envelope))

    async def close(self) -> None:
        await self._bus.close()


_shared: NotificationEvents | None = None


def shared_notification_events() -> NotificationEvents:
    """Process-wide publisher singleton (one producer connection per process)."""
    global _shared
    if _shared is None:
        _shared = NotificationEvents()
    return _shared
