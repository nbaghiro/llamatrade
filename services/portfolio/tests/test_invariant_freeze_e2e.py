"""Money-path ingestion proofs on the REAL ``persist_append`` stack, no Docker.

An in-memory ``AsyncSession`` double routes exactly the statements the fill
pipeline issues (sleeve lookups, the writer's ``ON CONFLICT`` insert with its
dedup fallback, the projector's ordered event read), so the real translation
(``append_from_message``), the real ``LedgerWriter``, the real fold, and the
real invariant-freeze guard all run unmocked. Covered here:

- negative-cash freeze end-to-end: fill → FROZEN sleeve + deterministic
  ``SLEEVE_FROZEN`` event + alert dispatch, idempotent on re-ingestion;
- dual-path delivery (stream-shape vs REST-shape fill for one order) folds to
  exactly one ledger row — the projection half of trading's
  ``test_dual_path_emission.py``;
- reservation releases (``order_rejected`` / ``order_cancelled``) return a
  sleeve's reserved cash to zero — the projection half of trading's
  ``test_reservation_release.py``.
"""

import hashlib
from collections.abc import Mapping
from datetime import UTC, datetime
from decimal import Decimal
from typing import cast
from uuid import UUID, uuid4

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import Insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Select

from llamatrade_db.models.ledger import (
    LedgerEvent,
    LedgerEventType,
    Sleeve,
    SleeveStatus,
    SleeveType,
)
from llamatrade_events import LedgerFill, LedgerReservation

import src.alerts as alerts_module
from src.alerts import LedgerIncident
from src.ledger.ingestion import append_from_message
from src.ledger.projection import AccountProjection, LedgerEventLike, fold
from src.ledger.writer import LedgerWriter
from src.tasks.fill_ingestion import persist_append

TENANT = uuid4()
ACCOUNT = uuid4()
D = Decimal


def _uuid(value: object) -> UUID:
    assert isinstance(value, UUID)
    return value


class _InsertResult:
    def __init__(self, row: LedgerEvent | None) -> None:
        self._row = row

    def scalars(self) -> _InsertResult:
        return self

    def first(self) -> LedgerEvent | None:
        return self._row


class FakeLedgerSession:
    """AsyncSession double for the exact statement shapes ``persist_append`` issues."""

    def __init__(self) -> None:
        self.events: list[LedgerEvent] = []
        self.sleeves: dict[UUID, Sleeve] = {}
        self.commits = 0
        self._seq = 0

    def add_sleeve(self, sleeve: Sleeve) -> None:
        self.sleeves[sleeve.id] = sleeve

    def _select_entity(self, stmt: Select[tuple[Sleeve]] | Select[tuple[LedgerEvent]]) -> object:
        entity: object = stmt.column_descriptions[0]["entity"]
        return entity

    def _param_uuids(self, stmt: Select[tuple[Sleeve]] | Select[tuple[LedgerEvent]]) -> set[UUID]:
        params: Mapping[str, object] = stmt.compile().params
        return {value for value in params.values() if isinstance(value, UUID)}

    async def scalar(
        self, stmt: Select[tuple[Sleeve]] | Select[tuple[LedgerEvent]]
    ) -> Sleeve | LedgerEvent | None:
        wanted = self._param_uuids(stmt)
        if self._select_entity(stmt) is Sleeve:
            return next((self.sleeves[sid] for sid in wanted if sid in self.sleeves), None)
        return next((e for e in self.events if e.event_id in wanted), None)

    async def scalars(self, stmt: Select[tuple[LedgerEvent]]) -> list[LedgerEvent]:
        return sorted(self.events, key=lambda e: e.sequence)

    async def execute(self, stmt: Insert) -> _InsertResult:
        params: Mapping[str, object] = stmt.compile(dialect=postgresql.dialect()).params
        event_id = _uuid(params["event_id"])
        if any(e.event_id == event_id for e in self.events):
            return _InsertResult(None)  # ON CONFLICT (event_id) DO NOTHING
        sleeve_id = params.get("sleeve_id")
        occurred_at = params.get("occurred_at")
        event_type = params["event_type"]
        data = params["data"]
        assert isinstance(event_type, str)
        assert isinstance(data, dict)
        event = LedgerEvent(
            event_id=event_id,
            tenant_id=_uuid(params["tenant_id"]),
            account_id=_uuid(params["account_id"]),
            sleeve_id=_uuid(sleeve_id) if isinstance(sleeve_id, UUID) else None,
            event_type=event_type,
            data=data,
            occurred_at=occurred_at if isinstance(occurred_at, datetime) else datetime.now(UTC),
        )
        self._seq += 1
        event.sequence = self._seq
        self.events.append(event)
        return _InsertResult(event)

    async def flush(self) -> None:
        return None

    async def commit(self) -> None:
        self.commits += 1

    def typed(self) -> AsyncSession:
        return cast(AsyncSession, self)


