"""DLQ replay against a real Kafka broker.

Proves the operator tool's contract on real partitions: parked entries are
re-published onto the main fill topic, and the cursor-bounded
``purge(up_to_cursor=)`` removes exactly what this run drained — entries past
the drained high-water mark survive for a follow-up run.
"""

from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest

from llamatrade_events import (
    CURSOR_BEGIN,
    EventBus,
    LedgerFill,
    derive_event_id,
    encode_envelope,
    make_envelope,
)
from llamatrade_events.transport.kafka import KafkaTransport
from llamatrade_proto.generated import events_pb2

from src.tasks.dlq_replay import replay_dlq
from src.tasks.fill_ingestion import LEDGER_FILLS_DLQ_STREAM, LEDGER_FILLS_STREAM

pytestmark = pytest.mark.integration

_ACCOUNT = str(uuid4())


def _fill_bytes(client_order_id: str) -> bytes:
    fill = LedgerFill(
        tenant_id=str(uuid4()),
        account_id=_ACCOUNT,
        sleeve_id=str(uuid4()),
        client_order_id=client_order_id,
        symbol="SPY",
        side="buy",
        qty="5",
        price="100",
        filled_at="2026-06-12T14:30:00+00:00",
    )
    return encode_envelope(
        make_envelope(
            events_pb2.EVENT_TYPE_LEDGER_FILL, fill, event_id=derive_event_id(client_order_id)
        )
    )


async def _read_n(bus: EventBus, stream: str, n: int, *, timeout: float = 30.0) -> list[bytes]:
    async def _collect() -> list[bytes]:
        out: list[bytes] = []
        async for _cursor, raw in bus.tail_raw(stream, from_cursor=CURSOR_BEGIN):
            out.append(raw)
            if len(out) >= n:
                break
        return out

    return await asyncio.wait_for(_collect(), timeout=timeout)


async def _wait_length(bus: EventBus, stream: str, expected: int, *, timeout: float = 30.0) -> None:
    async def _poll() -> None:
        while await bus.length(stream) != expected:
            await asyncio.sleep(0.25)

    await asyncio.wait_for(_poll(), timeout=timeout)


async def test_replay_republishes_and_purges_only_what_it_drained(kafka_bootstrap: str) -> None:
    namespace = f"dlq{uuid4().hex[:12]}"
    bus = EventBus(KafkaTransport(kafka_bootstrap, namespace=namespace))
    try:
        # One partition key so the three parks share a partition in strict order —
        # exactly how the quarantine parks an account's fills.
        parked = [_fill_bytes("dlq-1"), b"\xff\xfe not an envelope", _fill_bytes("dlq-3")]
        for raw in parked:
            await bus.publish_raw(LEDGER_FILLS_DLQ_STREAM, raw, key=_ACCOUNT)
        await _wait_length(bus, LEDGER_FILLS_DLQ_STREAM, 3)

        # Bounded run drains the first two; the purge must spare the third.
        assert await replay_dlq(bus, max_entries=2) == 2
        await _wait_length(bus, LEDGER_FILLS_DLQ_STREAM, 1)
        assert sorted(await _read_n(bus, LEDGER_FILLS_STREAM, 2)) == sorted(parked[:2])

        # The follow-up run drains the survivor and clears the DLQ.
        assert await replay_dlq(bus) == 1
        await _wait_length(bus, LEDGER_FILLS_DLQ_STREAM, 0)
        assert sorted(await _read_n(bus, LEDGER_FILLS_STREAM, 3)) == sorted(parked)
    finally:
        await bus.close()


async def test_replay_of_an_empty_dlq_is_a_noop(kafka_bootstrap: str) -> None:
    namespace = f"dlq{uuid4().hex[:12]}"
    bus = EventBus(KafkaTransport(kafka_bootstrap, namespace=namespace))
    try:
        assert await replay_dlq(bus) == 0
    finally:
        await bus.close()
