"""Event transport integration tests against real Redis.

Covers both delivery modes (tail fan-out, consumer-group durability) plus the
failure behaviors the messaging substrate exists for: reconnect replay from a
stored cursor, reclaim of a dead consumer's pending entries, and MAXLEN bounds.

Targets ``llamatrade_events.RedisStreamsTransport`` directly — the byte-level
Redis Streams layer the high-level ``EventBus``/catalog sit on top of, and where
these delivery/durability guarantees actually live.
"""

from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest
import redis.asyncio as aioredis

from llamatrade_events import RedisStreamsTransport

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest.fixture
async def transport(redis_url: str):
    transport = RedisStreamsTransport(redis_url, namespace=f"t{uuid4().hex[:8]}")
    yield transport
    await transport.close()


async def _collect(aiter, n: int, timeout: float = 5.0) -> list[tuple[str, bytes]]:
    """Collect n entries from an async iterator with a deadline."""

    async def take() -> list[tuple[str, bytes]]:
        out: list[tuple[str, bytes]] = []
        async for entry in aiter:
            out.append(entry)
            if len(out) >= n:
                break
        return out

    return await asyncio.wait_for(take(), timeout=timeout)


class TestPublishAndTail:
    async def test_tail_fan_out_two_independent_readers(
        self, transport: RedisStreamsTransport
    ) -> None:
        stream = "fanout"
        # Both tails replay from the start — each gets its own full copy
        await transport.publish(stream, b"1")
        await transport.publish(stream, b"2")

        first = await _collect(transport.tail(stream, from_cursor="0", block_ms=200), 2)
        second = await _collect(transport.tail(stream, from_cursor="0", block_ms=200), 2)

        assert [v for _, v in first] == [b"1", b"2"]
        assert [v for _, v in second] == [b"1", b"2"]

    async def test_reconnect_replays_gap_from_cursor(
        self, transport: RedisStreamsTransport
    ) -> None:
        stream = "cursor"
        await transport.publish(stream, b"1")
        ((first_id, _),) = await _collect(transport.tail(stream, from_cursor="0", block_ms=200), 1)

        # "Disconnect"; two entries land while we're away
        await transport.publish(stream, b"2")
        await transport.publish(stream, b"3")

        replayed = await _collect(transport.tail(stream, from_cursor=first_id, block_ms=200), 2)
        assert [v for _, v in replayed] == [b"2", b"3"]

    async def test_maxlen_bounds_stream(
        self, transport: RedisStreamsTransport, redis_url: str
    ) -> None:
        stream = "bounded"
        # Approximate MAXLEN trims at whole-node granularity, so a small batch may
        # not trim at all; publish enough to span several nodes and force it.
        for i in range(500):
            await transport.publish(stream, str(i).encode(), maxlen=10)

        client = aioredis.from_url(redis_url)
        try:
            length = await client.xlen(transport.key(stream))
        finally:
            await client.aclose()

        # Approximate trim keeps the stream bounded well below the 500 published.
        assert length < 200


class TestConsumerGroups:
    async def test_consume_ack_lifecycle(self, transport: RedisStreamsTransport) -> None:
        stream, group = "fills", "portfolio-ledger"
        await transport.ensure_group(stream, group, start_id="0")
        await transport.publish(stream, b"lt-1")
        await transport.publish(stream, b"lt-2")

        entries = await _collect(transport.consume(stream, group, "c1", block_ms=200), 2)
        assert [v for _, v in entries] == [b"lt-1", b"lt-2"]
        assert await transport.pending(stream, group) == 2

        for cursor, _ in entries:
            await transport.ack(stream, group, cursor)
        assert await transport.pending(stream, group) == 0

    async def test_unacked_entries_reclaimed_from_dead_consumer(
        self, transport: RedisStreamsTransport
    ) -> None:
        stream, group = "reclaim", "portfolio-ledger"
        await transport.ensure_group(stream, group, start_id="0")
        await transport.publish(stream, b"lt-dead")

        # Consumer 1 reads but dies before acking
        await _collect(transport.consume(stream, group, "dead-pod", block_ms=200), 1)
        assert await transport.pending(stream, group) == 1

        # Consumer 2 takes over via XAUTOCLAIM (min idle 0 for the test)
        entries = await _collect(
            transport.consume(stream, group, "new-pod", block_ms=200, claim_min_idle_ms=0), 1
        )
        assert entries[0][1] == b"lt-dead"
        await transport.ack(stream, group, entries[0][0])
        assert await transport.pending(stream, group) == 0

    async def test_group_sees_entries_published_after_creation_point(
        self, transport: RedisStreamsTransport
    ) -> None:
        stream, group = "fresh", "portfolio-ledger"
        await transport.publish(stream, b"old")
        await transport.ensure_group(stream, group)  # default start_id: new entries only
        await transport.publish(stream, b"new")

        entries = await _collect(transport.consume(stream, group, "c1", block_ms=200), 1)
        assert entries[0][1] == b"new"

    async def test_ensure_group_is_idempotent(self, transport: RedisStreamsTransport) -> None:
        stream, group = "idem", "g"
        await transport.ensure_group(stream, group)
        await transport.ensure_group(stream, group)  # BUSYGROUP swallowed


class TestNamespacing:
    async def test_keys_are_namespace_prefixed(
        self, transport: RedisStreamsTransport, redis_url: str
    ) -> None:
        await transport.publish("nskey", b"1")
        client = aioredis.from_url(redis_url)
        try:
            assert await client.exists(transport.key("nskey")) == 1
            assert transport.key("nskey").startswith("t")  # test namespace, not "lt"
        finally:
            await client.aclose()
