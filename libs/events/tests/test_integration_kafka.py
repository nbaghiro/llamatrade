"""Real-Kafka integration tests for ``KafkaTransport`` and the runtime.

These run actual producer/consumer/commit calls against a throwaway broker — the
in-memory fake suite (``test_kafka.py``) proves the adapter's branching, this proves
the calls behave as we assume against a real Kafka.

Gated behind ``@pytest.mark.integration`` and self-skips when Docker / testcontainers
is unavailable, so the default unit run stays green without a daemon.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator, Iterator
from uuid import uuid4

import pytest
from aiokafka import AIOKafkaConsumer
from aiokafka.admin import AIOKafkaAdminClient, NewTopic

from llamatrade_events.bus import EventBus
from llamatrade_events.codec import EventEnvelope, decode_envelope, make_envelope, parse_payload
from llamatrade_events.consumer import PoisonError, StreamConsumer
from llamatrade_events.idempotency import derive_event_id
from llamatrade_events.transport.base import CURSOR_BEGIN, OutgoingRecord
from llamatrade_events.transport.kafka import KafkaTransport
from llamatrade_proto.generated import events_pb2

pytestmark = pytest.mark.integration

STREAM = "ledger:fills"
GROUP = "portfolio-ledger"


@pytest.fixture(scope="module")
def bootstrap() -> Iterator[str]:
    """A Kafka broker for the module.

    Prefers a broker provided via ``KAFKA_BOOTSTRAP_SERVERS`` (the CI service
    container); otherwise spins a throwaway ``KafkaContainer`` via testcontainers,
    skipping the module when neither is available.
    """
    provided = os.getenv("KAFKA_BOOTSTRAP_SERVERS")
    if provided:
        yield provided
        return
    kafka_mod = pytest.importorskip("testcontainers.kafka")
    try:
        container = kafka_mod.KafkaContainer()
        container.start()
    except Exception as exc:  # Docker daemon down / image pull failed
        pytest.skip(f"Docker/Kafka unavailable: {exc}")
    try:
        yield container.get_bootstrap_server()
    finally:
        container.stop()


@pytest.fixture
async def transport(
    bootstrap: str, request: pytest.FixtureRequest
) -> AsyncIterator[KafkaTransport]:
    """A transport on a per-test namespace so topics never collide across tests."""
    namespace = f"itest{abs(hash(request.node.nodeid)) % 1_000_000}"
    t = KafkaTransport(bootstrap, namespace=namespace)
    try:
        yield t
    finally:
        await t.close()


async def _take[T](agen: AsyncIterator[T], n: int, *, timeout: float = 30.0) -> list[T]:
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


# -- publish / consume / ack / pending --


async def test_consume_ack_and_pending(transport: KafkaTransport) -> None:
    await transport.ensure_group(STREAM, GROUP)
    await transport.publish(STREAM, b"f1", key="acctA")
    entries = transport.consume(STREAM, GROUP, "c1", group_start_id=CURSOR_BEGIN)
    # Kafka commits are consumer-scoped: ack while the consumer that yielded the
    # entry is still live, before the generator (and its member) is closed.
    async for cursor, value in entries:
        assert value == b"f1"
        assert await transport.pending(STREAM, GROUP) == 1  # delivered, not committed
        await transport.ack(STREAM, GROUP, cursor)
        break
    await entries.aclose()
    # committed offset advanced → no lag
    assert await transport.pending(STREAM, GROUP) == 0


async def test_per_account_order_preserved(transport: KafkaTransport) -> None:
    await transport.ensure_group(STREAM, GROUP)
    # Interleave two accounts; same-key records keep publish order in their partition.
    await transport.publish(STREAM, b"a1", key="acctA")
    await transport.publish(STREAM, b"b1", key="acctB")
    await transport.publish(STREAM, b"a2", key="acctA")
    got = await _take(transport.consume(STREAM, GROUP, "c1", group_start_id=CURSOR_BEGIN), 3)
    vals = [v for _, v in got]
    assert vals.index(b"a1") < vals.index(b"a2")  # per-account FIFO


async def test_publish_many_delivers_the_whole_batch_in_per_key_order(
    transport: KafkaTransport,
) -> None:
    """A single ``publish_many`` on a real broker lands every record and keeps
    per-key order (same key → one partition → FIFO)."""
    await transport.ensure_group(STREAM, GROUP)
    records = [OutgoingRecord(f"m{i}".encode(), key="acctA") for i in range(10)]
    cursors = await transport.publish_many(STREAM, records)
    assert len(cursors) == len(records)  # one cursor per record

    got = await _take(transport.consume(STREAM, GROUP, "c1", group_start_id=CURSOR_BEGIN), 10)
    assert [v for _, v in got] == [f"m{i}".encode() for i in range(10)]


async def test_publish_many_keeps_per_key_order_across_partitions(
    transport: KafkaTransport, bootstrap: str
) -> None:
    """On a multi-partition topic, records batched through ``publish_many`` stick
    to one partition per key (the structural basis for per-key order) and each
    key's records are consumed in publish order."""
    await _create_topic(bootstrap, transport.topic(STREAM), partitions=4)
    keys = ("acctA", "acctB")
    batch = [OutgoingRecord(f"{k}:{i}".encode(), key=k) for i in range(4) for k in keys]

    cursors = await transport.publish_many(STREAM, batch)
    assert len(cursors) == len(batch)

    partition_of: dict[str | None, int] = {}
    for record, cursor in zip(batch, cursors, strict=True):
        partition_of.setdefault(record.key, _partition_of(cursor))
        assert _partition_of(cursor) == partition_of[record.key]  # sticky per key

    got = await _take(
        transport.consume(STREAM, GROUP, "c1", group_start_id=CURSOR_BEGIN), len(batch)
    )
    for key in keys:
        seq = [v.decode() for _, v in got if v.decode().startswith(f"{key}:")]
        assert seq == [f"{key}:{i}" for i in range(4)]  # per-key publish order holds


