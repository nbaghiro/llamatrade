"""Pipeline integration over real Postgres: persist, dedup, plan, deliver.

The bus is the in-memory FakeTransport; the DB is real, so the ON CONFLICT
dedup, the tenant GUC, and the delivery-row lifecycle are exercised as they
run in production.
"""

from __future__ import annotations

from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from llamatrade_db import tenant_session
from llamatrade_db.models.auth import Tenant, User
from llamatrade_db.models.notification import (
    Notification,
    NotificationChannel,
    NotificationDelivery,
    Webhook,
)
from llamatrade_events import EventBus
from llamatrade_events.catalog.notifications import NotificationEvents
from llamatrade_events.testing import FakeTransport
from llamatrade_proto.generated import events_pb2, notification_pb2

from src.channels.email import EmailChannel
from src.channels.webhook import WebhookChannel
from src.delivery import DeliveryDispatcher
from src.pipeline import make_notification_handler, persist_and_plan

pytestmark = pytest.mark.integration

TENANT_ID = UUID("11111111-1111-1111-1111-111111111111")
_E = events_pb2


class StubEmail(EmailChannel):
    def __init__(self, *, ok: bool = True) -> None:
        super().__init__()
        self.sent: list[tuple[str, str, str]] = []
        self.html_bodies: list[str | None] = []
        self._ok = ok

    async def send(self, to: str, subject: str, body: str, html_body: str | None = None) -> bool:
        self.sent.append((to, subject, body))
        self.html_bodies.append(html_body)
        return self._ok


async def _seed_tenant(session_factory: async_sessionmaker) -> None:
    async with session_factory() as db:
        db.add(Tenant(id=TENANT_ID, name="t", slug="t"))
        db.add(
            User(
                tenant_id=TENANT_ID,
                email="owner@test",
                password_hash="x",
                is_active=True,
            )
        )
        await db.commit()


def _event(category: int = _E.NOTIFICATION_CATEGORY_SLEEVE_FROZEN) -> events_pb2.NotificationEvent:
    return events_pb2.NotificationEvent(category=category, sleeve_id="sl1", reason="qty mismatch")


async def test_persist_creates_row_and_email_plan(session_factory: async_sessionmaker) -> None:
    await _seed_tenant(session_factory)
    async with tenant_session(TENANT_ID, session_factory) as db:
        result = await persist_and_plan(
            db, tenant_id=TENANT_ID, user_id=None, event_id="ev-1", event=_event()
        )
        await db.commit()

    pending = result.deliveries
    assert [p.channel for p in pending] == [notification_pb2.CHANNEL_TYPE_EMAIL]
    assert pending[0].destination == "owner@test"
    async with tenant_session(TENANT_ID, session_factory) as db:
        row = await db.scalar(select(Notification))
        assert row is not None
        assert row.event_id == "ev-1"
        assert row.category == _E.NOTIFICATION_CATEGORY_SLEEVE_FROZEN
        assert row.severity == _E.NOTIFICATION_SEVERITY_CRITICAL
        assert row.title == "Sleeve frozen"
        assert row.data is not None and row.data["reason"] == "qty mismatch"


async def test_duplicate_event_id_is_noop(session_factory: async_sessionmaker) -> None:
    await _seed_tenant(session_factory)
    async with tenant_session(TENANT_ID, session_factory) as db:
        first = await persist_and_plan(
            db, tenant_id=TENANT_ID, user_id=None, event_id="ev-dup", event=_event()
        )
        second = await persist_and_plan(
            db, tenant_id=TENANT_ID, user_id=None, event_id="ev-dup", event=_event()
        )
        await db.commit()
    assert first.notification_id is not None and first.deliveries
    assert second.notification_id is None and second.deliveries == []


async def test_webhook_target_matches_category_filter(
    session_factory: async_sessionmaker,
) -> None:
    await _seed_tenant(session_factory)
    async with session_factory() as db:
        db.add(
            Webhook(
                tenant_id=TENANT_ID,
                name="all",
                url="https://example.test/all",
                events=[],
                created_by=uuid4(),
            )
        )
        db.add(
            Webhook(
                tenant_id=TENANT_ID,
                name="orders-only",
                url="https://example.test/orders",
                events=[int(_E.NOTIFICATION_CATEGORY_ORDER_FILLED)],
                created_by=uuid4(),
            )
        )
        await db.commit()

    async with tenant_session(TENANT_ID, session_factory) as db:
        result = await persist_and_plan(
            db, tenant_id=TENANT_ID, user_id=None, event_id="ev-wh", event=_event()
        )
        await db.commit()
    webhook_targets = [
        p for p in result.deliveries if p.channel == notification_pb2.CHANNEL_TYPE_WEBHOOK
    ]
    assert len(webhook_targets) == 1  # the empty-filter endpoint only


