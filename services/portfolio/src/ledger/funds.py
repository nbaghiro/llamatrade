"""Fund disbursement: allocate / transfer / deposit / withdraw.

Pure planners that turn a requested capital operation into the balanced ledger
events to append, enforcing the cash invariants (you can't allocate or withdraw
more free cash than exists). Transfers from an illiquid sleeve produce a
**raise-cash** plan (sell the sleeve's own lots FIFO) that the caller executes
before the cash actually moves.

Pure (no IO) so the cash math is unit-testable; ``FundService`` is the thin
DB-backed wrapper that appends the planned events via the ledger writer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import ROUND_UP, Decimal
from uuid import UUID

from llamatrade_db.models.ledger import LedgerEventType

ZERO = Decimal("0")


class FundError(ValueError):
    """A capital operation that violates an invariant (e.g. insufficient cash)."""


@dataclass(frozen=True)
class PlannedFundEvent:
    """A balanced ledger event to append for a capital operation."""

    event_type: LedgerEventType
    data: dict[str, str]


@dataclass(frozen=True)
class RaiseCashSell:
    """A sell the source sleeve must execute to free cash for a transfer."""

    symbol: str
    qty: Decimal
    est_price: Decimal


@dataclass(frozen=True)
class TransferPlan:
    """A transfer plan: optional raise-cash sells, then the transfer event."""

    transfer: PlannedFundEvent
    raise_cash: list[RaiseCashSell] = field(default_factory=list)

    @property
    def needs_raise_cash(self) -> bool:
        return bool(self.raise_cash)


def _require_positive(amount: Decimal) -> None:
    if amount <= ZERO:
        raise FundError(f"amount must be positive, got {amount}")


def plan_deposit(*, unallocated_sleeve_id: UUID, amount: Decimal) -> list[PlannedFundEvent]:
    """Deposit external cash into the Unallocated sleeve."""
    _require_positive(amount)
    return [
        PlannedFundEvent(
            LedgerEventType.FUNDS_DEPOSITED,
            {"sleeve_id": str(unallocated_sleeve_id), "amount": str(amount)},
        )
    ]


def plan_withdraw(
    *, sleeve_id: UUID, amount: Decimal, free_cash: Decimal
) -> list[PlannedFundEvent]:
    """Withdraw external cash from a sleeve's free cash."""
    _require_positive(amount)
    if free_cash < amount:
        raise FundError(f"insufficient free cash: have {free_cash}, need {amount}")
    return [
        PlannedFundEvent(
            LedgerEventType.FUNDS_WITHDRAWN,
            {"sleeve_id": str(sleeve_id), "amount": str(amount)},
        )
    ]


def plan_allocate(
    *,
    from_sleeve_id: UUID,
    to_sleeve_id: UUID,
    amount: Decimal,
    from_free_cash: Decimal,
) -> list[PlannedFundEvent]:
    """Allocate cash from Unallocated (or any sleeve) into another sleeve."""
    _require_positive(amount)
    if from_free_cash < amount:
        raise FundError(f"insufficient free cash: have {from_free_cash}, need {amount}")
    return [
        PlannedFundEvent(
            LedgerEventType.CAPITAL_ALLOCATED,
            {
                "from_sleeve_id": str(from_sleeve_id),
                "to_sleeve_id": str(to_sleeve_id),
                "amount": str(amount),
            },
        )
    ]


def plan_transfer(
    *,
    from_sleeve_id: UUID,
    to_sleeve_id: UUID,
    amount: Decimal,
    from_free_cash: Decimal,
    from_positions: dict[str, tuple[Decimal, Decimal]] | None = None,
) -> TransferPlan:
    """Plan a sleeve→sleeve transfer, raising cash by selling lots if illiquid.

    ``from_positions`` maps symbol -> (qty, est_price); used only when the
    source sleeve lacks free cash. Raises :class:`FundError` if the transfer
    can't be funded even after liquidating all positions.
    """
    _require_positive(amount)
    transfer = PlannedFundEvent(
        LedgerEventType.CAPITAL_TRANSFERRED,
        {
            "from_sleeve_id": str(from_sleeve_id),
            "to_sleeve_id": str(to_sleeve_id),
            "amount": str(amount),
        },
    )
    if from_free_cash >= amount:
        return TransferPlan(transfer=transfer)

    shortfall = amount - from_free_cash
    sells = _raise_cash(from_positions or {}, shortfall)
    return TransferPlan(transfer=transfer, raise_cash=sells)


def _raise_cash(
    positions: dict[str, tuple[Decimal, Decimal]], shortfall: Decimal
) -> list[RaiseCashSell]:
    """Select sells (largest-value first) to cover a cash shortfall."""
    remaining = shortfall
    sells: list[RaiseCashSell] = []
    # Deterministic order: highest market value first.
    ordered = sorted(positions.items(), key=lambda kv: kv[1][0] * kv[1][1], reverse=True)
    for symbol, (qty, price) in ordered:
        if remaining <= ZERO:
            break
        if qty <= ZERO or price <= ZERO:
            continue
        value = qty * price
        if value <= remaining:
            sells.append(RaiseCashSell(symbol, qty, price))
            remaining -= value
        else:
            # Round qty UP so proceeds fully cover the remaining shortfall.
            need_qty = (remaining / price).quantize(Decimal("0.00000001"), rounding=ROUND_UP)
            sells.append(RaiseCashSell(symbol, need_qty, price))
            remaining = ZERO
    if remaining > ZERO:
        raise FundError(
            f"cannot raise {shortfall}: short by {remaining} after liquidating positions"
        )
    return sells


def check_admission(
    *,
    requested: Decimal,
    unallocated_free: Decimal,
    target_weights: dict[str, Decimal],
    min_notional: Decimal = Decimal("1"),
) -> list[str]:
    """Admission checks when funding a strategy sleeve. Returns violation strings.

    - **solvency:** requested ≤ Unallocated free cash
    - **feasibility:** each target asset's dollar slice ≥ a minimum tradable notional
    """
    violations: list[str] = []
    if requested <= ZERO:
        violations.append("requested capital must be positive")
    if requested > unallocated_free:
        violations.append(f"insufficient free cash: have {unallocated_free}, need {requested}")
    for symbol, weight in target_weights.items():
        slice_value = requested * weight / Decimal("100")
        if slice_value < min_notional:
            violations.append(f"{symbol}: slice {slice_value} below min notional {min_notional}")
    return violations
