"""Corporate-action planners: splits, ticker renames, dividends.

The broker reports a corporate action at the *account* grain (one split per
symbol, one dividend payment). The ledger must fan it out to **every sleeve**
holding the symbol so per-sleeve provenance and cost basis stay correct. These
are pure planners — they take the current per-sleeve holdings and return the
balanced events to append; the (deferred) corporate-actions ingestion feed reads
broker activity, projects holdings, and appends what these return.

Pure (no IO) so the share/cash math is unit-testable; conservation is enforced
when the events are folded by the projection kernel.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID

from llamatrade_db.models.ledger import LedgerEventType

ZERO = Decimal("0")
_CENTS = Decimal("0.01")


@dataclass(frozen=True)
class PlannedCorporateEvent:
    """A balanced ledger event to append for a corporate action."""

    event_type: LedgerEventType
    sleeve_id: UUID
    data: dict[str, str]
    dedup_key: str


def plan_split(
    *, symbol: str, ratio: Decimal, holders: dict[UUID, Decimal]
) -> list[PlannedCorporateEvent]:
    """Fan a stock split across every sleeve holding ``symbol``.

    ``ratio`` is new-shares-per-old (2 → 2-for-1 forward split; ``0.5`` → 1-for-2
    reverse split). Each holding sleeve gets a ``SPLIT_APPLIED`` event whose
    ``qty_delta = qty × (ratio − 1)`` (positive forward, negative reverse). Cost
    basis is preserved (zero-dollar leg). Sleeves with no position are skipped.
    """
    if ratio <= ZERO:
        raise ValueError(f"split ratio must be positive, got {ratio}")
    events: list[PlannedCorporateEvent] = []
    for sleeve_id, qty in holders.items():
        if qty == ZERO:
            continue
        qty_delta = qty * (ratio - Decimal("1"))
        if qty_delta == ZERO:
            continue
        events.append(
            PlannedCorporateEvent(
                event_type=LedgerEventType.SPLIT_APPLIED,
                sleeve_id=sleeve_id,
                data={
                    "sleeve_id": str(sleeve_id),
                    "symbol": symbol,
                    "qty_delta": str(qty_delta),
                },
                dedup_key=f"split:{symbol}:{ratio}:{sleeve_id}",
            )
        )
    return events


def plan_symbol_change(
    *, old_symbol: str, new_symbol: str, holders: dict[UUID, tuple[Decimal, Decimal]]
) -> list[PlannedCorporateEvent]:
    """Fan a ticker rename across every sleeve holding ``old_symbol``.

    ``holders`` maps sleeve -> ``(qty, cost_basis)``; each holding sleeve gets a
    ``SYMBOL_CHANGED`` event carrying qty + cost basis across to ``new_symbol``.
    """
    events: list[PlannedCorporateEvent] = []
    for sleeve_id, (qty, cost_basis) in holders.items():
        if qty == ZERO:
            continue
        events.append(
            PlannedCorporateEvent(
                event_type=LedgerEventType.SYMBOL_CHANGED,
                sleeve_id=sleeve_id,
                data={
                    "sleeve_id": str(sleeve_id),
                    "old_symbol": old_symbol,
                    "new_symbol": new_symbol,
                    "qty": str(qty),
                    "cost_basis": str(cost_basis),
                },
                dedup_key=f"rename:{old_symbol}:{new_symbol}:{sleeve_id}",
            )
        )
    return events


def split_dividend(
    *, symbol: str, total_amount: Decimal, holders: dict[UUID, Decimal], pay_id: str
) -> list[PlannedCorporateEvent]:
    """Split one broker dividend pro-rata by lot quantity across holding sleeves.

    Amounts are rounded to cents; the largest holder absorbs any rounding
    remainder so the per-sleeve amounts sum exactly to ``total_amount`` (cash
    conservation). Returns one ``DIVIDEND_RECEIVED`` event per holding sleeve.
    """
    if total_amount <= ZERO:
        raise ValueError(f"dividend amount must be positive, got {total_amount}")
    positive = {sid: qty for sid, qty in holders.items() if qty > ZERO}
    total_qty = sum(positive.values(), ZERO)
    if total_qty == ZERO:
        return []

    # Deterministic order: largest holder first (also the rounding sink).
    ordered = sorted(positive.items(), key=lambda kv: (kv[1], str(kv[0])), reverse=True)
    amounts: dict[UUID, Decimal] = {}
    allocated = ZERO
    for sleeve_id, qty in ordered[1:]:
        amt = (total_amount * qty / total_qty).quantize(_CENTS, rounding=ROUND_HALF_UP)
        amounts[sleeve_id] = amt
        allocated += amt
    # Largest holder takes the remainder so the split is exact.
    amounts[ordered[0][0]] = total_amount - allocated

    return [
        PlannedCorporateEvent(
            event_type=LedgerEventType.DIVIDEND_RECEIVED,
            sleeve_id=sleeve_id,
            data={"sleeve_id": str(sleeve_id), "amount": str(amount)},
            dedup_key=f"div:{symbol}:{pay_id}:{sleeve_id}",
        )
        for sleeve_id, amount in amounts.items()
    ]