async def test_consumer_round_trip_delivers_and_marks(
    session_factory: async_sessionmaker,
) -> None:
    await _seed_tenant(session_factory)
    captured: list[httpx.Request] = []

    def hook_handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200)

    async with session_factory() as db:
        db.add(
            Webhook(
                tenant_id=TENANT_ID,
                name="w",
                url="https://example.test/hook",
                secret="k",
                events=[],
                created_by=uuid4(),
            )
        )
        await db.commit()

    email = StubEmail()
    dispatcher = DeliveryDispatcher(
        session_factory,
        email=email,
        webhook=WebhookChannel(transport=httpx.MockTransport(hook_handler)),
    )
    events = NotificationEvents(bus=EventBus(FakeTransport()))
    await events.publish(_event(), tenant_id=str(TENANT_ID), dedup_parts=("rt",))

    handler = make_notification_handler(session_factory, dispatcher)
    await events.consumer(consumer_name="t1").run(handler)

    assert len(captured) == 1
    assert email.sent and email.sent[0][0] == "owner@test"
    # Email goes out multipart: the styled HTML part rides along.
    assert email.html_bodies[0] is not None
    assert "<html" in email.html_bodies[0]
    assert "__" not in email.html_bodies[0]
    async with tenant_session(TENANT_ID, session_factory) as db:
        deliveries = list(await db.scalars(select(NotificationDelivery)))
        assert len(deliveries) == 2
        assert all(
            d.status == notification_pb2.NOTIFICATION_STATUS_SENT and d.attempts == 1
            for d in deliveries
        )


async def test_redelivery_does_not_double_deliver(
    session_factory: async_sessionmaker,
) -> None:
    await _seed_tenant(session_factory)
    email = StubEmail()
    dispatcher = DeliveryDispatcher(session_factory, email=email)
    events = NotificationEvents(bus=EventBus(FakeTransport()))
    event = _event(_E.NOTIFICATION_CATEGORY_PAYMENT_FAILED)
    await events.publish(event, tenant_id=str(TENANT_ID), dedup_parts=("inv",))
    await events.publish(event, tenant_id=str(TENANT_ID), dedup_parts=("inv",))

    handler = make_notification_handler(session_factory, dispatcher)
    await events.consumer(consumer_name="t1").run(handler)

    async with tenant_session(TENANT_ID, session_factory) as db:
        rows = list(await db.scalars(select(Notification)))
    assert len(rows) == 1
    assert len(email.sent) == 1


