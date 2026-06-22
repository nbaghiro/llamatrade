"""Real-Redis integration tests for ``RedisStreamsTransport`` and the runtime.

These run the actual Redis Streams commands (XADD/XREAD/XREADGROUP/XAUTOCLAIM/
XACK/XPENDING/XTRIM/XGROUP) against a throwaway container — the in-memory
``FakeRedis`` suite proves the transport's branching, this proves the commands
behave as we assume against a real server.

Gated behind ``@pytest.mark.integration`` (deselect with ``-m 'not integration'``)
and self-skips when Docker / testcontainers is unavailable, so the default unit
run stays green without a daemon.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Iterator

import pytest

from llamatrade_events.bus import EventBus
from llamatrade_events.codec import EventEnvelope, make_envelope, parse_payload
from llamatrade_events.consumer import StreamConsumer
from llamatrade_events.idempotency import derive_event_id
from llamatrade_events.transport.base import CURSOR_BEGIN
from llamatrade_events.transport.redis_streams import RedisStreamsTransport
from llamatrade_proto.generated import events_pb2

# Skip the whole module cleanly if testcontainers isn't installed.
RedisContainer = pytest.importorskip("testcontainers.redis").RedisContainer

pytestmark = pytest.mark.integration

STREAM = "ledger:fills"
GROUP = "portfolio-ledger"


@pytest.fixture(scope="module")
def redis_url() -> Iterator[str]:
    """A throwaway Redis container; skip the module if Docker isn't available."""
    try:
        container = RedisContainer(image="redis:7-alpine")
        container.start()
    except Exception as exc:  # Docker daemon down / image pull failed
        pytest.skip(f"Docker/Redis unavailable: {exc}")
    try:
        host = container.get_container_host_ip()
        port = container.get_exposed_port(6379)
        yield f"redis://{host}:{port}/0"
    finally:
        container.stop()


@pytest.fixture
async def transport(
    redis_url: str, request: pytest.FixtureRequest
) -> AsyncIterator[RedisStreamsTransport]:
    """A transport on a per-test namespace so streams/groups never collide."""
    namespace = f"itest-{abs(hash(request.node.nodeid)) % 1_000_000}"
    t = RedisStreamsTransport(redis_url, namespace=namespace)
    try:
        yield t
    finally:
        await t.close()


async def _take[T](agen: AsyncIterator[T], n: int, *, timeout: float = 15.0) -> list[T]:
    """Pull exactly ``n`` items from an infinite generator under a timeout."""

    async def pull() -> list[T]:
        out: list[T] = []
        async for item in agen:
            out.append(item)
            if len(out) >= n:
                break
        return out

    try:
        return await asyncio.wait_for(pull(), timeout=timeout)
    finally:
        await agen.aclose()


def _fill_env(client_order_id: str) -> EventEnvelope:
    fill = events_pb2.LedgerFill(client_order_id=client_order_id, tenant_id="t1")
    return make_envelope(
        events_pb2.EVENT_TYPE_LEDGER_FILL, fill, event_id=derive_event_id(client_order_id)
    )


# -- publish / tail --


async def test_publish_and_tail_round_trip(transport: RedisStreamsTransport) -> None:
    await transport.publish("s", b"a", maxlen=100)
    await transport.publish("s", b"b", maxlen=100)
    got = await _take(transport.tail("s", from_cursor=CURSOR_BEGIN), 2)
    assert [v for _, v in got] == [b"a", b"b"]


async def test_publish_maxlen_trims_on_real_redis(transport: RedisStreamsTransport) -> None:
    for i in range(10):
        await transport.publish("s", str(i).encode(), maxlen=3)
    # approximate trimming may keep a few extra, but never the full 10.
    got = await _take(transport.tail("s", from_cursor=CURSOR_BEGIN), 1)
    assert got  # something survived
    # the earliest entries are gone — "0" must not be the first surviving value
    all_vals = [v async for _, v in transport.tail("s", from_cursor=CURSOR_BEGIN)]
    assert b"9" in all_vals
    assert len(all_vals) < 10


# -- consumer group: consume / ack / pending --


