"""Projections derived by folding the append-only ledger.

The ledger event log is the single source of truth; sleeve cash, positions, and
realized P&L are *derived* by folding postings — never mutated independently.
Folding also asserts the conservation invariant on every event, so any
imbalance surfaces immediately.

These are pure functions over an event stream (no DB/IO), so they are cheap to
unit-test and can rebuild any sleeve's state from the log.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Protocol

from llamatrade_db.models.ledger import LedgerEventType

from src.ledger.postings import Bucket, assert_balanced, build_postings
from src.ledger.sizing import Lot, select_lots_fifo

logger = logging.getLogger(__name__)

ZERO = Decimal("0")

# Called when an event can't be applied during fold: (event_id, exception).
PoisonHandler = Callable[[str | None, Exception], None]


class LedgerEventLike(Protocol):
    """Minimal shape needed to fold an event (DB row or plain object).

    Read-only properties so ORM rows (``Mapped[str]`` descriptors) and plain
    dataclasses both satisfy the protocol without invariance issues.
    """

    @property
    def event_type(self) -> str | LedgerEventType: ...

    @property
    def data(self) -> dict[str, Any]: ...


@dataclass
class PositionState:
    """A sleeve's holding in one symbol (derived)."""

    qty: Decimal = ZERO
    cost_basis: Decimal = ZERO  # total cost of the remaining qty


@dataclass
class SleeveProjection:
    """Derived state of a single sleeve."""

    cash: Decimal = ZERO
    realized_pnl: Decimal = ZERO
    # Cash earmarked for open buy orders (reservation lifecycle, §4).
    # Free cash = cash − reserved.
    reserved: Decimal = ZERO
    positions: dict[str, PositionState] = field(default_factory=dict)


@dataclass
class AccountProjection:
    """Derived state of an account (all its sleeves)."""

    sleeves: dict[str, SleeveProjection] = field(default_factory=dict)

    def sleeve(self, sleeve_id: str) -> SleeveProjection:
        return self.sleeves.setdefault(sleeve_id, SleeveProjection())

    def total_cash(self) -> Decimal:
        return sum((s.cash for s in self.sleeves.values()), ZERO)

    def account_positions(self) -> dict[str, Decimal]:
        """Aggregate share quantity per symbol across all sleeves (vs. broker)."""
        totals: dict[str, Decimal] = {}
        for sleeve in self.sleeves.values():
            for symbol, pos in sleeve.positions.items():
                totals[symbol] = totals.get(symbol, ZERO) + pos.qty
        return {sym: qty for sym, qty in totals.items() if qty != ZERO}


def _coerce(event_type: str | LedgerEventType) -> LedgerEventType:
    return event_type if isinstance(event_type, LedgerEventType) else LedgerEventType(event_type)


def fold(
    events: Iterable[LedgerEventLike], *, on_error: PoisonHandler | None = None
) -> AccountProjection:
    """Fold a chronological event stream into an :class:`AccountProjection`.

    Each event is applied in isolation: an event whose data can't be parsed or
    balanced (a "poison" event — corrupt payload, missing key, conservation
    violation) is logged and SKIPPED rather than aborting the whole account, so
    one bad event can never make an account's portfolio unreadable. ``on_error``
    (when wired) is called with the offending ``event_id`` for metrics/alerting.
    Postings are validated BEFORE any state mutation, so a skipped event leaves
    the projection untouched.
    """
    acc = AccountProjection()
    # Open cash reservations: client_order_id -> (sleeve_id, amount)
    pending_reservations: dict[str, tuple[str, Decimal]] = {}
    _fold_into(acc, pending_reservations, events, on_error=on_error)
    return acc


def _fold_into(
    acc: AccountProjection,
    pending: dict[str, tuple[str, Decimal]],
    events: Iterable[LedgerEventLike],
    *,
    on_error: PoisonHandler | None = None,
) -> int:
    """Apply ``events`` onto an existing projection + reservation map IN PLACE.

    Shared by the full :func:`fold` and the incremental (checkpoint + delta) path
    in :class:`LedgerProjector`, so a fold resumed from a checkpoint is IDENTICAL
    to a fold from zero by construction (the per-event logic lives here, once).
    Returns the highest event ``sequence`` seen (0 if none carry one) — the
    projector uses it to advance its checkpoint.
    """
    max_sequence = 0
    for ev in events:
        seq = getattr(ev, "sequence", None)
        if seq is not None:
            try:
                max_sequence = max(max_sequence, int(seq))
            except TypeError, ValueError:
                pass
        try:
            event_type = _coerce(ev.event_type)
            postings = build_postings(event_type, ev.data)
            if postings:
                assert_balanced(postings)  # conservation checksum — fail before mutating
            # Reservation lifecycle (no postings of its own); applied only once
            # the economic postings above have validated.
            _apply_reservation(acc, pending, event_type, ev.data)
            for p in postings:
                if p.sleeve_id is None:
                    continue  # EXTERNAL — account boundary, not a sleeve balance
                sleeve = acc.sleeve(p.sleeve_id)
                if p.bucket is Bucket.CASH:
                    sleeve.cash += p.amount
                elif p.bucket is Bucket.PNL:
                    sleeve.realized_pnl += -p.amount
                elif p.bucket is Bucket.POSITION and p.symbol is not None:
                    pos = sleeve.positions.setdefault(p.symbol, PositionState())
                    pos.cost_basis += p.amount
                    if p.qty is not None:
                        pos.qty += p.qty
        except (KeyError, TypeError, ValueError, ArithmeticError) as exc:
            event_id = getattr(ev, "event_id", None)
            eid = str(event_id) if event_id is not None else None
            logger.warning("skipping poison ledger event %s during fold: %s", eid, exc)
            if on_error is not None:
                on_error(eid, exc)
    return max_sequence