async def test_length_and_purge_report_and_clear_the_topic(transport: KafkaTransport) -> None:
    """Portfolio's DLQ replay gates on ``length`` and clears with ``purge``.

    Both read the topic's partitions, which an unsubscribed consumer's cached
    cluster never learns — so they are answered from the Admin API.
    """
    await transport.ensure_group(STREAM, GROUP)
    assert await transport.length(STREAM) == 0
    for i in range(3):
        await transport.publish(STREAM, f"f{i}".encode(), key="acctA")

    assert await transport.length(STREAM) == 3
    await transport.purge(STREAM)
    assert await transport.length(STREAM) == 0


async def test_length_of_a_topic_that_does_not_exist_is_zero(transport: KafkaTransport) -> None:
    assert await transport.length(STREAM + ":dlq") == 0


async def test_purge_up_to_cursor_leaves_records_at_later_cursors(
    transport: KafkaTransport,
) -> None:
    """Cursor-bounded purge clears only what a bounded drain read, leaving records
    that arrived at later cursors — the DLQ-replay re-park race.
    """
    await transport.ensure_group(STREAM, GROUP)
    for i in range(5):
        await transport.publish(STREAM, f"f{i}".encode(), key="acctA")

    # Drain the first three; keep the cursor of the last one read.
    drained = await _take(transport.tail(STREAM, from_cursor=CURSOR_BEGIN), 3)
    assert [v for _, v in drained] == [b"f0", b"f1", b"f2"]
    cursor_of_third = drained[-1][0]

    await transport.purge(STREAM, up_to_cursor=cursor_of_third)

    assert await transport.length(STREAM) == 2  # f0..f2 removed, f3/f4 kept
    rest = await _take(transport.tail(STREAM, from_cursor=CURSOR_BEGIN), 2)
    assert [v for _, v in rest] == [b"f3", b"f4"]


async def test_tail_filters_by_routing_key(transport: KafkaTransport) -> None:
    await transport.publish("trading:orders:sessA", b"a1", key="sessA")
    await transport.publish("trading:orders:sessB", b"b1", key="sessB")
    await transport.publish("trading:orders:sessA", b"a2", key="sessA")
    got = await _take(transport.tail("trading:orders:sessA", from_cursor=CURSOR_BEGIN), 2)
    assert [v for _, v in got] == [b"a1", b"a2"]  # only sessA


async def test_tail_resumes_from_concrete_cursor(transport: KafkaTransport) -> None:
    """Reconnect replay: a stored "partition:offset" cursor resumes exactly after it."""
    stream = "trading:orders:sessR"
    for i in range(3):
        await transport.publish(stream, f"m{i}".encode(), key="sessR")

    got = await _take(transport.tail(stream, from_cursor=CURSOR_BEGIN), 1)
    cursor, first = got[0]
    assert first == b"m0"

    for i in range(3, 5):
        await transport.publish(stream, f"m{i}".encode(), key="sessR")

    rest = await _take(transport.tail(stream, from_cursor=cursor), 4)
    assert [v for _, v in rest] == [b"m1", b"m2", b"m3", b"m4"]  # the whole gap, in order


# -- StreamConsumer runtime end-to-end --


async def test_stream_consumer_handles_and_acks(bootstrap: str) -> None:
    bus = EventBus(KafkaTransport(bootstrap, namespace="itestsc"))
    try:
        await bus.publish_envelope(STREAM, _fill_env("o1"), maxlen=100, key="acctA")
        consumer = StreamConsumer(bus, STREAM, GROUP, consumer_name="c1", group_start=CURSOR_BEGIN)

        done = asyncio.Event()
        received: list[str] = []

        async def handler(env: EventEnvelope) -> None:
            received.append(parse_payload(env).client_order_id)
            done.set()

        task = asyncio.create_task(consumer.run(handler))
        try:
            await asyncio.wait_for(done.wait(), timeout=30.0)
        finally:
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task

        assert received == ["o1"]
    finally:
        await bus.close()


