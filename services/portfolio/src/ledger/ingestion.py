"""Fill ingestion: trading-service fills → ledger events.

The trading service is the execution arm; it emits exactly ONE ``OrderFilled``
event per order, at terminal state (tagged with the deterministic
``client_order_id`` that maps to a sleeve):

- on ``fill``: the cumulative ``filled_qty`` / ``filled_avg_price``;
- on ``canceled``/``expired`` with a nonzero filled quantity: the filled
  portion only.

Partial fills never publish — the ledger ``event_id`` is derived from
``client_order_id``, so per-partial publishing would dedup all but the first.

``cost_basis``/``realized_pnl`` on sells are OPTIONAL in the payload: when
absent (proto scalar left empty), the consumer handler computes them at
ingestion via FIFO lot selection against the account projection (the ledger
owns the lots; trading reports broker facts only).

Trading emits proto messages (``LedgerFill`` / ``LedgerReservation``, the §1/§4
contract); the translation (`fill_to_append` / `reservation_to_append`, routed by
`append_from_message`) is a pure function so it can be unit-tested. The portfolio
service drives it from the Redis Streams consumer group
(``src.tasks.fill_ingestion``).
"""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from llamatrade_db.models.ledger import LedgerEventType
from llamatrade_events import LedgerFill, LedgerReservation

from src.ledger.sizing import Lot, select_lots_fifo

logger = logging.getLogger(__name__)

# Non-fill order lifecycle stages trading publishes on the same stream
# (reservation addendum, CONTRACTS.md §4). Recorded for the reservation
# lifecycle; they carry no economic postings of their own.
LIFECYCLE_EVENT_TYPES: dict[str, LedgerEventType] = {
    "order_submitted": LedgerEventType.ORDER_SUBMITTED,
    "order_cancelled": LedgerEventType.ORDER_CANCELLED,
    "order_rejected": LedgerEventType.ORDER_REJECTED,
}


@dataclass(frozen=True)
class LedgerAppend:
    """Resolved arguments for :meth:`LedgerWriter.append` (pure translation result)."""

    tenant_id: UUID
    account_id: UUID
    sleeve_id: UUID
    event_type: LedgerEventType
    data: dict[str, Any]
    event_id: UUID
    occurred_at: datetime


def _require(value: str, name: str) -> str:
    """A required proto scalar must be non-empty; empty → poison (drop)."""
    if not value:
        raise ValueError(f"ledger payload missing required field: {name}")
    return value


def fill_to_append(fill: LedgerFill) -> LedgerAppend:
    """Translate a trading ``LedgerFill`` (§1) into a ledger append.

    Required: ``tenant_id``, ``account_id``, ``sleeve_id``, ``client_order_id``
    (idempotency key), ``symbol``, ``side`` (buy/sell), ``qty``, ``price``.
    Optional (proto scalar empty ⇒ absent): ``fees``, ``cost_basis`` (sells),
    ``realized_pnl`` (sells), ``order_id``, ``filled_at`` (ISO).

    ``qty``/``price`` are the order's terminal cumulative fill quantity and
    average fill price — one message per order, never per partial fill. When
    ``cost_basis`` is absent on a sell, the consumer computes it at ingestion
    (FIFO against the projection) before appending.

    Idempotency: the ledger ``event_id`` is derived from the broker
    ``client_order_id`` so a re-delivered fill is a no-op at the writer.
    """
    client_order_id = _require(fill.client_order_id, "client_order_id")
    data: dict[str, Any] = {
        "sleeve_id": _require(fill.sleeve_id, "sleeve_id"),
        "symbol": _require(fill.symbol, "symbol"),
        "side": _require(fill.side, "side").lower(),
        "qty": _require(fill.qty, "qty"),
        "price": _require(fill.price, "price"),
        # Carried in data so the fill releases its cash reservation (§4)
        "client_order_id": client_order_id,
    }
    # Proto3 can't distinguish unset from empty: an empty scalar means "absent",
    # so the FIFO-enrichment trigger (no cost_basis) is preserved.
    for name, value in (
        ("fees", fill.fees),
        ("cost_basis", fill.cost_basis),
        ("realized_pnl", fill.realized_pnl),
        ("order_id", fill.order_id),
    ):
        if value:
            data[name] = value

    return LedgerAppend(
        tenant_id=UUID(_require(fill.tenant_id, "tenant_id")),
        account_id=UUID(_require(fill.account_id, "account_id")),
        sleeve_id=UUID(data["sleeve_id"]),
        event_type=LedgerEventType.ORDER_FILLED,
        data=data,
        event_id=_event_id_from_client_order_id(client_order_id),
        occurred_at=_parse_ts(fill.filled_at),
    )


