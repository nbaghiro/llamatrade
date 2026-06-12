"""EventBus integration tests against real Redis.

Covers both delivery modes (tail fan-out, consumer-group durability) plus the
failure behaviors the migration exists for: reconnect replay from a stored
cursor, reclaim of a dead consumer's pending entries, and MAXLEN bounds.
"""

from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest

from llamatrade_common.eventbus import EventBus

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest.fixture
async def bus(redis_url: str):
    bus = EventBus(redis_url, namespace=f"t{uuid4().hex[:8]}")
    yield bus
    await bus.close()


async def _collect(aiter, n: int, timeout: float = 5.0) -> list[tuple[str, dict[str, str]]]:
    """Collect n entries from an async iterator with a deadline."""

    async def take() -> list[tuple[str, dict[str, str]]]:
        out: list[tuple[str, dict[str, str]]] = []
        async for entry in aiter:
            out.append(entry)
            if len(out) >= n:
                break
        return out

    return await asyncio.wait_for(take(), timeout=timeout)


class TestPublishAndTail:
    async def test_tail_fan_out_two_independent_readers(self, bus: EventBus) -> None:
        stream = "fanout"
        # Both tails replay from the start — each gets its own full copy
        await bus.publish(stream, {"seq": "1"})
        await bus.publish(stream, {"seq": "2"})

        first = await _collect(bus.tail(stream, last_id="0", block_ms=200), 2)
        second = await _collect(bus.tail(stream, last_id="0", block_ms=200), 2)

        assert [f["seq"] for _, f in first] == ["1", "2"]
        assert [f["seq"] for _, f in second] == ["1", "2"]

    async def test_reconnect_replays_gap_from_cursor(self, bus: EventBus) -> None:
        stream = "cursor"
        await bus.publish(stream, {"seq": "1"})
        ((first_id, _),) = await _collect(bus.tail(stream, last_id="0", block_ms=200), 1)

        # "Disconnect"; two entries land while we're away
        await bus.publish(stream, {"seq": "2"})
        await bus.publish(stream, {"seq": "3"})

        replayed = await _collect(bus.tail(stream, last_id=first_id, block_ms=200), 2)
        assert [f["seq"] for _, f in replayed] == ["2", "3"]

    async def test_maxlen_bounds_stream(self, bus: EventBus) -> None:
        stream = "bounded"
        for i in range(50):
            # Exact trim (approximate=False) to assert a hard bound
            await bus.publish(stream, {"seq": str(i)}, maxlen=10, approximate=False)
        entries = await _collect(bus.tail(stream, last_id="0", block_ms=200), 10)
        assert len(entries) == 10
        assert entries[-1][1]["seq"] == "49"


class TestConsumerGroups:
    async def test_consume_ack_lifecycle(self, bus: EventBus) -> None:
        stream, group = "fills", "portfolio-ledger"
        await bus.ensure_group(stream, group, start_id="0")
        await bus.publish(stream, {"client_order_id": "lt-1"})
        await bus.publish(stream, {"client_order_id": "lt-2"})

        entries = await _collect(bus.consume(stream, group, "c1", block_ms=200), 2)
        assert [f["client_order_id"] for _, f in entries] == ["lt-1", "lt-2"]
        assert await bus.pending_count(stream, group) == 2

        for entry_id, _ in entries:
            await bus.ack(stream, group, entry_id)
        assert await bus.pending_count(stream, group) == 0

    async def test_unacked_entries_reclaimed_from_dead_consumer(self, bus: EventBus) -> None:
        stream, group = "reclaim", "portfolio-ledger"
        await bus.ensure_group(stream, group, start_id="0")
        await bus.publish(stream, {"client_order_id": "lt-dead"})

        # Consumer 1 reads but dies before acking
        await _collect(bus.consume(stream, group, "dead-pod", block_ms=200), 1)
        assert await bus.pending_count(stream, group) == 1

        # Consumer 2 takes over via XAUTOCLAIM (min idle 0 for the test)
        entries = await _collect(
            bus.consume(stream, group, "new-pod", block_ms=200, claim_min_idle_ms=0), 1
        )
        assert entries[0][1]["client_order_id"] == "lt-dead"
        await bus.ack(stream, group, entries[0][0])
        assert await bus.pending_count(stream, group) == 0

    async def test_group_sees_entries_published_after_creation_point(self, bus: EventBus) -> None:
        stream, group = "fresh", "portfolio-ledger"
        await bus.publish(stream, {"seq": "old"})
        await bus.ensure_group(stream, group)  # start_id="$": new entries only
        await bus.publish(stream, {"seq": "new"})

        entries = await _collect(bus.consume(stream, group, "c1", block_ms=200), 1)
        assert entries[0][1]["seq"] == "new"

    async def test_ensure_group_is_idempotent(self, bus: EventBus) -> None:
        stream, group = "idem", "g"
        await bus.ensure_group(stream, group)
        await bus.ensure_group(stream, group)  # BUSYGROUP swallowed


class TestNamespacing:
    async def test_keys_are_namespace_prefixed(self, bus: EventBus, redis_url: str) -> None:
        import redis.asyncio as aioredis

        await bus.publish("nskey", {"x": "1"})
        client = aioredis.from_url(redis_url)
        try:
            assert await client.exists(bus.key("nskey")) == 1
            assert bus.key("nskey").startswith("t")  # test namespace, not "lt"
        finally:
            await client.aclose()