# -- multi-partition ordering / rebalance survival / DLQ --


async def _create_topic(bootstrap: str, topic: str, *, partitions: int) -> None:
    """Create a topic with an explicit partition count (namespaces are per-test)."""
    admin = AIOKafkaAdminClient(bootstrap_servers=bootstrap)
    await admin.start()
    try:
        await admin.create_topics(
            [NewTopic(topic, num_partitions=partitions, replication_factor=1)]
        )
    finally:
        await admin.close()


def _partition_of(cursor: str) -> int:
    return int(cursor.split(":", 1)[0])


async def _drains_to_zero(transport: KafkaTransport, *, timeout: float) -> bool:
    """Whether the group's lag reaches zero within ``timeout`` (commits are async)."""
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        if await transport.pending(STREAM, GROUP) == 0:
            return True
        await asyncio.sleep(0.25)
    return False


async def test_key_routing_across_partitions_preserves_per_key_order(
    transport: KafkaTransport, bootstrap: str
) -> None:
    """On a 4-partition topic, keys stick to one partition each (per-key FIFO)
    while distinct keys spread across partitions."""
    await _create_topic(bootstrap, transport.topic(STREAM), partitions=4)

    candidates = [f"acct{i}" for i in range(16)]
    first_partition: dict[str, int] = {}
    for key in candidates:
        cursor = await transport.publish(STREAM, f"{key}:0".encode(), key=key)
        first_partition[key] = _partition_of(cursor)
    # Keyed publishing must actually spread load: 16 keys on 4 partitions.
    assert len(set(first_partition.values())) > 1

    key_a = candidates[0]
    key_b = next(k for k in candidates if first_partition[k] != first_partition[key_a])
    for i in (1, 2, 3):
        for key in (key_a, key_b):
            cursor = await transport.publish(STREAM, f"{key}:{i}".encode(), key=key)
            assert _partition_of(cursor) == first_partition[key]  # sticky per key

    total = len(candidates) + 6
    got = await _take(transport.consume(STREAM, GROUP, "c1", group_start_id=CURSOR_BEGIN), total)

    def per_key(key: str) -> list[tuple[int, int]]:
        prefix = f"{key}:"
        return [
            (_partition_of(cursor), int(value.decode().split(":", 1)[1]))
            for cursor, value in got
            if value.decode().startswith(prefix)
        ]

    seq_a, seq_b = per_key(key_a), per_key(key_b)
    assert [n for _, n in seq_a] == [0, 1, 2, 3]  # per-key order holds
    assert [n for _, n in seq_b] == [0, 1, 2, 3]
    assert {p for p, _ in seq_a} == {first_partition[key_a]}
    assert {p for p, _ in seq_b} == {first_partition[key_b]}
    assert first_partition[key_a] != first_partition[key_b]  # different partitions


async def test_group_member_kill_leaves_no_record_unconsumed(bootstrap: str) -> None:
    """Two group members on a 4-partition topic; one dies mid-stream. The group
    rebalances and every record is eventually consumed — exactly once after the
    writer-side dedup these ids simulate."""
    namespace = f"itkill{uuid4().hex[:12]}"
    victim_transport = KafkaTransport(bootstrap, namespace=namespace)
    survivor_transport = KafkaTransport(bootstrap, namespace=namespace)
    try:
        await _create_topic(bootstrap, victim_transport.topic(STREAM), partitions=4)

        total = 40
        expected = {f"r{i}" for i in range(total)}
        for i in range(total):
            await victim_transport.publish(STREAM, f"r{i}".encode(), key=f"acct{i % 8}")

        victim_seen: set[str] = set()
        victim_started = asyncio.Event()
        survivor_seen: set[str] = set()
        drained = asyncio.Event()

        async def victim() -> None:
            # Consumes but never commits: its records must redeliver after the kill.
            async for _cursor, value in victim_transport.consume(
                STREAM, GROUP, "victim", group_start_id=CURSOR_BEGIN
            ):
                victim_seen.add(value.decode())
                victim_started.set()

        async def survivor() -> None:
            async for cursor, value in survivor_transport.consume(
                STREAM, GROUP, "survivor", group_start_id=CURSOR_BEGIN
            ):
                survivor_seen.add(value.decode())
                await survivor_transport.ack(STREAM, GROUP, cursor)
                if survivor_seen >= expected:
                    drained.set()

        victim_task = asyncio.create_task(victim())
        survivor_task = asyncio.create_task(survivor())
        try:
            # Let the victim demonstrably join and consume, then kill it mid-stream.
            try:
                await asyncio.wait_for(victim_started.wait(), timeout=30.0)
            except TimeoutError:
                pass  # its partitions may hold no records; the kill still rebalances
            victim_task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await victim_task
            await victim_transport.close()

            await asyncio.wait_for(drained.wait(), timeout=120.0)
        finally:
            for task in (victim_task, survivor_task):
                task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await survivor_task

        assert survivor_seen >= expected  # nothing lost across the rebalance
        assert survivor_seen == expected  # dedup by id → exactly once
    finally:
        await survivor_transport.close()
        await victim_transport.close()


