"""Fill-ingestion wiring tests — pure, no broker/DB.

Covers the per-envelope path (``make_entry_handler``): parse + translate a
consumed envelope → append, with poison/quarantine surfaced as ``PoisonError``
and transient failures re-raised; the quarantine park (``make_fill_quarantine``);
and the composed ``consume_fill_stream`` over the in-memory transport. The DB
persistence (``persist_append`` → ``LedgerWriter``) is the thin IO shell,
exercised by the integration suite; loop-vs-legacy equivalence is pinned by
``test_fill_ingestion_parity.py``.
"""

from typing import cast
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from llamatrade_db.models.ledger import LedgerEventType
from llamatrade_events import (
    EventBus,
    EventEnvelope,
    FillEvents,
    LedgerFill,
    LedgerReservation,
    PoisonError,
    decode_envelope,
    derive_event_id,
    encode_envelope,
    make_envelope,
)
from llamatrade_events.testing import FakeTransport
from llamatrade_proto.generated import events_pb2

from src.ledger.ingestion import FillQuarantineError, LedgerAppend
from src.tasks.fill_ingestion import (
    LEDGER_FILLS_DLQ_STREAM,
    LEDGER_FILLS_STREAM,
    PORTFOLIO_LEDGER_GROUP,
    _dead_letter,
    consume_fill_stream,
    fill_retry_policy,
    make_entry_handler,
    make_fill_quarantine,
)


def _fill_env(**overrides: str) -> EventEnvelope:
    """A decoded envelope wrapping a LedgerFill (what the entry handler receives)."""
    fill = _fill(**overrides)
    return make_envelope(
        events_pb2.EVENT_TYPE_LEDGER_FILL,
        fill,
        event_id=derive_event_id(fill.client_order_id),
    )


def _reservation_env(**overrides: str) -> EventEnvelope:
    reservation = _reservation(**overrides)
    return make_envelope(
        events_pb2.EVENT_TYPE_LEDGER_RESERVATION,
        reservation,
        event_id=derive_event_id(reservation.client_order_id, reservation.event_type),
    )


def _raw_fill(**overrides: str) -> bytes:
    """A wire-encoded envelope wrapping a LedgerFill (what the consumer receives)."""
    return encode_envelope(_fill_env(**overrides))


TENANT = str(uuid4())
ACCOUNT = str(uuid4())
SLEEVE = str(uuid4())


def _fill(**overrides: str) -> LedgerFill:
    fields = {
        "tenant_id": TENANT,
        "account_id": ACCOUNT,
        "sleeve_id": SLEEVE,
        "client_order_id": "co-123",
        "symbol": "AAPL",
        "side": "buy",
        "qty": "10",
        "price": "150.25",
    }
    fields.update(overrides)
    return LedgerFill(**fields)


def _reservation(**overrides: str) -> LedgerReservation:
    fields = {
        "tenant_id": TENANT,
        "account_id": ACCOUNT,
        "sleeve_id": SLEEVE,
        "client_order_id": "co-123",
        "symbol": "AAPL",
        "side": "buy",
    }
    fields.update(overrides)
    return LedgerReservation(**fields)


class _Recorder:
    def __init__(self) -> None:
        self.appends: list[LedgerAppend] = []

    async def __call__(self, append: LedgerAppend) -> None:
        self.appends.append(append)


class _FlakyRecorder:
    """Handler that fails N times before succeeding (transient persistence)."""

    def __init__(self, failures: int = 0) -> None:
        self.appends: list[LedgerAppend] = []
        self._failures = failures

    async def __call__(self, append: LedgerAppend) -> None:
        if self._failures > 0:
            self._failures -= 1
            raise ConnectionError("db hiccup")
        self.appends.append(append)


async def test_translates_and_drives_handler() -> None:
    rec = _Recorder()
    await make_entry_handler(rec)(_fill_env())

    assert len(rec.appends) == 1
    append = rec.appends[0]
    assert append.tenant_id == UUID(TENANT)
    assert append.account_id == UUID(ACCOUNT)
    assert append.sleeve_id == UUID(SLEEVE)
    assert append.event_type == LedgerEventType.ORDER_FILLED
    assert append.data["symbol"] == "AAPL"
    assert append.data["side"] == "buy"
    assert append.data["qty"] == "10"
    assert append.data["price"] == "150.25"


async def test_idempotency_id_is_deterministic() -> None:
    rec = _Recorder()
    handle = make_entry_handler(rec)
    await handle(_fill_env())
    await handle(_fill_env())
    # Same client_order_id → identical ledger event_id (writer dedups on it).
    assert rec.appends[0].event_id == rec.appends[1].event_id


async def test_unknown_lifecycle_kind_is_poison() -> None:
    rec = _Recorder()
    with pytest.raises(PoisonError):
        await make_entry_handler(rec)(_reservation_env(event_type="order_teleported"))
    assert rec.appends == []


