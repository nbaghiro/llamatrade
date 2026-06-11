"""Backfill planner: seed the ledger from an account's pre-existing broker state.

When an account is first onboarded, its current broker cash and holdings must
enter the ledger so the invariant ``Σ sleeves == broker`` holds from day one.
Pre-existing positions land in the **Unmanaged** sleeve (a strategy can't adopt
them); free cash lands in **Unallocated**.

This is a pure planner: it returns the ordered events to append (resolved to
real sleeve ids by the caller, which also makes the append idempotent so the
backfill can be safely re-run).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from llamatrade_db.models.ledger import LedgerEventType

ZERO = Decimal("0")


@dataclass(frozen=True)
class BrokerPosition:
    """A pre-existing broker holding to import."""

    symbol: str
    qty: Decimal
    avg_price: Decimal


@dataclass(frozen=True)
class PlannedEvent:
    """An event to append during backfill (sleeve already resolved)."""

    event_type: LedgerEventType
    sleeve_id: UUID
    data: dict[str, str]
    # Stable idempotency suffix so re-running the backfill is a no-op.
    dedup_key: str


def plan_backfill(
    *,
    broker_cash: Decimal,
    broker_positions: list[BrokerPosition],
    unallocated_sleeve_id: UUID,
    unmanaged_sleeve_id: UUID,
) -> list[PlannedEvent]:
    """Produce the events that seed an account from current broker state."""
    planned: list[PlannedEvent] = []

    if broker_cash > ZERO:
        planned.append(
            PlannedEvent(
                event_type=LedgerEventType.FUNDS_DEPOSITED,
                sleeve_id=unallocated_sleeve_id,
                data={"sleeve_id": str(unallocated_sleeve_id), "amount": str(broker_cash)},
                dedup_key="backfill:cash",
            )
        )

    for pos in broker_positions:
        if pos.qty == ZERO:
            continue
        planned.append(
            PlannedEvent(
                event_type=LedgerEventType.EXTERNAL_TRADE_DETECTED,
                sleeve_id=unmanaged_sleeve_id,
                data={
                    "sleeve_id": str(unmanaged_sleeve_id),
                    "symbol": pos.symbol,
                    "qty": str(pos.qty),
                    "price": str(pos.avg_price),
                },
                dedup_key=f"backfill:pos:{pos.symbol}",
            )
        )

    return planned