async def test_poison_handler_parks_record_on_dlq_keyed_like_source(bootstrap: str) -> None:
    """A handler raising PoisonError dead-letters the entry to the DLQ topic,
    keyed like the source record, and commits past it on the source group."""
    namespace = f"itdlq{uuid4().hex[:12]}"
    transport = KafkaTransport(bootstrap, namespace=namespace)
    bus = EventBus(transport)
    try:
        await _create_topic(bootstrap, transport.topic(STREAM), partitions=2)
        fill = events_pb2.LedgerFill(client_order_id="poison-1", tenant_id="t1", account_id="acctZ")
        envelope = make_envelope(
            events_pb2.EVENT_TYPE_LEDGER_FILL, fill, event_id=derive_event_id("poison-1")
        )
        await bus.publish_envelope(STREAM, envelope, key="acctZ")

        consumer = StreamConsumer(bus, STREAM, GROUP, consumer_name="c1", group_start=CURSOR_BEGIN)

        async def poison_handler(env: EventEnvelope) -> None:
            raise PoisonError("permanently unprocessable")

        task = asyncio.create_task(consumer.run(poison_handler))
        dlq_topic = transport.topic(STREAM + ":dlq")
        reader = AIOKafkaConsumer(
            dlq_topic,
            bootstrap_servers=bootstrap,
            group_id=None,
            enable_auto_commit=False,
            auto_offset_reset="earliest",
        )
        await reader.start()
        try:
            record = await asyncio.wait_for(reader.getone(), timeout=60.0)
            # The commit follows the DLQ publish, so let it land on the live
            # member before the consumer task (and its group membership) ends.
            drained = await _drains_to_zero(transport, timeout=30.0)
        finally:
            await reader.stop()
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task

        assert record.key == b"acctZ"  # DLQ keyed like the source partition key
        assert record.value is not None
        parked = decode_envelope(record.value)
        assert parked.id == envelope.id
        parked_fill = parse_payload(parked)
        assert isinstance(parked_fill, events_pb2.LedgerFill)
        assert parked_fill.client_order_id == "poison-1"
        # The source group committed past the poison entry — it cannot wedge.
        assert drained
    finally:
        await bus.close()


async def test_tail_cursor_resume_reads_every_partition(bootstrap: str) -> None:
    """A concrete cursor resumes the whole topic, not just the cursor's partition.

    Trading's order/position topics are provisioned with several partitions, so a
    reader that stored a cursor and reconnects must assign all of them: the
    cursor's from ``offset + 1``, the rest from their end. Assigning only the
    cursor's partition leaves the reader silently blind to the others.
    """
    namespace = f"itseek{uuid4().hex[:12]}"
    transport = KafkaTransport(bootstrap, namespace=namespace)
    try:
        await _create_topic(bootstrap, transport.topic(STREAM), partitions=3)

        # One key per partition, learned from the cursors publishing hands back.
        key_for: dict[int, str] = {}
        for i in range(32):
            cursor = await transport.publish(STREAM, b"seed", key=f"acct{i}")
            key_for.setdefault(_partition_of(cursor), f"acct{i}")
        assert set(key_for) == {0, 1, 2}, "keys did not spread over all three partitions"

        resume_from = await transport.publish(STREAM, b"seed", key=key_for[0])
        assert _partition_of(resume_from) == 0
        seen: set[int] = set()

        async def read() -> None:
            async for cursor, _value in transport.tail(STREAM, from_cursor=resume_from):
                seen.add(_partition_of(cursor))

        async def publish_until_every_partition_arrives() -> None:
            # The non-cursor partitions resume at their end, so only records
            # published after the assignment are guaranteed to arrive; republish
            # until the reader has seen all three (a resume that assigned one
            # partition never gets there).
            while seen != {0, 1, 2}:
                for key in key_for.values():
                    await transport.publish(STREAM, b"after", key=key)
                await asyncio.sleep(0.5)

        reader = asyncio.create_task(read())
        try:
            await asyncio.wait_for(publish_until_every_partition_arrives(), timeout=60.0)
        finally:
            reader.cancel()
            with pytest.raises(asyncio.CancelledError):
                await reader

        assert seen == {0, 1, 2}
    finally:
        await transport.close()