async def test_consume_ack_and_pending(transport: RedisStreamsTransport) -> None:
    await transport.ensure_group(STREAM, GROUP, start_id=CURSOR_BEGIN)
    await transport.publish(STREAM, b"f1", maxlen=100)
    got = await _take(transport.consume(STREAM, GROUP, "c1"), 1)
    cursor, value = got[0]
    assert value == b"f1"
    assert await transport.pending(STREAM, GROUP) == 1  # delivered, unacked
    await transport.ack(STREAM, GROUP, cursor)
    assert await transport.pending(STREAM, GROUP) == 0


async def test_group_start_begin_replays_preexisting(transport: RedisStreamsTransport) -> None:
    # Publish BEFORE the group exists; a fresh group at BEGIN still replays it.
    await transport.publish(STREAM, b"early", maxlen=100)
    got = await _take(transport.consume(STREAM, GROUP, "c1", group_start_id=CURSOR_BEGIN), 1)
    assert got[0][1] == b"early"


async def test_xautoclaim_reclaims_from_dead_consumer(transport: RedisStreamsTransport) -> None:
    await transport.ensure_group("s", "g", start_id=CURSOR_BEGIN)
    await transport.publish("s", b"x", maxlen=100)
    # c1 reads but never acks → entry stays pending, owned by c1.
    await _take(transport.consume("s", "g", "c1"), 1)
    assert await transport.pending("s", "g") == 1
    # c2 reclaims it immediately (min idle 0) via XAUTOCLAIM.
    got = await _take(transport.consume("s", "g", "c2", claim_min_idle_ms=0), 1)
    assert got[0][1] == b"x"


async def test_consume_recovers_after_group_destroyed(transport: RedisStreamsTransport) -> None:
    """If the group is destroyed out-of-band (XGROUP DESTROY), the consumer
    recreates it on the next NOGROUP and keeps going."""
    await transport.ensure_group("s", "g", start_id=CURSOR_BEGIN)
    await transport.publish("s", b"one", maxlen=100)
    got = await _take(transport.consume("s", "g", "c1"), 1)
    assert got[0][1] == b"one"

    # Destroy the group behind the transport's back, then publish a new entry.
    client = await transport._client()
    await client.xgroup_destroy(transport.key("s"), "g")
    await transport.publish("s", b"two", maxlen=100)

    # consume() must recreate the group (group_start=BEGIN replays) and deliver.
    got = await _take(
        transport.consume("s", "g", "c1", group_start_id=CURSOR_BEGIN, block_ms=200), 1
    )
    assert got[0][1] in (b"one", b"two")  # recreated group drains the backlog


# -- StreamConsumer runtime end-to-end --


async def test_stream_consumer_handles_and_acks(redis_url: str) -> None:
    bus = EventBus(RedisStreamsTransport(redis_url, namespace="itest-sc"))
    try:
        await bus.publish_envelope(STREAM, _fill_env("o1"), maxlen=100)
        consumer = StreamConsumer(bus, STREAM, GROUP, consumer_name="c1")

        done = asyncio.Event()
        received: list[str] = []

        async def handler(env: EventEnvelope) -> None:
            received.append(parse_payload(env).client_order_id)
            done.set()

        task = asyncio.create_task(consumer.run(handler))
        try:
            await asyncio.wait_for(done.wait(), timeout=15.0)
        finally:
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task

        assert received == ["o1"]
        assert await bus.pending(STREAM, GROUP) == 0  # acked
    finally:
        await bus.close()


async def test_stream_consumer_dead_letters_undecodable(redis_url: str) -> None:
    bus = EventBus(RedisStreamsTransport(redis_url, namespace="itest-dlq"))
    try:
        await bus.publish_raw(STREAM, b"\xff not an envelope", maxlen=100)
        consumer = StreamConsumer(bus, STREAM, GROUP, consumer_name="c1")

        async def handler(_: EventEnvelope) -> None:
            return None

        task = asyncio.create_task(consumer.run(handler))
        try:
            # Poll until the poison entry has been acked off the live stream.
            for _ in range(100):
                if await bus.pending(STREAM, GROUP) == 0 and await _dlq_len(bus) == 1:
                    break
                await asyncio.sleep(0.05)
        finally:
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task

        assert await _dlq_len(bus) == 1  # the raw bytes were dead-lettered
        assert await bus.pending(STREAM, GROUP) == 0
    finally:
        await bus.close()


async def _dlq_len(bus: EventBus) -> int:
    return len([v async for _, v in bus.tail_raw(STREAM + ":dlq", from_cursor=CURSOR_BEGIN)])