async def test_missing_required_field_is_poison() -> None:
    rec = _Recorder()
    # An empty required scalar (proto3 can't omit fields) is poison, not retried.
    with pytest.raises(PoisonError):
        await make_entry_handler(rec)(_fill_env(price=""))
    assert rec.appends == []


async def test_transient_failure_reraises_for_retry() -> None:
    """A persistence failure propagates untouched — the RetryForever policy
    classifies it transient and redelivers until it lands."""
    rec = _FlakyRecorder(failures=1)
    handle = make_entry_handler(rec)
    with pytest.raises(ConnectionError):
        await handle(_fill_env())
    await handle(_fill_env())  # in-place retry
    assert len(rec.appends) == 1


async def test_quarantined_fill_raises_poison_not_transient() -> None:
    """A sell with no resolvable cost basis (FillQuarantineError) surfaces as
    PoisonError (quarantine + ack), never as a transient retry — or it would
    redeliver forever and wedge the FIFO consumer."""

    async def _quarantine(_append: LedgerAppend) -> None:
        raise FillQuarantineError("no open lots to cover the sell")

    with pytest.raises(PoisonError):
        await make_entry_handler(_quarantine)(_fill_env(side="sell"))


class _FakeBus:
    """Records publish_raw (DLQ park), ack (offset commit), and pause/resume calls."""

    def __init__(self) -> None:
        self.published: list[tuple[str, bytes, str | None]] = []
        self.acked: list[str] = []
        self.paused: list[tuple[str, str, str]] = []
        self.resumed: list[tuple[str, str, str]] = []

    async def publish_raw(
        self, stream: str, value: bytes, *, key: str | None = None, maxlen: int | None = None
    ) -> str:
        self.published.append((stream, value, key))
        return "0-1"

    async def ack(self, stream: str, group: str, cursor: str) -> None:
        self.acked.append(cursor)

    async def pause_partition(self, stream: str, group: str, cursor: str) -> None:
        self.paused.append((stream, group, cursor))

    async def resume_partition(self, stream: str, group: str, cursor: str) -> None:
        self.resumed.append((stream, group, cursor))


async def test_dead_letter_parks_unrecordable_entry() -> None:
    """An unrecordable raw entry is parked on the DLQ stream (recoverable)."""
    bus = _FakeBus()
    await _dead_letter(cast(EventBus, bus), b"corrupt-bytes")
    assert bus.published[0][0] == LEDGER_FILLS_DLQ_STREAM
    assert bus.published[0][1] == b"corrupt-bytes"
    assert bus.published[0][2] is None  # undecodable → no recoverable account key


async def test_dead_letter_parks_with_account_key() -> None:
    """A decodable entry parks keyed by account so replay preserves per-account order."""
    bus = _FakeBus()
    await _dead_letter(cast(EventBus, bus), b"payload", key="acct-9")
    assert bus.published[0] == (LEDGER_FILLS_DLQ_STREAM, b"payload", "acct-9")


async def test_dead_letter_swallows_publish_failure() -> None:
    """A DLQ publish failure must not propagate and wedge the consumer."""

    class _BadBus:
        async def publish_raw(self, *args: object, **kwargs: object) -> str:
            raise RuntimeError("broker down")

    await _dead_letter(cast(EventBus, _BadBus()), b"x")  # must not raise


# --- make_fill_quarantine: park the raw entry on the ledger DLQ ---------------


async def test_quarantine_parks_undecodable_bytes_unkeyed() -> None:
    bus = _FakeBus()
    await make_fill_quarantine(cast(EventBus, bus))(
        b"\xffnot-an-envelope", None, ValueError("bad bytes")
    )
    assert bus.published == [(LEDGER_FILLS_DLQ_STREAM, b"\xffnot-an-envelope", None)]


async def test_quarantine_parks_decodable_entry_keyed_by_account() -> None:
    bus = _FakeBus()
    raw = _raw_fill(side="sell")
    await make_fill_quarantine(cast(EventBus, bus))(
        raw, decode_envelope(raw), FillQuarantineError("no open lots")
    )
    assert bus.published == [(LEDGER_FILLS_DLQ_STREAM, raw, ACCOUNT)]


# --- consume_fill_stream: the composed consumer over the in-memory transport --


def _stream_fixture() -> tuple[FakeTransport, FillEvents]:
    transport = FakeTransport()
    return transport, FillEvents(bus=EventBus(transport))


def _dlq_parks(transport: FakeTransport) -> list[tuple[bytes, str | None]]:
    return [(r.value, r.key) for r in transport.records if r.stream == LEDGER_FILLS_DLQ_STREAM]