class _RecordingDispatcher:
    def __init__(self) -> None:
        self.incidents: list[tuple[UUID, LedgerIncident]] = []

    async def dispatch(self, tenant_id: UUID, incident: LedgerIncident) -> None:
        self.incidents.append((tenant_id, incident))


def _sleeve(status: SleeveStatus = SleeveStatus.ACTIVE) -> Sleeve:
    sleeve = Sleeve(
        tenant_id=TENANT,
        account_id=ACCOUNT,
        type=SleeveType.STRATEGY.value,
        status=status.value,
        name="Strategy A",
        strategy_execution_id=uuid4(),
        allocated_capital=D("0"),
    )
    sleeve.id = uuid4()
    return sleeve


async def _fund(db: FakeLedgerSession, sleeve_id: UUID, amount: str) -> None:
    """Fund through the real writer so the fold sees a balanced deposit."""
    await LedgerWriter(db.typed()).append(
        tenant_id=TENANT,
        account_id=ACCOUNT,
        event_type=LedgerEventType.FUNDS_DEPOSITED,
        data={"sleeve_id": str(sleeve_id), "amount": amount},
        sleeve_id=sleeve_id,
    )


def _fill(
    sleeve_id: UUID,
    *,
    client_order_id: str,
    qty: str,
    price: str,
    side: str = "buy",
    order_id: str = "",
    filled_at: str = "2026-07-20T14:30:00+00:00",
) -> LedgerFill:
    fill = LedgerFill(
        tenant_id=str(TENANT),
        account_id=str(ACCOUNT),
        sleeve_id=str(sleeve_id),
        client_order_id=client_order_id,
        symbol="SPY",
        side=side,
        qty=qty,
        price=price,
        filled_at=filled_at,
    )
    if order_id:
        fill.order_id = order_id
    return fill


def _reservation(
    sleeve_id: UUID,
    *,
    event_type: str,
    client_order_id: str,
    reserved: str = "",
) -> LedgerReservation:
    reservation = LedgerReservation(
        event_type=event_type,
        tenant_id=str(TENANT),
        account_id=str(ACCOUNT),
        sleeve_id=str(sleeve_id),
        client_order_id=client_order_id,
        symbol="SPY",
        side="buy",
    )
    if reserved:
        reservation.reserved = reserved
    return reservation


def _project(db: FakeLedgerSession) -> AccountProjection:
    return fold(cast("list[LedgerEventLike]", sorted(db.events, key=lambda e: e.sequence)))


def _events_of(db: FakeLedgerSession, event_type: LedgerEventType) -> list[LedgerEvent]:
    return [e for e in db.events if e.event_type == event_type.value]


@pytest.fixture
def dispatcher(monkeypatch: pytest.MonkeyPatch) -> _RecordingDispatcher:
    recorder = _RecordingDispatcher()
    monkeypatch.setattr(alerts_module, "get_ledger_alert_dispatcher", lambda: recorder)
    return recorder


class TestNegativeCashFreeze:
    """A fill overdrawing the sleeve freezes it — once, deterministically, loudly."""

    async def _overdraw(self, db: FakeLedgerSession, sleeve: Sleeve) -> UUID:
        """Fund $1000, ingest a $24000 buy; returns the fill's ledger event id."""
        await _fund(db, sleeve.id, "1000")
        message = _fill(sleeve.id, client_order_id="lt-freeze-1", qty="50", price="480")
        append = append_from_message(message)
        await persist_append(db.typed(), append)
        return append.event_id

    async def test_overdrawing_fill_freezes_the_sleeve(
        self, dispatcher: _RecordingDispatcher
    ) -> None:
        db = FakeLedgerSession()
        sleeve = _sleeve()
        db.add_sleeve(sleeve)

        await self._overdraw(db, sleeve)

        assert sleeve.status == SleeveStatus.FROZEN.value
        assert _project(db).sleeve(str(sleeve.id)).cash == D("-23000")
        assert db.commits == 1  # persisted in one transaction

    async def test_freeze_event_has_deterministic_id_derived_from_the_fill(
        self, dispatcher: _RecordingDispatcher
    ) -> None:
        db = FakeLedgerSession()
        sleeve = _sleeve()
        db.add_sleeve(sleeve)

        fill_event_id = await self._overdraw(db, sleeve)

        frozen = _events_of(db, LedgerEventType.SLEEVE_FROZEN)
        assert len(frozen) == 1
        expected = UUID(
            bytes=hashlib.sha256(f"{fill_event_id}:invariant_freeze".encode()).digest()[:16]
        )
        assert frozen[0].event_id == expected
        assert frozen[0].sleeve_id == sleeve.id
        assert "negative_cash" in str(frozen[0].data.get("reason"))

    async def test_reingesting_the_same_fill_does_not_double_freeze(
        self, dispatcher: _RecordingDispatcher
    ) -> None:
        db = FakeLedgerSession()
        sleeve = _sleeve()
        db.add_sleeve(sleeve)
        await self._overdraw(db, sleeve)

        message = _fill(sleeve.id, client_order_id="lt-freeze-1", qty="50", price="480")
        await persist_append(db.typed(), append_from_message(message))

        assert len(_events_of(db, LedgerEventType.ORDER_FILLED)) == 1  # writer dedup
        assert len(_events_of(db, LedgerEventType.SLEEVE_FROZEN)) == 1
        assert len(dispatcher.incidents) == 1
        assert sleeve.status == SleeveStatus.FROZEN.value

    async def test_freeze_dispatches_a_sleeve_frozen_alert(
        self, dispatcher: _RecordingDispatcher
    ) -> None:
        db = FakeLedgerSession()
        sleeve = _sleeve()
        db.add_sleeve(sleeve)

        await self._overdraw(db, sleeve)

        assert len(dispatcher.incidents) == 1
        tenant_id, incident = dispatcher.incidents[0]
        assert tenant_id == TENANT
        assert incident.kind == "sleeve_frozen"
        assert incident.context["sleeve_id"] == str(sleeve.id)
        assert incident.context["account_id"] == str(ACCOUNT)

    async def test_funded_fill_does_not_freeze(self, dispatcher: _RecordingDispatcher) -> None:
        db = FakeLedgerSession()
        sleeve = _sleeve()
        db.add_sleeve(sleeve)
        await _fund(db, sleeve.id, "40000")

        message = _fill(sleeve.id, client_order_id="lt-ok-1", qty="50", price="480")
        await persist_append(db.typed(), append_from_message(message))

        assert sleeve.status == SleeveStatus.ACTIVE.value
        assert _events_of(db, LedgerEventType.SLEEVE_FROZEN) == []
        assert dispatcher.incidents == []


