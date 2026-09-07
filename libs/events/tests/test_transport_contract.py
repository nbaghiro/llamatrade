"""Transport contract suite — the semantics every ``EventTransport`` backend must
give the layers above (bus, consumer runtime, DLQ replay).

Parametrized over the shipped :class:`FakeTransport` (runs unconditionally) and
:class:`KafkaTransport` against a real broker (integration marker). What both
backends guarantee, pinned here:

- publish → consume → ack: a delivered entry counts as lag until acked;
- per-key ordering: records sharing a key are consumed in publish order;
- an acked entry is never delivered to the group again;
- an entry delivered but never acked reaches a **later** consume of the same
  group (Kafka: the uncommitted offset after the member leaves; fake: pending
  replay) — and nothing more: no redelivery to the live member, which is why
  the retry policies retry in place;
- pause/resume of an entry's partition does not disturb consumption;
- ``length`` counts retained entries; ``purge`` clears them; a cursor-bounded
  purge removes entries at or below the cursor only.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from uuid import uuid4

import pytest
from conftest import FakeTransport, aclose, take

from llamatrade_events.transport.base import CURSOR_BEGIN, EventTransport
from llamatrade_events.transport.kafka import KafkaTransport

STREAM = "ledger:fills"
GROUP = "contract"


@pytest.fixture(
    params=[
        pytest.param("fake", id="fake"),
        pytest.param("kafka", marks=pytest.mark.integration, id="kafka"),
    ]
)
async def transport(request: pytest.FixtureRequest) -> AsyncIterator[EventTransport]:
    """One instance per backend; Kafka runs on a per-test topic namespace."""
    if request.param == "fake":
        yield FakeTransport()
        return
    bootstrap: str = request.getfixturevalue("bootstrap")
    kafka = KafkaTransport(bootstrap, namespace=f"contract{uuid4().hex[:12]}")
    try:
        yield kafka
    finally:
        await kafka.close()


async def test_publish_consume_ack_lifecycle(transport: EventTransport) -> None:
    await transport.ensure_group(STREAM, GROUP)
    await transport.publish(STREAM, b"f1", key="acctA")
    entries = transport.consume(STREAM, GROUP, "c1", group_start_id=CURSOR_BEGIN)

    async def consume_one() -> None:
        async for cursor, value in entries:
            assert value == b"f1"
            assert await transport.pending(STREAM, GROUP) == 1  # delivered, unacked
            await transport.ack(STREAM, GROUP, cursor)
            return

    try:
        await asyncio.wait_for(consume_one(), timeout=30.0)
    finally:
        await aclose(entries)
    assert await transport.pending(STREAM, GROUP) == 0  # committed past the entry


async def test_per_key_order_preserved(transport: EventTransport) -> None:
    await transport.ensure_group(STREAM, GROUP)
    await transport.publish(STREAM, b"a1", key="acctA")
    await transport.publish(STREAM, b"b1", key="acctB")
    await transport.publish(STREAM, b"a2", key="acctA")
    got = await take(transport.consume(STREAM, GROUP, "c1", group_start_id=CURSOR_BEGIN), 3)
    vals = [v for _, v in got]
    assert vals.index(b"a1") < vals.index(b"a2")  # same key → publish order


async def test_acked_entry_is_not_delivered_again(transport: EventTransport) -> None:
    """After an ack, a later consume of the same group sees only newer records."""
    await transport.ensure_group(STREAM, GROUP)
    await transport.publish(STREAM, b"a", key="k")
    entries = transport.consume(STREAM, GROUP, "c1", group_start_id=CURSOR_BEGIN)

    async def consume_and_ack() -> None:
        async for cursor, value in entries:
            assert value == b"a"
            await transport.ack(STREAM, GROUP, cursor)
            return

    try:
        await asyncio.wait_for(consume_and_ack(), timeout=30.0)
    finally:
        await aclose(entries)

    await transport.publish(STREAM, b"b", key="k")
    got = await take(transport.consume(STREAM, GROUP, "c2", group_start_id=CURSOR_BEGIN), 1)
    assert [v for _, v in got] == [b"b"]


async def test_unacked_entry_redelivers_to_a_later_consume(transport: EventTransport) -> None:
    """An entry delivered but never acked is not lost: it reaches a later consume
    of the same group. This crash-redelivery guarantee is all the retry policies
    lean on the transport for — retries within a delivery happen in place."""
    await transport.ensure_group(STREAM, GROUP)
    await transport.publish(STREAM, b"a", key="k")
    first = await take(transport.consume(STREAM, GROUP, "c1", group_start_id=CURSOR_BEGIN), 1)
    assert [v for _, v in first] == [b"a"]  # delivered, never acked

    again = await take(transport.consume(STREAM, GROUP, "c2", group_start_id=CURSOR_BEGIN), 1)
    assert [v for _, v in again] == [b"a"]  # redelivered after the member left


async def test_pause_resume_roundtrip_does_not_disturb_consumption(
    transport: EventTransport,
) -> None:
    """The in-place retry loop pauses the entry's partition and resumes it after;
    consumption then continues with the next record."""
    await transport.ensure_group(STREAM, GROUP)
    await transport.publish(STREAM, b"f1", key="acctA")
    await transport.publish(STREAM, b"f2", key="acctA")
    seen: list[bytes] = []
    entries = transport.consume(STREAM, GROUP, "c1", group_start_id=CURSOR_BEGIN)

    async def consume_two() -> None:
        async for cursor, value in entries:
            seen.append(value)
            if len(seen) == 1:
                await transport.pause_partition(STREAM, GROUP, cursor)
                await transport.resume_partition(STREAM, GROUP, cursor)
            await transport.ack(STREAM, GROUP, cursor)
            if len(seen) == 2:
                return

    try:
        await asyncio.wait_for(consume_two(), timeout=30.0)
    finally:
        await aclose(entries)
    assert seen == [b"f1", b"f2"]


async def test_length_counts_retained_entries(transport: EventTransport) -> None:
    await transport.ensure_group(STREAM, GROUP)
    assert await transport.length(STREAM) == 0
    for i in range(3):
        await transport.publish(STREAM, f"f{i}".encode(), key="acctA")
    assert await transport.length(STREAM) == 3


async def test_length_of_a_stream_never_published_is_zero(transport: EventTransport) -> None:
    assert await transport.length(STREAM + ":dlq") == 0


async def test_purge_clears_the_stream(transport: EventTransport) -> None:
    await transport.ensure_group(STREAM, GROUP)
    for i in range(3):
        await transport.publish(STREAM, f"f{i}".encode(), key="acctA")
    await transport.purge(STREAM)
    assert await transport.length(STREAM) == 0


async def test_purge_up_to_cursor_leaves_records_at_later_cursors(
    transport: EventTransport,
) -> None:
    """A bounded drain (a DLQ replay) clears exactly what it read; records
    re-parked at later cursors during the run survive."""
    await transport.ensure_group(STREAM, GROUP)
    for i in range(5):
        await transport.publish(STREAM, f"f{i}".encode(), key="acctA")
    drained = await take(transport.tail(STREAM, from_cursor=CURSOR_BEGIN), 3)
    assert [v for _, v in drained] == [b"f0", b"f1", b"f2"]

    await transport.purge(STREAM, up_to_cursor=drained[-1][0])

    assert await transport.length(STREAM) == 2
    rest = await take(transport.tail(STREAM, from_cursor=CURSOR_BEGIN), 2)
    assert [v for _, v in rest] == [b"f3", b"f4"]
