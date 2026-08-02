"""The typed catalog — the surface services actually call."""

from __future__ import annotations

import pytest
from conftest import FakeTransport

from llamatrade_events.bus import EventBus
from llamatrade_events.catalog import (
    BarEvents,
    FillEvents,
    NotificationEvents,
    OrderEvents,
    PositionEvents,
    ProgressEvents,
)
from llamatrade_events.catalog.orders import event_type_for as order_event_type_for
from llamatrade_events.catalog.positions import event_type_for as position_event_type_for
from llamatrade_events.codec import EventEnvelope
from llamatrade_events.idempotency import InMemoryDedupStore, derive_event_id
from llamatrade_events.transport.base import CURSOR_BEGIN
from llamatrade_proto.generated import backtest_pb2, events_pb2, market_data_pb2, trading_pb2

# --- orders ---


async def test_order_publish_tail_round_trip(bus: EventBus) -> None:
    orders = OrderEvents(bus=bus)
    await orders.publish("s1", trading_pb2.OrderUpdate(event_type="filled"), tenant_id="t1")
    got = [(c, u) async for c, u in orders.tail("s1", from_cursor=CURSOR_BEGIN)]
    assert len(got) == 1
    assert got[0][1].event_type == "filled"


async def test_order_publish_maps_event_type(bus: EventBus, transport: FakeTransport) -> None:
    orders = OrderEvents(bus=bus)
    await orders.publish("s1", trading_pb2.OrderUpdate(event_type="cancelled"))
    stream, value = transport.published[0]
    assert stream == "trading:orders:s1"
    env = EventEnvelope.FromString(value)
    assert env.type == events_pb2.EVENT_TYPE_ORDER_CANCELLED


async def test_order_publish_keys_by_session(bus: EventBus, transport: FakeTransport) -> None:
    orders = OrderEvents(bus=bus)
    await orders.publish("s1", trading_pb2.OrderUpdate(event_type="filled"))
    assert transport.records[0].key == "s1"


def test_order_event_type_mapping() -> None:
    assert order_event_type_for("submitted") == events_pb2.EVENT_TYPE_ORDER_SUBMITTED
    assert order_event_type_for("FILLED") == events_pb2.EVENT_TYPE_ORDER_FILLED
    assert order_event_type_for("partial_fill") == events_pb2.EVENT_TYPE_ORDER_FILLED
    assert order_event_type_for("anything-else") == events_pb2.EVENT_TYPE_ORDER_UPDATED


# --- positions ---


async def test_position_publish_tail_round_trip(bus: EventBus) -> None:
    positions = PositionEvents(bus=bus)
    await positions.publish("s1", trading_pb2.PositionUpdate(event_type="opened"))
    got = [u async for _, u in positions.tail("s1", from_cursor=CURSOR_BEGIN)]
    assert len(got) == 1
    assert got[0].event_type == "opened"


async def test_position_publish_keys_by_session(bus: EventBus, transport: FakeTransport) -> None:
    positions = PositionEvents(bus=bus)
    await positions.publish("s2", trading_pb2.PositionUpdate(event_type="opened"))
    assert transport.records[0].key == "s2"


def test_position_event_type_mapping() -> None:
    assert position_event_type_for("opened") == events_pb2.EVENT_TYPE_POSITION_OPENED
    assert position_event_type_for("closed") == events_pb2.EVENT_TYPE_POSITION_CLOSED
    assert position_event_type_for("?") == events_pb2.EVENT_TYPE_POSITION_UPDATED


# --- progress ---


async def test_progress_replays_from_start(bus: EventBus) -> None:
    progress = ProgressEvents(bus=bus)
    await progress.publish("bt-1", backtest_pb2.BacktestProgressUpdate(progress_percent=10))
    await progress.publish("bt-1", backtest_pb2.BacktestProgressUpdate(progress_percent=50))
    # Default tail cursor is BEGIN → a late joiner sees both.
    got = [u async for _, u in progress.tail("bt-1")]
    assert [u.progress_percent for u in got] == [10, 50]


async def test_progress_publish_keys_by_backtest(bus: EventBus, transport: FakeTransport) -> None:
    progress = ProgressEvents(bus=bus)
    await progress.publish("bt-9", backtest_pb2.BacktestProgressUpdate(progress_percent=10))
    assert transport.records[0].key == "bt-9"


# --- fills (durable) ---


async def test_fill_publish_and_consume(bus: EventBus) -> None:
    fills = FillEvents(bus=bus)
    await fills.publish_fill(
        events_pb2.LedgerFill(client_order_id="o1", tenant_id="t1", symbol="AAPL", side="buy")
    )

    received: list[object] = []

    async def handler(env: EventEnvelope) -> None:
        received.append(FillEvents.payload(env))

    await fills.consumer(consumer_name="p1").run(handler)
    assert len(received) == 1
    assert isinstance(received[0], events_pb2.LedgerFill)
    assert received[0].client_order_id == "o1"


async def test_fill_idempotency_seed_is_client_order_id(
    bus: EventBus, transport: FakeTransport
) -> None:
    fills = FillEvents(bus=bus)
    await fills.publish_fill(events_pb2.LedgerFill(client_order_id="abc"))
    env = EventEnvelope.FromString(transport.published[0][1])
    assert env.id == derive_event_id("abc")


async def test_reservation_seed_includes_event_type(
    bus: EventBus, transport: FakeTransport
) -> None:
    fills = FillEvents(bus=bus)
    await fills.publish_reservation(
        events_pb2.LedgerReservation(client_order_id="abc", event_type="order_submitted")
    )
    env = EventEnvelope.FromString(transport.published[0][1])
    assert env.type == events_pb2.EVENT_TYPE_LEDGER_RESERVATION
    assert env.id == derive_event_id("abc", "order_submitted")


