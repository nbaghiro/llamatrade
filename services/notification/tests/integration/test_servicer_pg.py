"""Servicer integration over real Postgres: RPC surface end to end."""

from __future__ import annotations

from uuid import UUID, uuid4

import httpx
import pytest
from connectrpc.code import Code
from connectrpc.errors import ConnectError
from sqlalchemy.ext.asyncio import async_sessionmaker

from llamatrade_db import tenant_session
from llamatrade_db.models.auth import Tenant, User
from llamatrade_proto.generated import common_pb2, events_pb2, notification_pb2

from src.channels.webhook import WebhookChannel
from src.grpc.servicer import NotificationServicer
from src.pipeline import persist_and_plan

pytestmark = pytest.mark.integration

TENANT_ID = UUID("21111111-1111-1111-1111-111111111111")
USER_ID = UUID("22222222-2222-2222-2222-222222222222")
_E = events_pb2


class MockRequestContext:
    pass


def _ctx() -> common_pb2.TenantContext:
    return common_pb2.TenantContext(tenant_id=str(TENANT_ID), user_id=str(USER_ID))


async def _seed(session_factory: async_sessionmaker, notifications: int = 0) -> None:
    async with session_factory() as db:
        db.add(Tenant(id=TENANT_ID, name="t", slug="t2"))
        db.add(
            User(
                id=USER_ID,
                tenant_id=TENANT_ID,
                email="owner@test",
                password_hash="x",
                is_active=True,
            )
        )
        await db.commit()
    if notifications:
        async with tenant_session(TENANT_ID, session_factory) as db:
            for n in range(notifications):
                await persist_and_plan(
                    db,
                    tenant_id=TENANT_ID,
                    user_id=USER_ID if n % 2 == 0 else None,
                    event_id=f"seed-{n}",
                    event=events_pb2.NotificationEvent(
                        category=_E.NOTIFICATION_CATEGORY_SESSION_STARTED
                    ),
                )
            await db.commit()


async def test_list_and_mark_read_round_trip(session_factory: async_sessionmaker) -> None:
    await _seed(session_factory, notifications=3)
    servicer = NotificationServicer(session_maker=session_factory)

    listed = await servicer.list_notifications(
        notification_pb2.ListNotificationsRequest(context=_ctx()), MockRequestContext()
    )
    assert listed.unread_count == 3
    assert len(listed.notifications) == 3
    assert listed.notifications[0].title == "Trading session started"

    first_id = listed.notifications[0].id
    marked = await servicer.mark_as_read(
        notification_pb2.MarkAsReadRequest(context=_ctx(), notification_id=first_id),
        MockRequestContext(),
    )
    assert marked.marked_count == 1

    unread = await servicer.list_notifications(
        notification_pb2.ListNotificationsRequest(context=_ctx(), unread_only=True),
        MockRequestContext(),
    )
    assert unread.unread_count == 2
    assert all(not n.is_read for n in unread.notifications)

    marked_all = await servicer.mark_as_read(
        notification_pb2.MarkAsReadRequest(context=_ctx(), mark_all=True),
        MockRequestContext(),
    )
    assert marked_all.marked_count == 2


async def test_pagination(session_factory: async_sessionmaker) -> None:
    await _seed(session_factory, notifications=5)
    servicer = NotificationServicer(session_maker=session_factory)
    page2 = await servicer.list_notifications(
        notification_pb2.ListNotificationsRequest(
            context=_ctx(),
            pagination=common_pb2.PaginationRequest(page=2, page_size=2),
        ),
        MockRequestContext(),
    )
    assert len(page2.notifications) == 2
    assert page2.pagination.total_items == 5
    assert page2.pagination.total_pages == 3
    assert page2.pagination.has_next
    assert page2.pagination.has_previous


async def test_webhook_crud_cycle(session_factory: async_sessionmaker) -> None:
    await _seed(session_factory)
    servicer = NotificationServicer(session_maker=session_factory)

    created = await servicer.create_webhook(
        notification_pb2.CreateWebhookRequest(
            context=_ctx(),
            name="ops",
            url="https://example.test/hook",
            events=[_E.NOTIFICATION_CATEGORY_SLEEVE_FROZEN],
        ),
        MockRequestContext(),
    )
    assert created.secret
    assert created.webhook.is_active
    assert list(created.webhook.events) == [_E.NOTIFICATION_CATEGORY_SLEEVE_FROZEN]

    listed = await servicer.list_webhooks(
        notification_pb2.ListWebhooksRequest(context=_ctx()), MockRequestContext()
    )
    assert len(listed.webhooks) == 1

    updated = await servicer.update_webhook(
        notification_pb2.UpdateWebhookRequest(
            context=_ctx(),
            webhook_id=created.webhook.id,
            name="ops2",
            url="https://example.test/hook2",
            events=[],
            is_active=False,
        ),
        MockRequestContext(),
    )
    assert updated.webhook.name == "ops2"
    assert not updated.webhook.is_active

    deleted = await servicer.delete_webhook(
        notification_pb2.DeleteWebhookRequest(context=_ctx(), webhook_id=created.webhook.id),
        MockRequestContext(),
    )
    assert deleted.success
    listed = await servicer.list_webhooks(
        notification_pb2.ListWebhooksRequest(context=_ctx()), MockRequestContext()
    )
    assert listed.webhooks == []


