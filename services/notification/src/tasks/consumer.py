"""The durable notification consumer: StreamConsumer over ``notifications``.

``StreamConsumer`` supplies dedupe, in-place retry (5 attempts), DLQ produce,
and the lag gauge; the handler (src/pipeline.py) persists before the ack and
hands committed deliveries to the dispatcher. One consumer group across all
pods; Kafka assigns each tenant's partition to one member.
"""

from __future__ import annotations

import asyncio
import os

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from llamatrade_events import NOTIFICATIONS, DlqDepthSampler
from llamatrade_events.catalog.notifications import NotificationEvents

from src.alerts.matcher import EventAlertMatcher
from src.delivery import DeliveryDispatcher
from src.pipeline import AlertMatcher, make_notification_handler

# Mirrors StreamConsumer's default dlq_suffix for the notifications stream.
NOTIFICATIONS_DLQ_STREAM = NOTIFICATIONS.key() + ":dlq"


async def run_notification_consumer(
    events: NotificationEvents,
    session_factory: async_sessionmaker[AsyncSession],
    *,
    stop_event: asyncio.Event,
    alert_matcher: AlertMatcher | None = None,
) -> None:
    dispatcher = DeliveryDispatcher(session_factory)
    handler = make_notification_handler(
        session_factory,
        dispatcher,
        alert_matcher=alert_matcher or EventAlertMatcher(session_factory, dispatcher),
    )
    consumer = events.consumer(consumer_name=os.getenv("HOSTNAME", "notification-0"))
    await consumer.run(handler, stop_event=stop_event)


async def run_dlq_sampler(events: NotificationEvents, *, stop_event: asyncio.Event) -> None:
    """Sample the notifications dead-letter depth into the events DLQ gauge."""
    await DlqDepthSampler(events.bus, [NOTIFICATIONS_DLQ_STREAM]).run(stop_event=stop_event)