def reservation_to_append(reservation: LedgerReservation) -> LedgerAppend:
    """Translate a trading ``LedgerReservation`` (§4 lifecycle) into an append.

    ``order_submitted`` / ``order_cancelled`` / ``order_rejected`` carry no
    economic postings of their own; the ``event_id`` derives from
    ``client_order_id:stage`` so each stage is idempotent independently of the
    fill. Reservations carry no timestamp, so ``occurred_at`` is "now".
    """
    kind = _require(reservation.event_type, "event_type").lower()
    try:
        event_type = LIFECYCLE_EVENT_TYPES[kind]
    except KeyError:
        raise ValueError(f"unknown ledger reservation event_type: {kind!r}") from None

    client_order_id = _require(reservation.client_order_id, "client_order_id")
    data: dict[str, Any] = {
        "sleeve_id": _require(reservation.sleeve_id, "sleeve_id"),
        "client_order_id": client_order_id,
    }
    for name, value in (
        ("symbol", reservation.symbol),
        ("side", reservation.side),
        ("reserved", reservation.reserved),
        ("order_id", reservation.order_id),
    ):
        if value:
            data[name] = value

    return LedgerAppend(
        tenant_id=UUID(_require(reservation.tenant_id, "tenant_id")),
        account_id=UUID(_require(reservation.account_id, "account_id")),
        sleeve_id=UUID(data["sleeve_id"]),
        event_type=event_type,
        data=data,
        event_id=_event_id_from_client_order_id(f"{client_order_id}:{kind}"),
        occurred_at=_parse_ts(None),
    )


def append_from_message(message: LedgerFill | LedgerReservation) -> LedgerAppend:
    """Route a consumed ledger message to its append by proto type.

    ``LedgerReservation`` → a lifecycle stage; ``LedgerFill`` → a fill. The
    envelope's ``EventType`` already discriminated which message was parsed, so
    the type is authoritative (no string sniffing).
    """
    if isinstance(message, LedgerReservation):
        return reservation_to_append(message)
    return fill_to_append(message)


def needs_cost_basis(append: LedgerAppend) -> bool:
    """True for a sell fill whose publisher did not resolve a cost basis."""
    return (
        append.event_type is LedgerEventType.ORDER_FILLED
        and append.data.get("side") == "sell"
        and "cost_basis" not in append.data
    )


def enrich_sell_fill(append: LedgerAppend, lots: list[Lot]) -> LedgerAppend:
    """Resolve FIFO cost basis + realized P&L into a sell fill's event data.

    The consumer calls this at ingestion (the ledger owns the lots; trading
    only reports broker facts). If the open lots can't cover the sell, the
    fill is recorded unenriched (cost defaults to notional → zero P&L) and
    reconciliation surfaces the discrepancy.
    """
    if not needs_cost_basis(append):
        return append

    qty = Decimal(append.data["qty"])
    try:
        result = select_lots_fifo(lots, qty)
    except ValueError as e:
        logger.warning(
            "cannot resolve FIFO cost basis for sell (sleeve=%s symbol=%s qty=%s): %s",
            append.sleeve_id,
            append.data.get("symbol"),
            qty,
            e,
        )
        return append

    price = Decimal(append.data["price"])
    fees = Decimal(append.data["fees"]) if "fees" in append.data else Decimal("0")
    realized = qty * price - result.closed_cost_basis - fees

    data = dict(append.data)
    data["cost_basis"] = str(result.closed_cost_basis)
    data.setdefault("realized_pnl", str(realized))
    return replace(append, data=data)


def _parse_ts(raw: object) -> datetime:
    if isinstance(raw, str):
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            pass
    return datetime.now(UTC)


def _event_id_from_client_order_id(client_order_id: str) -> UUID:
    """Deterministic, idempotent ledger event id derived from the broker order id."""
    return UUID(bytes=hashlib.sha256(client_order_id.encode()).digest()[:16])


FillHandler = Callable[[LedgerAppend], Awaitable[None]]
