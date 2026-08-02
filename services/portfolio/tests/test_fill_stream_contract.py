"""End-to-end trading↔ledger contract test over the stream seam.

A proto ``LedgerFill`` published exactly as trading publishes it round-trips
through the in-memory ``FakeTransport`` — publish → durable consume → decode →
translate — into the portfolio ingestion. This exercises the transport + proto
codec + translation together, which the mock-based ingestion tests skip.
"""

from uuid import UUID, uuid4

import pytest

from llamatrade_db.models.ledger import LedgerEventType
from llamatrade_events import EventBus, FillEvents, LedgerFill
from llamatrade_events.testing import FakeTransport

from src.ledger.ingestion import LedgerAppend
from src.tasks.fill_ingestion import (
    CURSOR_BEGIN,
    LEDGER_FILLS_STREAM,
    PORTFOLIO_LEDGER_GROUP,
    _decode_message,
    process_stream_entry,
)

pytestmark = pytest.mark.asyncio


async def test_ledger_fill_contract_roundtrips_through_stream() -> None:
    tenant, account, sleeve = str(uuid4()), str(uuid4()), str(uuid4())
    fills = FillEvents(bus=EventBus(FakeTransport()))

    fill = LedgerFill(
        tenant_id=tenant,
        account_id=account,
        sleeve_id=sleeve,
        client_order_id="co-xyz",
        symbol="AAPL",
        side="buy",
        qty="10",
        price="150.25",
    )
    await fills.publish_fill(fill)  # the trading side of the contract

    appends: list[LedgerAppend] = []

    async def handler(a: LedgerAppend) -> None:
        appends.append(a)

    async for _entry_id, raw in fills.bus.consume_raw(
        LEDGER_FILLS_STREAM,
        PORTFOLIO_LEDGER_GROUP,
        "test-consumer",
        group_start_id=CURSOR_BEGIN,
    ):
        message = _decode_message(raw)
        assert message is not None
        assert await process_stream_entry(handler, message) == "ack"
        break

    await fills.close()

    assert len(appends) == 1
    a = appends[0]
    assert a.tenant_id == UUID(tenant)
    assert a.account_id == UUID(account)
    assert a.sleeve_id == UUID(sleeve)
    assert a.event_type == LedgerEventType.ORDER_FILLED
    assert a.data["symbol"] == "AAPL"
    assert a.data["side"] == "buy"
    assert a.data["qty"] == "10"
    assert a.data["price"] == "150.25"


async def test_replay_dlq_redrives_and_clears() -> None:
    from src.tasks.dlq_replay import replay_dlq
    from src.tasks.fill_ingestion import LEDGER_FILLS_DLQ_STREAM

    transport = FakeTransport()
    bus = EventBus(transport)

    # Two parked entries (opaque bytes, as _dead_letter parks them).
    await bus.publish_raw(LEDGER_FILLS_DLQ_STREAM, b"entry-1")
    await bus.publish_raw(LEDGER_FILLS_DLQ_STREAM, b"entry-2")
    assert await bus.length(LEDGER_FILLS_DLQ_STREAM) == 2

    replayed = await replay_dlq(bus)

    assert replayed == 2
    assert await bus.length(LEDGER_FILLS_STREAM) == 2  # re-driven onto the main stream
    assert await bus.length(LEDGER_FILLS_DLQ_STREAM) == 0  # cleared on full drain
    await bus.close()


async def test_replay_dlq_keys_decodable_entries_by_account() -> None:
    """Replayed fills carry key=account_id so they land on the account's partition
    (in order); only undecodable bytes replay unkeyed."""
    from llamatrade_events import derive_event_id, encode_envelope, make_envelope
    from llamatrade_proto.generated import events_pb2

    from src.tasks.dlq_replay import replay_dlq
    from src.tasks.fill_ingestion import LEDGER_FILLS_DLQ_STREAM

    account = str(uuid4())
    fill = LedgerFill(
        tenant_id=str(uuid4()),
        account_id=account,
        sleeve_id=str(uuid4()),
        client_order_id="co-dlq",
        symbol="AAPL",
        side="buy",
        qty="10",
        price="150.25",
    )
    parked = encode_envelope(
        make_envelope(
            events_pb2.EVENT_TYPE_LEDGER_FILL,
            fill,
            event_id=derive_event_id(fill.client_order_id),
        )
    )

    transport = FakeTransport()
    bus = EventBus(transport)
    await bus.publish_raw(LEDGER_FILLS_DLQ_STREAM, parked)
    await bus.publish_raw(LEDGER_FILLS_DLQ_STREAM, b"\xffundecodable")

    assert await replay_dlq(bus) == 2

    replays = [r for r in transport.records if r.stream == LEDGER_FILLS_STREAM]
    assert [(r.value, r.key) for r in replays] == [
        (parked, account),  # decodable → keyed by account
        (b"\xffundecodable", None),  # corrupt bytes → unkeyed fallback
    ]
    await bus.close()


async def test_replay_dlq_empty_is_noop() -> None:
    from src.tasks.dlq_replay import replay_dlq

    bus = EventBus(FakeTransport())
    assert await replay_dlq(bus) == 0
    await bus.close()


async def test_replay_dlq_purges_only_what_it_drained() -> None:
    """A cursor-bounded purge clears exactly the drained entries and leaves those
    past the high-water mark (a re-park during the run, or an over-max backlog)."""
    from src.tasks.dlq_replay import replay_dlq
    from src.tasks.fill_ingestion import LEDGER_FILLS_DLQ_STREAM

    transport = FakeTransport()
    bus = EventBus(transport)
    await bus.publish_raw(LEDGER_FILLS_DLQ_STREAM, b"e1")
    await bus.publish_raw(LEDGER_FILLS_DLQ_STREAM, b"e2")
    await bus.publish_raw(LEDGER_FILLS_DLQ_STREAM, b"e3")

    replayed = await replay_dlq(bus, max_entries=2)  # drain only the first two

    assert replayed == 2
    # e1/e2 purged up to the high-water cursor; e3 (a later cursor) survives.
    assert [value for _cursor, value in transport.entries(LEDGER_FILLS_DLQ_STREAM)] == [b"e3"]
    await bus.close()


async def test_replay_dlq_skips_and_purges_null_entry() -> None:
    """A null/tombstone entry is never republished but is still purged (its cursor
    advances the per-partition high-water mark)."""
    from src.tasks.dlq_replay import replay_dlq
    from src.tasks.fill_ingestion import LEDGER_FILLS_DLQ_STREAM

    transport = FakeTransport()
    bus = EventBus(transport)
    await bus.publish_raw(LEDGER_FILLS_DLQ_STREAM, b"")  # tombstone / empty
    await bus.publish_raw(LEDGER_FILLS_DLQ_STREAM, b"real")

    replayed = await replay_dlq(bus)

    assert replayed == 1  # the null was skipped, not republished
    assert await bus.length(LEDGER_FILLS_DLQ_STREAM) == 0  # both purged, null included
    assert [value for stream, value in transport.published if stream == LEDGER_FILLS_STREAM] == [
        b"real"
    ]
    await bus.close()