async def test_fill_publish_keys_by_account(bus: EventBus, transport: FakeTransport) -> None:
    fills = FillEvents(bus=bus)
    await fills.publish_fill(events_pb2.LedgerFill(client_order_id="o1", account_id="acct-1"))
    assert transport.records[0].key == "acct-1"


async def test_reservation_publish_keys_by_account(bus: EventBus, transport: FakeTransport) -> None:
    fills = FillEvents(bus=bus)
    await fills.publish_reservation(
        events_pb2.LedgerReservation(
            client_order_id="o1", account_id="acct-2", event_type="order_submitted"
        )
    )
    assert transport.records[0].key == "acct-2"


async def test_fill_consumer_dedup_path(bus: EventBus) -> None:
    fills = FillEvents(bus=bus)
    fill = events_pb2.LedgerFill(client_order_id="dup")
    await fills.publish_fill(fill)
    dedup = InMemoryDedupStore()
    await dedup.mark(derive_event_id("dup"))

    called = 0

    async def handler(_: EventEnvelope) -> None:
        nonlocal called
        called += 1

    await fills.consumer(consumer_name="p1", dedup=dedup).run(handler)
    assert called == 0  # already applied → skipped


# --- bars (raw) ---


async def test_bar_raw_round_trip(bus: EventBus, transport: FakeTransport) -> None:
    bars = BarEvents(bus=bus)
    await bars.publish(market_data_pb2.Bar(symbol="AAPL", volume=100))
    # Raw channel: the stored value is the bare Bar, not an envelope.
    stream, value = transport.published[0]
    assert stream == "market:bars:1m"
    assert market_data_pb2.Bar.FromString(value).symbol == "AAPL"

    got = [b async for _, b in bars.tail(from_cursor=CURSOR_BEGIN)]
    assert len(got) == 1
    assert got[0].symbol == "AAPL"
    assert got[0].volume == 100


async def test_bar_publish_keys_by_symbol(bus: EventBus, transport: FakeTransport) -> None:
    bars = BarEvents(bus=bus)
    await bars.publish(market_data_pb2.Bar(symbol="MSFT", volume=100))
    assert transport.records[0].key == "MSFT"


# --- notifications (durable) ---


async def test_notification_publish_and_consume(bus: EventBus) -> None:
    notifications = NotificationEvents(bus=bus)
    await notifications.publish(
        events_pb2.NotificationEvent(
            category=events_pb2.NOTIFICATION_CATEGORY_SLEEVE_FROZEN,
            severity=events_pb2.NOTIFICATION_SEVERITY_CRITICAL,
            sleeve_id="sl1",
        ),
        tenant_id="t1",
    )

    received: list[object] = []

    async def handler(env: EventEnvelope) -> None:
        received.append(NotificationEvents.payload(env))

    await notifications.consumer(consumer_name="n1").run(handler)
    assert len(received) == 1
    assert isinstance(received[0], events_pb2.NotificationEvent)
    assert received[0].sleeve_id == "sl1"


async def test_notification_publish_keys_by_tenant(bus: EventBus, transport: FakeTransport) -> None:
    notifications = NotificationEvents(bus=bus)
    await notifications.publish(
        events_pb2.NotificationEvent(category=events_pb2.NOTIFICATION_CATEGORY_ORDER_FILLED),
        tenant_id="t42",
    )
    assert transport.records[0].key == "t42"
    stream, value = transport.published[0]
    assert stream == "notifications"
    env = EventEnvelope.FromString(value)
    assert env.type == events_pb2.EVENT_TYPE_NOTIFICATION
    assert env.tenant_id == "t42"


async def test_notification_dedup_seed_extends_with_parts(
    bus: EventBus, transport: FakeTransport
) -> None:
    notifications = NotificationEvents(bus=bus)
    event = events_pb2.NotificationEvent(category=events_pb2.NOTIFICATION_CATEGORY_ORDER_FILLED)
    await notifications.publish(event, tenant_id="t1", dedup_parts=("ord-1",))
    env = EventEnvelope.FromString(transport.published[0][1])
    assert env.id == derive_event_id(
        str(events_pb2.NOTIFICATION_CATEGORY_ORDER_FILLED), "t1", "ord-1"
    )


async def test_notification_redelivery_collapses_to_one_id(
    bus: EventBus, transport: FakeTransport
) -> None:
    notifications = NotificationEvents(bus=bus)
    event = events_pb2.NotificationEvent(category=events_pb2.NOTIFICATION_CATEGORY_PAYMENT_FAILED)
    await notifications.publish(event, tenant_id="t1", dedup_parts=("inv-9",))
    await notifications.publish(event, tenant_id="t1", dedup_parts=("inv-9",))
    ids = {EventEnvelope.FromString(v).id for _, v in transport.published}
    assert len(ids) == 1


async def test_publish_safe_returns_cursor(bus: EventBus) -> None:
    notifications = NotificationEvents(bus=bus)
    cursor = await notifications.publish_safe(
        events_pb2.NotificationEvent(category=events_pb2.NOTIFICATION_CATEGORY_ORDER_FILLED),
        tenant_id="t1",
    )
    assert cursor is not None


async def test_publish_safe_swallows_transport_failure(
    bus: EventBus, monkeypatch: pytest.MonkeyPatch
) -> None:
    notifications = NotificationEvents(bus=bus)

    async def boom(*args: object, **kwargs: object) -> None:
        raise RuntimeError("broker down")

    monkeypatch.setattr(notifications.bus, "publish_envelope", boom)
    cursor = await notifications.publish_safe(
        events_pb2.NotificationEvent(category=events_pb2.NOTIFICATION_CATEGORY_ORDER_FILLED),
        tenant_id="t1",
    )
    assert cursor is None
