"""Fill-ingestion wiring tests — pure, no Redis/DB.

Covers the stream-entry path (``process_stream_entry``): translate a parsed proto
message → append, with ack/drop/retry verdicts. The DB persistence
(``persist_append`` → ``LedgerWriter``) is the thin IO shell, exercised by the
integration suite.
"""

from uuid import UUID, uuid4

from llamatrade_db.models.ledger import LedgerEventType
from llamatrade_events import LedgerFill, LedgerReservation

from src.ledger.ingestion import LedgerAppend
from src.tasks.fill_ingestion import process_stream_entry

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
        cash_balance=Decimal("0"),
        reserved_cash=Decimal("0"),
        unsettled_cash=Decimal("0"),
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
