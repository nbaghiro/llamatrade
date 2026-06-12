"""Fill-ingestion wiring tests — pure, no Redis/DB.

Covers the decode→translate→handler path (``dispatch_fill``). The DB persistence
(``persist_append`` → ``LedgerWriter``) is the thin IO shell, exercised by the
integration suite.
"""

import json
from uuid import UUID, uuid4

from llamatrade_db.models.ledger import LedgerEventType

from src.ledger.ingestion import LedgerAppend
from src.tasks.fill_ingestion import dispatch_fill

TENANT = str(uuid4())
ACCOUNT = str(uuid4())
SLEEVE = str(uuid4())


def _fill(**overrides) -> dict:
    fill = {
        "tenant_id": TENANT,
        "account_id": ACCOUNT,
        "sleeve_id": SLEEVE,
        "client_order_id": "co-123",
        "symbol": "AAPL",
        "side": "buy",
        "qty": "10",
        "price": "150.25",
    }
    fill.update(overrides)
    return fill


class _Recorder:
    def __init__(self) -> None:
        self.appends: list[LedgerAppend] = []

    async def __call__(self, append: LedgerAppend) -> None:
        self.appends.append(append)


async def test_dispatch_translates_and_drives_handler() -> None:
    rec = _Recorder()
    ok = await dispatch_fill(rec, json.dumps(_fill()))

    assert ok is True
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


async def test_dispatch_accepts_bytes_payload() -> None:
    rec = _Recorder()
    ok = await dispatch_fill(rec, json.dumps(_fill()).encode())
    assert ok is True
    assert len(rec.appends) == 1


async def test_dispatch_idempotency_id_is_deterministic() -> None:
    rec = _Recorder()
    await dispatch_fill(rec, json.dumps(_fill()))
    await dispatch_fill(rec, json.dumps(_fill()))
    # Same client_order_id → identical ledger event_id (writer dedups on it).
    assert rec.appends[0].event_id == rec.appends[1].event_id


async def test_dispatch_bad_json_is_swallowed() -> None:
    rec = _Recorder()
    ok = await dispatch_fill(rec, "{not json")
    assert ok is False
    assert rec.appends == []


async def test_dispatch_routes_reservation_events() -> None:
    rec = _Recorder()
    ok = await dispatch_fill(
        rec, json.dumps(_fill(event_type="order_submitted", reserved="1502.50"))
    )
    assert ok is True
    append = rec.appends[0]
    assert append.event_type == LedgerEventType.ORDER_SUBMITTED
    assert append.data["reserved"] == "1502.50"
    # Reservation stage must not collide with the fill's idempotency key.
    await dispatch_fill(rec, json.dumps(_fill()))
    assert rec.appends[0].event_id != rec.appends[1].event_id


async def test_dispatch_unknown_event_type_is_swallowed() -> None:
    rec = _Recorder()
    ok = await dispatch_fill(rec, json.dumps(_fill(event_type="order_teleported")))
    assert ok is False
    assert rec.appends == []


async def test_dispatch_missing_required_field_is_swallowed() -> None:
    rec = _Recorder()
    fill = _fill()
    del fill["price"]
    ok = await dispatch_fill(rec, json.dumps(fill))
    assert ok is False
    assert rec.appends == []


async def test_dispatch_handler_error_is_swallowed() -> None:
    async def boom(_append: LedgerAppend) -> None:
        raise RuntimeError("handler down")

    ok = await dispatch_fill(boom, json.dumps(_fill()))
    assert ok is False
