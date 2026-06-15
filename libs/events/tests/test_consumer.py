"""StreamConsumer runtime: happy path, dedupe, and dead-letter."""

from __future__ import annotations

from conftest import FakeTransport

from llamatrade_events.bus import EventBus
from llamatrade_events.codec import EventEnvelope, make_envelope, parse_payload
from llamatrade_events.consumer import StreamConsumer
from llamatrade_events.idempotency import InMemoryDedupStore, derive_event_id
from llamatrade_proto.generated import events_pb2

STREAM = "ledger:fills"
GROUP = "portfolio-ledger"

# Importing llamatrade_events above ran the package __init__, which imports the
# catalog and registers LedgerFill for EVENT_TYPE_LEDGER_FILL.


def _fill_env(client_order_id: str) -> EventEnvelope:
    fill = events_pb2.LedgerFill(client_order_id=client_order_id, tenant_id="t1")
    return make_envelope(
        events_pb2.EVENT_TYPE_LEDGER_FILL, fill, event_id=derive_event_id(client_order_id)
    )


async def test_happy_path_handles_and_acks(bus: EventBus, transport: FakeTransport) -> None:
    await bus.publish_envelope(STREAM, _fill_env("o1"), maxlen=100)
    consumer = StreamConsumer(bus, STREAM, GROUP, consumer_name="c1")

    received: list[str] = []

    async def handler(env: EventEnvelope) -> None:
        received.append(parse_payload(env).client_order_id)

    await consumer.run(handler)
    assert received == ["o1"]
    assert await bus.pending(STREAM, GROUP) == 0  # acked


async def test_dedup_skips_already_applied(bus: EventBus) -> None:
    env = _fill_env("dup")
    await bus.publish_envelope(STREAM, env, maxlen=100)
    dedup = InMemoryDedupStore()
    await dedup.mark(env.id)  # pretend it was already applied
    consumer = StreamConsumer(bus, STREAM, GROUP, consumer_name="c1", dedup=dedup)

    called = 0

    async def handler(_: EventEnvelope) -> None:
        nonlocal called
        called += 1

    await consumer.run(handler)
    assert called == 0  # handler skipped
    assert await bus.pending(STREAM, GROUP) == 0  # but still acked


async def test_dedup_marks_after_success(bus: EventBus) -> None:
    env = _fill_env("once")
    await bus.publish_envelope(STREAM, env, maxlen=100)
    dedup = InMemoryDedupStore()
    consumer = StreamConsumer(bus, STREAM, GROUP, consumer_name="c1", dedup=dedup)

    async def handler(_: EventEnvelope) -> None:
        return None

    await consumer.run(handler)
    assert await dedup.seen(env.id) is True


async def test_poison_message_goes_to_dlq(bus: EventBus, transport: FakeTransport) -> None:
    await bus.publish_envelope(STREAM, _fill_env("bad"), maxlen=100)
    consumer = StreamConsumer(bus, STREAM, GROUP, consumer_name="c1", max_attempts=3)

    attempts = 0

    async def boom(_: EventEnvelope) -> None:
        nonlocal attempts
        attempts += 1
        raise RuntimeError("nope")

    # Each run() redelivers the unacked entry (FakeTransport mimics XAUTOCLAIM).
    for _ in range(3):
        await consumer.run(boom)

    assert attempts == 3
    assert len(transport.entries(STREAM + ":dlq")) == 1  # dead-lettered
    assert await bus.pending(STREAM, GROUP) == 0  # acked off the live stream


async def test_stop_event_halts_loop(bus: EventBus) -> None:
    import asyncio

    await bus.publish_envelope(STREAM, _fill_env("x"), maxlen=100)
    consumer = StreamConsumer(bus, STREAM, GROUP, consumer_name="c1")
    stop = asyncio.Event()
    stop.set()

    called = 0

    async def handler(_: EventEnvelope) -> None:
        nonlocal called
        called += 1

    await consumer.run(handler, stop_event=stop)
    assert called == 0  # stopped before handling
