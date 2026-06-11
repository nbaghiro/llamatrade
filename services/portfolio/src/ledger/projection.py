"""Projections derived by folding the append-only ledger.

The ledger event log is the single source of truth; sleeve cash, positions, and
realized P&L are *derived* by folding postings — never mutated independently.
Folding also asserts the conservation invariant on every event, so any
imbalance surfaces immediately.

These are pure functions over an event stream (no DB/IO), so they are cheap to
unit-test and can rebuild any sleeve's state from the log.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Protocol

from llamatrade_db.models.ledger import LedgerEventType

from src.ledger.postings import Bucket, assert_balanced, build_postings

ZERO = Decimal("0")


class LedgerEventLike(Protocol):
    """Minimal shape needed to fold an event (DB row or plain object)."""

    event_type: str | LedgerEventType
    data: dict[str, Any]


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


def fold(events: Iterable[LedgerEventLike]) -> AccountProjection:
    """Fold a chronological event stream into an :class:`AccountProjection`.

    Raises ``UnbalancedEventError`` if any event violates conservation.
    """
    acc = AccountProjection()
    for ev in events:
        postings = build_postings(_coerce(ev.event_type), ev.data)
        if not postings:
            continue
        assert_balanced(postings)
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
    return acc


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
