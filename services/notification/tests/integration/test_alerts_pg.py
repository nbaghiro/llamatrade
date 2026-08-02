"""Price-alert engine over real Postgres: trigger, dedup, matcher, CRUD, leadership."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from llamatrade_db import tenant_session
from llamatrade_db.models.auth import Tenant, User
from llamatrade_db.models.notification import Alert, Notification
from llamatrade_proto.generated import common_pb2, events_pb2, notification_pb2

from src.alerts.engine import trigger_alert
from src.alerts.market_loop import (
    MARKET_LOOP_LOCK_KEY,
    active_market_alerts,
    release_leadership,
    try_acquire_leadership,
)
from src.alerts.matcher import EventAlertMatcher
from src.grpc.servicer import NotificationServicer
from src.pipeline import Dispatcher, PendingDelivery

pytestmark = pytest.mark.integration

TENANT_ID = UUID("31111111-1111-1111-1111-111111111111")
USER_ID = UUID("32222222-2222-2222-2222-222222222222")
_C = notification_pb2
_E = events_pb2


class RecordingDispatcher(Dispatcher):
    def __init__(self) -> None:
        self.dispatched: list[PendingDelivery] = []

    async def dispatch(self, pending: list[PendingDelivery]) -> None:
        self.dispatched.extend(pending)


async def _seed(session_factory: async_sessionmaker) -> None:
    async with session_factory() as db:
        db.add(Tenant(id=TENANT_ID, name="t", slug="t3"))
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


async def _make_alert(
    session_factory: async_sessionmaker,
    *,
    condition_type: int = _C.ALERT_CONDITION_TYPE_PRICE_ABOVE,
    symbol: str | None = "SPY",
    cooldown_minutes: int = 60,
    channels: list[int] | None = None,
    condition: dict[str, str] | None = None,
) -> UUID:
    alert_id = uuid4()
    async with session_factory() as db:
        db.add(
            Alert(
                id=alert_id,
                tenant_id=TENANT_ID,
                name="watch",
                alert_type=condition_type,
                symbol=symbol,
                condition=condition or {"threshold": "500"},
                channels=channels or [],
                cooldown_minutes=cooldown_minutes,
                created_by=USER_ID,
            )
        )
        await db.commit()
    return alert_id


async def test_trigger_persists_and_counts(session_factory: async_sessionmaker) -> None:
    await _seed(session_factory)
    alert_id = await _make_alert(session_factory)
    dispatcher = RecordingDispatcher()

    fired = await trigger_alert(
        session_factory,
        dispatcher,
        alert_id=alert_id,
        tenant_id=TENANT_ID,
        reason="price 501.00 above 500.00",
        bucket="bar:SPY:100",
    )
    assert fired
    async with tenant_session(TENANT_ID, session_factory) as db:
        alert = await db.get(Alert, alert_id)
        assert alert is not None
        assert alert.trigger_count == 1
        assert alert.last_triggered_at is not None
        row = await db.scalar(select(Notification))
        assert row is not None
        assert row.category == _E.NOTIFICATION_CATEGORY_PRICE_ALERT_TRIGGERED
        assert "watch" in row.message
        assert row.user_id == USER_ID


async def test_same_bucket_fires_once(session_factory: async_sessionmaker) -> None:
    await _seed(session_factory)
    alert_id = await _make_alert(session_factory, cooldown_minutes=0)
    dispatcher = RecordingDispatcher()

    first = await trigger_alert(
        session_factory,
        dispatcher,
        alert_id=alert_id,
        tenant_id=TENANT_ID,
        reason="r",
        bucket="bar:SPY:100",
    )
    second = await trigger_alert(
        session_factory,
        dispatcher,
        alert_id=alert_id,
        tenant_id=TENANT_ID,
        reason="r",
        bucket="bar:SPY:100",
    )
    assert first and not second
    async with tenant_session(TENANT_ID, session_factory) as db:
        alert = await db.get(Alert, alert_id)
        assert alert is not None and alert.trigger_count == 1


async def test_cooldown_blocks_next_bucket(session_factory: async_sessionmaker) -> None:
    await _seed(session_factory)
    alert_id = await _make_alert(session_factory, cooldown_minutes=60)
    dispatcher = RecordingDispatcher()

    assert await trigger_alert(
        session_factory,
        dispatcher,
        alert_id=alert_id,
        tenant_id=TENANT_ID,
        reason="r",
        bucket="bar:SPY:100",
    )
    assert not await trigger_alert(
        session_factory,
        dispatcher,
        alert_id=alert_id,
        tenant_id=TENANT_ID,
        reason="r",
        bucket="bar:SPY:101",
    )


async def test_alert_channels_override_delivery_plan(
    session_factory: async_sessionmaker,
) -> None:
    await _seed(session_factory)
    alert_id = await _make_alert(session_factory, channels=[int(_C.CHANNEL_TYPE_EMAIL)])
    dispatcher = RecordingDispatcher()
    await trigger_alert(
        session_factory,
        dispatcher,
        alert_id=alert_id,
        tenant_id=TENANT_ID,
        reason="r",
        bucket="b1",
    )
    assert [d.channel for d in dispatcher.dispatched] == [_C.CHANNEL_TYPE_EMAIL]
    assert dispatcher.dispatched[0].destination == "owner@test"


async def test_event_matcher_fires_order_filled_alert(
    session_factory: async_sessionmaker,
) -> None:
    await _seed(session_factory)
    await _make_alert(
        session_factory, condition_type=_C.ALERT_CONDITION_TYPE_ORDER_FILLED, symbol="SPY"
    )
    other = await _make_alert(
        session_factory, condition_type=_C.ALERT_CONDITION_TYPE_ORDER_FILLED, symbol="QQQ"
    )
    dispatcher = RecordingDispatcher()
    matcher = EventAlertMatcher(session_factory, dispatcher)
    await matcher.match(
        TENANT_ID,
        events_pb2.NotificationEvent(
            category=_E.NOTIFICATION_CATEGORY_ORDER_FILLED, symbol="SPY", reason="filled"
        ),
    )
    async with tenant_session(TENANT_ID, session_factory) as db:
        rows = list(
            await db.scalars(
                select(Notification).where(
                    Notification.category == _E.NOTIFICATION_CATEGORY_PRICE_ALERT_TRIGGERED
                )
            )
        )
        assert len(rows) == 1
        other_alert = await db.get(Alert, other)
        assert other_alert is not None and other_alert.trigger_count == 0


async def test_active_market_alerts_sweep(session_factory: async_sessionmaker) -> None:
    await _seed(session_factory)
    await _make_alert(session_factory, symbol="SPY")
    await _make_alert(
        session_factory, condition_type=_C.ALERT_CONDITION_TYPE_ORDER_FILLED, symbol="TLT"
    )
    watched = await active_market_alerts(session_factory)
    assert set(watched) == {"SPY"}
    assert watched["SPY"][0][1] == TENANT_ID


async def test_leadership_is_exclusive(postgres_url: str) -> None:
    engine_a = create_async_engine(postgres_url)
    engine_b = create_async_engine(postgres_url)
    try:
        leader = await try_acquire_leadership(engine_a)
        assert leader is not None
        follower = await try_acquire_leadership(engine_b)
        assert follower is None
        await release_leadership(leader)
        promoted = await try_acquire_leadership(engine_b)
        assert promoted is not None
        await release_leadership(promoted)
    finally:
        await engine_a.dispose()
        await engine_b.dispose()
    assert MARKET_LOOP_LOCK_KEY == 0x6E6F7469


async def test_alert_crud_cycle(session_factory: async_sessionmaker) -> None:
    await _seed(session_factory)
    servicer = NotificationServicer(session_maker=session_factory)
    ctx = common_pb2.TenantContext(tenant_id=str(TENANT_ID), user_id=str(USER_ID))

    created = await servicer.create_alert(
        notification_pb2.CreateAlertRequest(
            context=ctx,
            name="RSI watch",
            description="overbought",
            condition=notification_pb2.AlertCondition(
                type=_C.ALERT_CONDITION_TYPE_RSI_ABOVE,
                symbol="SPY",
                threshold=common_pb2.Decimal(value="70"),
            ),
            channels=[_C.CHANNEL_TYPE_EMAIL],
            cooldown_minutes=30,
        ),
        object(),
    )
    assert created.alert.is_active
    assert created.alert.condition.threshold.value == "70"
    assert created.alert.description == "overbought"

    listed = await servicer.list_alerts(
        notification_pb2.ListAlertsRequest(context=ctx, active_only=True), object()
    )
    assert len(listed.alerts) == 1

    toggled = await servicer.toggle_alert(
        notification_pb2.ToggleAlertRequest(
            context=ctx, alert_id=created.alert.id, is_active=False
        ),
        object(),
    )
    assert not toggled.alert.is_active
    listed = await servicer.list_alerts(
        notification_pb2.ListAlertsRequest(context=ctx, active_only=True), object()
    )
    assert listed.alerts == []

    deleted = await servicer.delete_alert(
        notification_pb2.DeleteAlertRequest(context=ctx, alert_id=created.alert.id), object()
    )
    assert deleted.success


async def test_expired_alert_never_fires(session_factory: async_sessionmaker) -> None:
    await _seed(session_factory)
    alert_id = await _make_alert(session_factory)
    async with session_factory() as db:
        alert = await db.get(Alert, alert_id)
        assert alert is not None
        alert.expires_at = datetime.now(UTC) - timedelta(days=1)
        await db.commit()
    dispatcher = RecordingDispatcher()
    fired = await trigger_alert(
        session_factory,
        dispatcher,
        alert_id=alert_id,
        tenant_id=TENANT_ID,
        reason="r",
        bucket="b",
    )
    assert not fired
