"""Pure planners for sleeve lifecycle transitions.

Closing a sleeve re-homes its open positions to the account's **Unmanaged**
sleeve and its free cash to **Unallocated**, then retires the sleeve. These are
pure functions over already-projected state (no DB/IO), so the close payload is
unit-testable and the resulting ``SLEEVE_CLOSED`` event is self-contained — it
enumerates exactly what moved, so the log stays replayable (mirrors how
``enrich_sell_fill`` resolves a sell's cost basis into its event data).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

ZERO = Decimal("0")


class SleeveCloseError(ValueError):
    """Raised when a sleeve cannot be cleanly closed (e.g. in-flight orders)."""


@dataclass(frozen=True)
class RehomedPosition:
    """One open position moved out of a closing sleeve, at cost."""

    symbol: str
    qty: Decimal
    cost_basis: Decimal  # total cost of ``qty`` (carried across unchanged)


@dataclass(frozen=True)
class ClosePlan:
    """A planned close: the ``SLEEVE_CLOSED`` event payload + what it re-homes."""

    event_data: dict[str, object]
    positions: tuple[RehomedPosition, ...]
    cash: Decimal


def close_event_id(sleeve_id: UUID) -> UUID:
    """Deterministic event id so re-closing a sleeve never double-appends."""
    return UUID(bytes=hashlib.sha256(f"{sleeve_id}:close".encode()).digest()[:16])


def plan_sleeve_close(
    *,
    from_sleeve_id: UUID,
    positions: list[RehomedPosition],
    cash: Decimal,
    unmanaged_sleeve_id: UUID,
    unallocated_sleeve_id: UUID,
    reason: str | None = None,
) -> ClosePlan:
    """Plan re-homing a sleeve's holdings (positions → Unmanaged, cash →
    Unallocated) and retiring it.

    Zero-qty positions are dropped (nothing to move). An empty sleeve yields an
    event with no economic legs — a pure lifecycle marker. Decimals are stringified
    in the payload so the event is JSON-stable and exactly replayable.
    """
    nonzero = tuple(p for p in positions if p.qty != ZERO)
    event_data: dict[str, object] = {
        "sleeve_id": str(from_sleeve_id),
        "to_position_sleeve_id": str(unmanaged_sleeve_id),
        "to_cash_sleeve_id": str(unallocated_sleeve_id),
        "positions": [
            {"symbol": p.symbol, "qty": str(p.qty), "cost_basis": str(p.cost_basis)}
            for p in nonzero
        ],
        "cash": str(cash),
    }
    if reason:
        event_data["reason"] = reason
    return ClosePlan(event_data=event_data, positions=nonzero, cash=cash)