# Terminal order events that release an open cash reservation.
_RESERVATION_RELEASES = {
    LedgerEventType.ORDER_FILLED,
    LedgerEventType.ORDER_CANCELLED,
    LedgerEventType.ORDER_REJECTED,
}


def _apply_reservation(
    acc: AccountProjection,
    pending: dict[str, tuple[str, Decimal]],
    event_type: LedgerEventType,
    data: dict[str, Any],
) -> None:
    """Track the §4 cash-reservation lifecycle (reserve → release/consume).

    ``reserved`` is derived state, not a posting bucket — reservations don't
    move value, they only earmark it, so conservation is untouched.
    """
    client_order_id = data.get("client_order_id")
    if client_order_id is None:
        return

    if event_type is LedgerEventType.ORDER_SUBMITTED and "reserved" in data:
        sleeve_id = data.get("sleeve_id")
        if sleeve_id is None:
            return
        amount = Decimal(str(data["reserved"]))
        acc.sleeve(str(sleeve_id)).reserved += amount
        pending[str(client_order_id)] = (str(sleeve_id), amount)
    elif event_type in _RESERVATION_RELEASES:
        entry = pending.pop(str(client_order_id), None)
        if entry is not None:
            acc.sleeve(entry[0]).reserved -= entry[1]


def open_lots(events: Iterable[LedgerEventLike], sleeve_id: str, symbol: str) -> list[Lot]:
    """Fold the event stream into the open FIFO lots of one (sleeve, symbol).

    Buys (positive POSITION postings) open lots in event order; sells consume
    them FIFO. Used at fill ingestion to resolve the cost basis of a sell when
    the publisher didn't supply one — the resolved value is then written into
    the event data, so the log stays self-contained and replayable.

    A sell exceeding the open lots (abnormal: drift, external trades) clears
    them all rather than raising — reconciliation surfaces the discrepancy.
    """
    lots: list[Lot] = []
    for index, ev in enumerate(events):
        postings = build_postings(_coerce(ev.event_type), ev.data)
        for p in postings:
            if (
                p.bucket is not Bucket.POSITION
                or p.sleeve_id != sleeve_id
                or p.symbol != symbol
                or p.qty is None
                or p.qty == ZERO
            ):
                continue
            if p.qty > ZERO:
                seq = getattr(ev, "sequence", None)
                lots.append(
                    Lot(
                        qty=p.qty, cost_basis=p.amount, opened_seq=seq if seq is not None else index
                    )
                )
            else:
                sell_qty = -p.qty
                if sell_qty >= sum((lot.qty for lot in lots), ZERO):
                    lots = []
                else:
                    lots = select_lots_fifo(lots, sell_qty).remaining_lots
    return lots


@dataclass
class HoldingHistoryEntry:
    """One provenance-bearing line in a symbol's trade history."""

    sleeve_id: str
    side: str  # "buy" | "sell"
    qty: Decimal  # absolute
    price: Decimal | None
    realized_pnl: Decimal | None
    occurred_at: Any | None


def holding_history(events: Iterable[LedgerEventLike], symbol: str) -> list[HoldingHistoryEntry]:
    """Per-symbol trade timeline with sleeve provenance (the user-facing view)."""
    out: list[HoldingHistoryEntry] = []
    for ev in events:
        postings = build_postings(_coerce(ev.event_type), ev.data)
        for p in postings:
            if p.bucket is not Bucket.POSITION or p.symbol != symbol or p.qty is None:
                continue
            if p.sleeve_id is None:
                continue
            data = ev.data
            price = Decimal(str(data["price"])) if "price" in data else None
            realized = Decimal(str(data["realized_pnl"])) if "realized_pnl" in data else None
            out.append(
                HoldingHistoryEntry(
                    sleeve_id=p.sleeve_id,
                    side="buy" if p.qty > ZERO else "sell",
                    qty=abs(p.qty),
                    price=price,
                    realized_pnl=realized,
                    occurred_at=getattr(ev, "occurred_at", None),
                )
            )
    return out
