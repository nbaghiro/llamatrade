"""Fill-ingestion wiring tests — pure, no Redis/DB.

Covers the stream-entry path (``process_stream_entry``): translate a parsed proto
message → append, with ack/drop/retry verdicts. The DB persistence
(``persist_append`` → ``LedgerWriter``) is the thin IO shell, exercised by the
integration suite.
"""

from typing import cast
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from llamatrade_db.models.ledger import LedgerEventType
from llamatrade_events import (
    EventBus,
    LedgerFill,
    LedgerReservation,
    derive_event_id,
    encode_envelope,
    make_envelope,
)
from llamatrade_proto.generated import events_pb2

from src.ledger.ingestion import FillQuarantineError, LedgerAppend
from src.tasks.fill_ingestion import (
    LEDGER_FILLS_DLQ_STREAM,
    LEDGER_FILLS_STREAM,
    PORTFOLIO_LEDGER_GROUP,
    _dead_letter,
    handle_ledger_entry,
    process_stream_entry,
)


def _raw_fill(**overrides: str) -> bytes:
    """A wire-encoded envelope wrapping a LedgerFill (what the consumer receives)."""
    fill = _fill(**overrides)
    return encode_envelope(
        make_envelope(
            events_pb2.EVENT_TYPE_LEDGER_FILL,
            fill,
            event_id=derive_event_id(fill.client_order_id),
        )
    )


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
    verdict = await process_stream_entry(rec, _fill())

    assert verdict == "ack"
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
    await process_stream_entry(rec, _fill())
    await process_stream_entry(rec, _fill())
    # Same client_order_id → identical ledger event_id (writer dedups on it).
    assert rec.appends[0].event_id == rec.appends[1].event_id


async def test_ack_on_success() -> None:
    rec = _Recorder()
    verdict = await process_stream_entry(rec, _fill())
    assert verdict == "ack"
    assert len(rec.appends) == 1


async def test_poison_dropped() -> None:
    rec = _Recorder()
    verdict = await process_stream_entry(rec, _reservation(event_type="order_teleported"))
    assert verdict == "drop"  # acked anyway — never redeliver poison forever
    assert rec.appends == []


async def test_missing_required_field_is_poison() -> None:
    rec = _Recorder()
    # An empty required scalar (proto3 can't omit fields) is poison, not retried.
    verdict = await process_stream_entry(rec, _fill(price=""))
    assert verdict == "drop"
    assert rec.appends == []


async def test_transient_failure_retries() -> None:
    rec = _FlakyRecorder(failures=1)
    first = await process_stream_entry(rec, _fill())
    second = await process_stream_entry(rec, _fill())  # group redelivery
    assert first == "retry"  # left pending
    assert second == "ack"
    assert len(rec.appends) == 1


async def test_quarantined_fill_is_dropped_not_retried() -> None:
    """A sell with no resolvable cost basis (FillQuarantineError) is dropped + alerted,
    never left pending — or it would redeliver forever and wedge the FIFO consumer."""

    async def _quarantine(_append: LedgerAppend) -> None:
        raise FillQuarantineError("no open lots to cover the sell")

    verdict = await process_stream_entry(_quarantine, _fill(side="sell"))
    assert verdict == "drop"  # NOT "retry"


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


# --- handle_ledger_entry: per-entry decode → persist → ack (in-place retry) ----


async def test_handle_entry_success_acks() -> None:
    rec = _Recorder()
    bus = _FakeBus()
    await handle_ledger_entry(cast(EventBus, bus), rec, "0:0", _raw_fill())
    assert len(rec.appends) == 1
    assert bus.acked == ["0:0"]  # committed
    assert bus.published == []  # nothing dead-lettered
    assert bus.paused == []  # no retry → no partition pause


async def test_handle_entry_retries_in_place_then_acks(monkeypatch: pytest.MonkeyPatch) -> None:
    import src.tasks.fill_ingestion as fi

    monkeypatch.setattr(fi, "_RETRY_BASE_DELAY_SECONDS", 0.0)
    monkeypatch.setattr(fi, "_RETRY_MAX_DELAY_SECONDS", 0.0)
    rec = _FlakyRecorder(failures=2)  # two transient DB hiccups, then success
    bus = _FakeBus()
    await handle_ledger_entry(cast(EventBus, bus), rec, "0:0", _raw_fill())
    # Retried in place until it landed (Kafka won't redeliver to a live consumer),
    # then committed exactly once — never dead-lettered a real fill.
    assert len(rec.appends) == 1
    assert bus.acked == ["0:0"]
    assert bus.published == []


async def test_handle_entry_retry_pauses_partition_until_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The retried entry's partition is paused once (not per attempt) and resumed
    after the fill lands, so the fetcher stops prefetching the stalled partition."""
    import src.tasks.fill_ingestion as fi

    monkeypatch.setattr(fi, "_RETRY_BASE_DELAY_SECONDS", 0.0)
    monkeypatch.setattr(fi, "_RETRY_MAX_DELAY_SECONDS", 0.0)
    rec = _FlakyRecorder(failures=3)
    bus = _FakeBus()
    await handle_ledger_entry(cast(EventBus, bus), rec, "2:7", _raw_fill())
    assert bus.paused == [(LEDGER_FILLS_STREAM, PORTFOLIO_LEDGER_GROUP, "2:7")]
    assert bus.resumed == [(LEDGER_FILLS_STREAM, PORTFOLIO_LEDGER_GROUP, "2:7")]
    assert bus.acked == ["2:7"]
    assert len(rec.appends) == 1


async def test_handle_entry_poison_deadletters_and_acks() -> None:
    rec = _Recorder()
    bus = _FakeBus()
    await handle_ledger_entry(cast(EventBus, bus), rec, "0:0", b"\xffnot-an-envelope")
    assert rec.appends == []
    assert bus.published[0][0] == LEDGER_FILLS_DLQ_STREAM  # parked
    assert bus.published[0][2] is None  # undecodable → parked unkeyed
    assert bus.acked == ["0:0"]  # acked so it can't wedge the partition


async def test_handle_entry_quarantine_deadletters_and_acks() -> None:
    async def _quarantine(_append: LedgerAppend) -> None:
        raise FillQuarantineError("no open lots to cover the sell")

    bus = _FakeBus()
    await handle_ledger_entry(cast(EventBus, bus), _quarantine, "0:0", _raw_fill(side="sell"))
    assert bus.published[0][0] == LEDGER_FILLS_DLQ_STREAM  # parked, not lost
    assert bus.published[0][2] == ACCOUNT  # keyed by account for ordered replay
    assert bus.acked == ["0:0"]


async def test_routes_lifecycle_events() -> None:
    rec = _Recorder()
    verdict = await process_stream_entry(
        rec, _reservation(event_type="order_submitted", reserved="1000")
    )
    assert verdict == "ack"
    append = rec.appends[0]
    assert append.event_type == LedgerEventType.ORDER_SUBMITTED
    assert append.data["reserved"] == "1000"


async def test_reservation_and_fill_have_distinct_ids() -> None:
    rec = _Recorder()
    await process_stream_entry(rec, _reservation(event_type="order_submitted", reserved="1502.50"))
    await process_stream_entry(rec, _fill())
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