async def test_consume_success_persists_and_commits() -> None:
    transport, fills = _stream_fixture()
    await fills.publish_fill(_fill())
    rec = _Recorder()

    await consume_fill_stream(fills, rec, consumer_name="c1")

    assert len(rec.appends) == 1
    assert await fills.bus.pending(LEDGER_FILLS_STREAM, PORTFOLIO_LEDGER_GROUP) == 0  # committed
    assert _dlq_parks(transport) == []
    assert transport.pause_calls == []  # no retry → no partition pause


async def test_consume_retries_in_place_pausing_the_partition() -> None:
    """A transient failure never dead-letters: the entry retries in place with
    its partition paused once, then commits exactly once when the fill lands."""
    transport, fills = _stream_fixture()
    await fills.publish_fill(_fill())
    rec = _FlakyRecorder(failures=3)
    consumer = fills.consumer(
        consumer_name="c1",
        policy=fill_retry_policy(fills.bus, base_delay_seconds=0.0, max_delay_seconds=0.0),
    )

    await consumer.run(make_entry_handler(rec))

    assert len(rec.appends) == 1
    assert _dlq_parks(transport) == []  # never dead-lettered a real fill
    assert len(transport.pause_calls) == 1  # paused once, not per attempt
    assert len(transport.resume_calls) == 1
    assert await fills.bus.pending(LEDGER_FILLS_STREAM, PORTFOLIO_LEDGER_GROUP) == 0


async def test_consume_undecodable_entry_parks_unkeyed_and_continues() -> None:
    transport, fills = _stream_fixture()
    garbage = b"\xffnot-an-envelope"
    await fills.bus.publish_raw(LEDGER_FILLS_STREAM, garbage)
    await fills.publish_fill(_fill())
    rec = _Recorder()

    await consume_fill_stream(fills, rec, consumer_name="c1")

    assert _dlq_parks(transport) == [(garbage, None)]  # parked unkeyed, raw preserved
    assert len(rec.appends) == 1  # the stream continued past the poison entry
    assert await fills.bus.pending(LEDGER_FILLS_STREAM, PORTFOLIO_LEDGER_GROUP) == 0


async def test_consume_quarantined_fill_parks_keyed_and_commits() -> None:
    transport, fills = _stream_fixture()
    await fills.publish_fill(_fill(side="sell"))

    async def _quarantine(_append: LedgerAppend) -> None:
        raise FillQuarantineError("no open lots to cover the sell")

    await consume_fill_stream(fills, _quarantine, consumer_name="c1")

    parks = _dlq_parks(transport)
    assert len(parks) == 1
    assert parks[0][1] == ACCOUNT  # keyed by account for ordered replay
    assert await fills.bus.pending(LEDGER_FILLS_STREAM, PORTFOLIO_LEDGER_GROUP) == 0


async def test_routes_lifecycle_events() -> None:
    rec = _Recorder()
    await make_entry_handler(rec)(_reservation_env(event_type="order_submitted", reserved="1000"))
    append = rec.appends[0]
    assert append.event_type == LedgerEventType.ORDER_SUBMITTED
    assert append.data["reserved"] == "1000"


async def test_reservation_and_fill_have_distinct_ids() -> None:
    rec = _Recorder()
    handle = make_entry_handler(rec)
    await handle(_reservation_env(event_type="order_submitted", reserved="1502.50"))
    await handle(_fill_env())
    # Reservation stage must not collide with the fill's idempotency key.
    assert rec.appends[0].event_id != rec.appends[1].event_id


# --- late-fill routing: a fill for a CLOSED sleeve re-homes to Unmanaged -------


def _ledger_sleeve(stype, status, *, tenant: UUID, account: UUID):
    from decimal import Decimal

    from llamatrade_db.models.ledger import Sleeve

    s = Sleeve(
        tenant_id=tenant,
        account_id=account,
        type=stype.value,
        status=status.value,
        name=stype.value,
        strategy_execution_id=None,
        allocated_capital=Decimal("0"),
    )
    s.id = uuid4()
    return s


def _fill_append(sleeve_id: UUID, tenant: UUID, account: UUID) -> LedgerAppend:
    from datetime import UTC, datetime

    return LedgerAppend(
        tenant_id=tenant,
        account_id=account,
        sleeve_id=sleeve_id,
        event_type=LedgerEventType.ORDER_FILLED,
        data={
            "sleeve_id": str(sleeve_id),
            "symbol": "AAPL",
            "side": "buy",
            "qty": "10",
            "price": "150",
        },
        event_id=uuid4(),
        occurred_at=datetime.now(UTC),
    )