async def test_create_webhook_rejects_bad_url(session_factory: async_sessionmaker) -> None:
    await _seed(session_factory)
    servicer = NotificationServicer(session_maker=session_factory)
    with pytest.raises(ConnectError) as exc:
        await servicer.create_webhook(
            notification_pb2.CreateWebhookRequest(
                context=_ctx(), name="bad", url="ftp://example.test"
            ),
            MockRequestContext(),
        )
    assert exc.value.code == Code.INVALID_ARGUMENT


async def test_update_missing_webhook_not_found(session_factory: async_sessionmaker) -> None:
    await _seed(session_factory)
    servicer = NotificationServicer(session_maker=session_factory)
    with pytest.raises(ConnectError) as exc:
        await servicer.update_webhook(
            notification_pb2.UpdateWebhookRequest(
                context=_ctx(),
                webhook_id=str(uuid4()),
                name="x",
                url="https://example.test",
                is_active=True,
            ),
            MockRequestContext(),
        )
    assert exc.value.code == Code.NOT_FOUND


async def test_test_webhook_delivers_signed_test(session_factory: async_sessionmaker) -> None:
    await _seed(session_factory)
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(204)

    servicer = NotificationServicer(
        session_maker=session_factory,
        webhook=WebhookChannel(transport=httpx.MockTransport(handler)),
    )
    created = await servicer.create_webhook(
        notification_pb2.CreateWebhookRequest(
            context=_ctx(), name="t", url="https://example.test/hook"
        ),
        MockRequestContext(),
    )
    result = await servicer.test_webhook(
        notification_pb2.TestWebhookRequest(context=_ctx(), webhook_id=created.webhook.id),
        MockRequestContext(),
    )
    assert result.success
    assert result.status_code == 204
    assert captured and "X-Webhook-Signature" in captured[0].headers


async def test_preferences_round_trip(session_factory: async_sessionmaker) -> None:
    await _seed(session_factory)
    servicer = NotificationServicer(session_maker=session_factory)

    initial = await servicer.get_preferences(
        notification_pb2.GetPreferencesRequest(context=_ctx()), MockRequestContext()
    )
    assert {p.channel for p in initial.preferences} == {
        notification_pb2.CHANNEL_TYPE_EMAIL,
        notification_pb2.CHANNEL_TYPE_WEBHOOK,
    }
    assert all(p.enabled for p in initial.preferences)

    updated = await servicer.update_preferences(
        notification_pb2.UpdatePreferencesRequest(
            context=_ctx(),
            preferences=[
                notification_pb2.ChannelPreference(
                    channel=notification_pb2.CHANNEL_TYPE_EMAIL,
                    enabled=True,
                    categories=[_E.NOTIFICATION_CATEGORY_PAYMENT_FAILED],
                )
            ],
        ),
        MockRequestContext(),
    )
    email_pref = next(
        p for p in updated.preferences if p.channel == notification_pb2.CHANNEL_TYPE_EMAIL
    )
    assert list(email_pref.categories) == [_E.NOTIFICATION_CATEGORY_PAYMENT_FAILED]

    fetched = await servicer.get_preferences(
        notification_pb2.GetPreferencesRequest(context=_ctx()), MockRequestContext()
    )
    email_pref = next(
        p for p in fetched.preferences if p.channel == notification_pb2.CHANNEL_TYPE_EMAIL
    )
    assert list(email_pref.categories) == [_E.NOTIFICATION_CATEGORY_PAYMENT_FAILED]


async def test_tenant_isolation_on_lists(session_factory: async_sessionmaker) -> None:
    await _seed(session_factory, notifications=2)
    other_tenant = uuid4()
    async with session_factory() as db:
        db.add(Tenant(id=other_tenant, name="o", slug="other"))
        await db.commit()
    servicer = NotificationServicer(session_maker=session_factory)
    other_ctx = common_pb2.TenantContext(tenant_id=str(other_tenant), user_id=str(uuid4()))
    listed = await servicer.list_notifications(
        notification_pb2.ListNotificationsRequest(context=other_ctx), MockRequestContext()
    )
    assert listed.notifications == []
    assert listed.unread_count == 0