class TestDualPathDeliveryFoldsOnce:
    """Stream-shape and REST-shape fills for one order → exactly one ledger row."""

    async def test_differing_payload_bytes_same_order_dedup_to_one_event(
        self, dispatcher: _RecordingDispatcher
    ) -> None:
        db = FakeLedgerSession()
        sleeve = _sleeve()
        db.add_sleeve(sleeve)
        await _fund(db, sleeve.id, "40000")

        stream_shape = _fill(sleeve.id, client_order_id="lt-dual-1", qty="50", price="480")
        rest_shape = _fill(
            sleeve.id,
            client_order_id="lt-dual-1",
            qty="50",
            price="480",
            order_id=str(uuid4()),
            filled_at="2026-07-20T14:30:02+00:00",
        )
        assert stream_shape.SerializeToString() != rest_shape.SerializeToString()

        first = append_from_message(stream_shape)
        second = append_from_message(rest_shape)
        assert first.event_id == second.event_id  # shared idempotency key

        await persist_append(db.typed(), first)
        await persist_append(db.typed(), second)

        assert len(_events_of(db, LedgerEventType.ORDER_FILLED)) == 1
        projected = _project(db).sleeve(str(sleeve.id))
        assert projected.positions["SPY"].qty == D("50")  # folded once, not twice
        assert projected.cash == D("16000")  # 40000 − 24000


class TestReservationReleaseFolds:
    """The trading-side release payloads fold reserved cash back to zero."""

    async def _reserve(self, db: FakeLedgerSession, sleeve: Sleeve, coid: str) -> None:
        await _fund(db, sleeve.id, "40000")
        submitted = _reservation(
            sleeve.id, event_type="order_submitted", client_order_id=coid, reserved="24000"
        )
        await persist_append(db.typed(), append_from_message(submitted))
        assert _project(db).sleeve(str(sleeve.id)).reserved == D("24000")

    @pytest.mark.parametrize("release_kind", ["order_rejected", "order_cancelled"])
    async def test_release_returns_reserved_to_zero(
        self, release_kind: str, dispatcher: _RecordingDispatcher
    ) -> None:
        db = FakeLedgerSession()
        sleeve = _sleeve()
        db.add_sleeve(sleeve)
        coid = f"lt-{release_kind}"
        await self._reserve(db, sleeve, coid)

        release = _reservation(sleeve.id, event_type=release_kind, client_order_id=coid)
        await persist_append(db.typed(), append_from_message(release))

        projected = _project(db).sleeve(str(sleeve.id))
        assert projected.reserved == D("0")
        assert projected.cash == D("40000")  # releases move no value

    async def test_release_is_idempotent_at_the_writer(
        self, dispatcher: _RecordingDispatcher
    ) -> None:
        db = FakeLedgerSession()
        sleeve = _sleeve()
        db.add_sleeve(sleeve)
        await self._reserve(db, sleeve, "lt-idem")

        release = _reservation(sleeve.id, event_type="order_rejected", client_order_id="lt-idem")
        await persist_append(db.typed(), append_from_message(release))
        await persist_append(db.typed(), append_from_message(release))

        assert len(_events_of(db, LedgerEventType.ORDER_REJECTED)) == 1
        assert _project(db).sleeve(str(sleeve.id)).reserved == D("0")
