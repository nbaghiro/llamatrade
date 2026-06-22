"""EventBus over the FakeTransport (codec + transport wiring)."""

from __future__ import annotations

from conftest import FakeTransport

from llamatrade_events.bus import EventBus
from llamatrade_events.codec import make_envelope
from llamatrade_events.transport.base import CURSOR_BEGIN
from llamatrade_proto.generated import events_pb2, trading_pb2

ORDER_FILLED = events_pb2.EVENT_TYPE_ORDER_FILLED


async def test_publish_and_tail_envelopes(bus: EventBus, transport: FakeTransport) -> None:
    env = make_envelope(ORDER_FILLED, trading_pb2.OrderUpdate(event_type="filled"), tenant_id="t1")
    cursor = await bus.publish_envelope("trading:orders:s1", env, maxlen=10)
    assert cursor == "1"

    got = [e async for e in bus.tail_envelopes("trading:orders:s1", from_cursor=CURSOR_BEGIN)]
    assert len(got) == 1
    _, back = got[0]
    assert back.tenant_id == "t1"
    assert back.type == ORDER_FILLED


async def test_tail_new_cursor_skips_existing(bus: EventBus) -> None:
    env = make_envelope(ORDER_FILLED, trading_pb2.OrderUpdate())
    await bus.publish_envelope("trading:orders:s1", env, maxlen=10)
    # CURSOR_NEW ("$") = only entries after now → nothing already stored.
    got = [e async for e in bus.tail_envelopes("trading:orders:s1")]
    assert got == []


async def test_publish_and_tail_raw(bus: EventBus) -> None:
    await bus.publish_raw("market:bars:1m", b"\x01\x02", maxlen=10)
    got = [v async for _, v in bus.tail_raw("market:bars:1m", from_cursor=CURSOR_BEGIN)]
    assert got == [b"\x01\x02"]


async def test_consume_ack_and_pending(bus: EventBus) -> None:
    env = make_envelope(
        events_pb2.EVENT_TYPE_LEDGER_FILL, events_pb2.LedgerFill(client_order_id="o1")
    )
    await bus.publish_envelope("ledger:fills", env, maxlen=10)

    seen = []
    # group_start=BEGIN: a fresh group replays the entry published before it.
    async for cursor, e in bus.consume_envelopes(
        "ledger:fills", "g1", "c1", group_start_id=CURSOR_BEGIN
    ):
        seen.append(e)
        assert await bus.pending("ledger:fills", "g1") == 1  # delivered, unacked
        await bus.ack("ledger:fills", "g1", cursor)
    assert len(seen) == 1
    assert await bus.pending("ledger:fills", "g1") == 0


async def test_consume_raw_yields_undecodable_bytes(bus: EventBus) -> None:
    """consume_raw must NOT decode — it hands back the raw bytes so the caller
    can guard the decode (corrupt entries go to a DLQ instead of crashing)."""
    garbage = b"\xff\x00 not an envelope"
    await bus.publish_raw("ledger:fills", garbage, maxlen=10)

    out = []
    async for cursor, raw in bus.consume_raw(
        "ledger:fills", "g1", "c1", group_start_id=CURSOR_BEGIN
    ):
        out.append(raw)
        await bus.ack("ledger:fills", "g1", cursor)
    assert out == [garbage]


async def test_consume_raw_new_group_skips_preexisting(bus: EventBus) -> None:
    """Default group_start (CURSOR_NEW) means a fresh group ignores entries that
    predate it."""
    await bus.publish_raw("ledger:fills", b"early", maxlen=10)
    out = [raw async for _, raw in bus.consume_raw("ledger:fills", "g1", "c1")]
    assert out == []


async def test_close_delegates_to_transport(bus: EventBus, transport: FakeTransport) -> None:
    await bus.close()
    assert transport.closed is True


def test_default_transport_is_redis() -> None:
    from llamatrade_events.transport.redis_streams import RedisStreamsTransport

    assert isinstance(EventBus().transport, RedisStreamsTransport)