async def test_reroute_closed_sleeve_to_unmanaged() -> None:
    from unittest.mock import AsyncMock

    from llamatrade_db.models.ledger import SleeveStatus, SleeveType

    from src.tasks.fill_ingestion import _reroute_if_sleeve_closed

    tenant, account = uuid4(), uuid4()
    closed = _ledger_sleeve(
        SleeveType.STRATEGY, SleeveStatus.CLOSED, tenant=tenant, account=account
    )
    unmanaged = _ledger_sleeve(
        SleeveType.UNMANAGED, SleeveStatus.ACTIVE, tenant=tenant, account=account
    )
    db = AsyncMock()
    db.scalar = AsyncMock(side_effect=[closed, unmanaged])  # get_sleeve, get_sleeve_by_type
    append = _fill_append(closed.id, tenant, account)

    result = await _reroute_if_sleeve_closed(db, append)

    assert result.sleeve_id == unmanaged.id
    assert result.data["sleeve_id"] == str(unmanaged.id)


async def test_reroute_noop_for_active_sleeve() -> None:
    from unittest.mock import AsyncMock

    from llamatrade_db.models.ledger import SleeveStatus, SleeveType

    from src.tasks.fill_ingestion import _reroute_if_sleeve_closed

    tenant, account = uuid4(), uuid4()
    active = _ledger_sleeve(
        SleeveType.STRATEGY, SleeveStatus.ACTIVE, tenant=tenant, account=account
    )
    db = AsyncMock()
    db.scalar = AsyncMock(side_effect=[active])
    append = _fill_append(active.id, tenant, account)

    result = await _reroute_if_sleeve_closed(db, append)

    assert result is append  # unchanged, no Unmanaged lookup
    assert db.scalar.await_count == 1


async def test_reroute_noop_when_no_unmanaged_sleeve() -> None:
    from unittest.mock import AsyncMock

    from llamatrade_db.models.ledger import SleeveStatus, SleeveType

    from src.tasks.fill_ingestion import _reroute_if_sleeve_closed

    tenant, account = uuid4(), uuid4()
    closed = _ledger_sleeve(
        SleeveType.STRATEGY, SleeveStatus.CLOSED, tenant=tenant, account=account
    )
    db = AsyncMock()
    db.scalar = AsyncMock(side_effect=[closed, None])  # account missing Unmanaged
    append = _fill_append(closed.id, tenant, account)

    result = await _reroute_if_sleeve_closed(db, append)

    assert result.sleeve_id == closed.id  # left untouched for reconciliation


# --------------------------------------------------------------------------- #
# Ledger-writer lease
# --------------------------------------------------------------------------- #


class _FakeLeaseSession:
    """An AsyncSession stand-in whose advisory-lock probe is scripted."""

    def __init__(self, *, held: bool, raises: bool = False) -> None:
        self.held = held
        self.raises = raises
        self.probes = 0
        self.closed = False
        self.unlocked = False

    async def scalar(self, statement: object, params: object = None) -> object:
        text = str(statement)
        if "pg_advisory_unlock" in text:
            self.unlocked = True
            if self.raises:
                raise RuntimeError("connection is closed")
            return True
        self.probes += 1
        if self.raises:
            raise RuntimeError("connection is closed")
        return self.held

    async def close(self) -> None:
        self.closed = True


async def test_lease_reports_leadership_while_the_lock_is_held() -> None:
    from src.tasks.fill_ingestion import LedgerWriterLease

    session = _FakeLeaseSession(held=True)
    lease = LedgerWriterLease(cast(AsyncSession, session))

    assert await lease.is_leader() is True
    assert await lease.is_leader() is True
    assert session.probes == 2  # asked every time, never cached as "still mine"
    assert lease.lost.is_set() is False


async def test_lease_latches_the_loss_and_wakes_the_sweeps() -> None:
    """Once the lock is gone the lease stays lost and stops probing a dead
    connection; ``lost`` is what pulls the sweeps out of their interval sleeps."""
    from src.tasks.fill_ingestion import LedgerWriterLease

    session = _FakeLeaseSession(held=False)
    lease = LedgerWriterLease(cast(AsyncSession, session))

    assert await lease.is_leader() is False
    assert lease.lost.is_set() is True
    assert await lease.is_leader() is False
    assert session.probes == 1  # latched — no second round trip


async def test_lease_treats_a_torn_connection_as_lost_leadership() -> None:
    from src.tasks.fill_ingestion import LedgerWriterLease

    session = _FakeLeaseSession(held=True, raises=True)
    lease = LedgerWriterLease(cast(AsyncSession, session))

    assert await lease.is_leader() is False
    assert lease.lost.is_set() is True


async def test_releasing_the_writer_lock_absorbs_a_torn_connection() -> None:
    """Shutdown still has a Kafka client and a pool to close, so the unlock on a
    dead connection must warn rather than raise."""
    from src.tasks.fill_ingestion import release_ledger_writer_lock

    session = _FakeLeaseSession(held=True, raises=True)

    await release_ledger_writer_lock(cast(AsyncSession, session))

    assert session.unlocked is True
    assert session.closed is True