async def test_failed_webhook_disables_and_notifies(
    session_factory: async_sessionmaker,
) -> None:
    await _seed_tenant(session_factory)

    def failing(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    async with session_factory() as db:
        db.add(
            Webhook(
                tenant_id=TENANT_ID,
                name="dead",
                url="https://example.test/dead",
                events=[],
                created_by=uuid4(),
            )
        )
        await db.commit()

    email = StubEmail()
    dispatcher = DeliveryDispatcher(
        session_factory,
        email=email,
        webhook=WebhookChannel(transport=httpx.MockTransport(failing)),
        disable_threshold=2,
    )
    events = NotificationEvents(bus=EventBus(FakeTransport()))
    handler = make_notification_handler(session_factory, dispatcher)
    for n in range(2):
        await events.publish(
            _event(_E.NOTIFICATION_CATEGORY_ORDER_REJECTED),
            tenant_id=str(TENANT_ID),
            dedup_parts=(f"o{n}",),
        )
    await events.consumer(consumer_name="t1").run(handler)

    async with tenant_session(TENANT_ID, session_factory) as db:
        webhook = await db.scalar(select(Webhook))
        assert webhook is not None
        assert webhook.is_active is False
        assert webhook.failure_count == 2
        disabled_notice = await db.scalar(
            select(Notification).where(
                Notification.category == _E.NOTIFICATION_CATEGORY_WEBHOOK_DISABLED
            )
        )
        assert disabled_notice is not None
    # The disable notice itself went out by email.
    assert any("Webhook disabled" in subject for _, subject, _ in email.sent)


async def test_disabled_email_channel_suppresses_info(
    session_factory: async_sessionmaker,
) -> None:
    await _seed_tenant(session_factory)
    async with session_factory() as db:
        db.add(
            NotificationChannel(
                tenant_id=TENANT_ID,
                user_id=uuid4(),
                channel_type=notification_pb2.CHANNEL_TYPE_EMAIL,
                destination="",
                is_enabled=False,
            )
        )
        await db.commit()

    async with tenant_session(TENANT_ID, session_factory) as db:
        result = await persist_and_plan(
            db,
            tenant_id=TENANT_ID,
            user_id=None,
            event_id="ev-pref",
            event=_event(_E.NOTIFICATION_CATEGORY_PAYMENT_SUCCEEDED),
        )
        await db.commit()
    assert result.notification_id is not None
    assert result.deliveries == []


async def test_critical_overrides_disabled_email(
    session_factory: async_sessionmaker,
) -> None:
    await _seed_tenant(session_factory)
    async with session_factory() as db:
        db.add(
            NotificationChannel(
                tenant_id=TENANT_ID,
                user_id=uuid4(),
                channel_type=notification_pb2.CHANNEL_TYPE_EMAIL,
                destination="",
                is_enabled=False,
            )
        )
        await db.commit()

    async with tenant_session(TENANT_ID, session_factory) as db:
        result = await persist_and_plan(
            db,
            tenant_id=TENANT_ID,
            user_id=None,
            event_id="ev-crit",
            event=_event(),
        )
        await db.commit()
    assert [p.channel for p in result.deliveries] == [notification_pb2.CHANNEL_TYPE_EMAIL]


async def test_invite_without_tenant_is_emailed_directly_and_not_persisted(
    session_factory: async_sessionmaker,
) -> None:
    email = StubEmail()
    dispatcher = DeliveryDispatcher(session_factory, email=email)
    events = NotificationEvents(bus=EventBus(FakeTransport()))
    invite = events_pb2.NotificationEvent(
        category=_E.NOTIFICATION_CATEGORY_INVITE,
        extra={
            "to": "invitee@example.com",
            "code": "ABCD-EFGH",
            "link": "http://localhost:8800/register?code=ABCD-EFGH",
        },
    )
    await events.publish(invite, tenant_id="", dedup_parts=("ABCDEFGH",))

    await events.consumer(consumer_name="t1").run(
        make_notification_handler(session_factory, dispatcher)
    )

    assert [sent[0] for sent in email.sent] == ["invitee@example.com"]
    assert "ABCD-EFGH" in email.sent[0][2]
    assert email.html_bodies[0] is not None and "__" not in email.html_bodies[0]
    async with session_factory() as db:
        assert list(await db.scalars(select(Notification))) == []


@pytest.mark.parametrize(
    "event",
    [
        events_pb2.NotificationEvent(category=_E.NOTIFICATION_CATEGORY_INVITE),
        events_pb2.NotificationEvent(
            category=_E.NOTIFICATION_CATEGORY_ORDER_FILLED, extra={"to": "x@example.com"}
        ),
    ],
)
async def test_tenantless_event_without_recipient_or_direct_category_is_poison(
    session_factory: async_sessionmaker, event: events_pb2.NotificationEvent
) -> None:
    from llamatrade_events import PoisonError, make_envelope

    email = StubEmail()
    handler = make_notification_handler(
        session_factory, DeliveryDispatcher(session_factory, email=email)
    )
    envelope = make_envelope(events_pb2.EVENT_TYPE_NOTIFICATION, event, tenant_id="")

    with pytest.raises(PoisonError):
        await handler(envelope)
    assert email.sent == []


async def test_failed_direct_email_does_not_raise_into_the_consumer(
    session_factory: async_sessionmaker,
) -> None:
    from llamatrade_events import make_envelope

    email = StubEmail(ok=False)
    handler = make_notification_handler(
        session_factory, DeliveryDispatcher(session_factory, email=email)
    )
    event = events_pb2.NotificationEvent(
        category=_E.NOTIFICATION_CATEGORY_INVITE, extra={"to": "invitee@example.com"}
    )

    await handler(make_envelope(events_pb2.EVENT_TYPE_NOTIFICATION, event, tenant_id=""))

    assert len(email.sent) == 1
