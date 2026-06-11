"""Desired-state reconciliation (Phase 4): targets → intended orders.

Each sleeve declares *what its portfolio should be* (target weights); this folds
the per-sleeve desired state against current holdings into intended orders. It's
a pure function, so it is idempotent and self-healing — re-running with the same
state produces the same orders, and a missed cycle simply converges next time.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from src.ledger.sizing import (
    DEFAULT_DRIFT_TOLERANCE,
    IntendedOrder,
    fit_to_free_cash,
    target_orders,
)


@dataclass(frozen=True)
class SleeveDesired:
    """A sleeve's desired state plus the inputs needed to size against it."""

    sleeve_id: str
    equity: Decimal
    target_weights: dict[str, Decimal]
    current_positions: dict[str, Decimal]
    free_cash: Decimal
    target_weights_default: dict[str, Decimal] = field(default_factory=dict)


def plan_rebalance(
    desired: list[SleeveDesired],
    prices: dict[str, Decimal],
    *,
    drift_tolerance: Decimal = DEFAULT_DRIFT_TOLERANCE,
) -> dict[str, list[IntendedOrder]]:
    """Produce intended orders per sleeve to converge each toward its target.

    Buys are fit to the sleeve's free cash (sells, which raise cash, pass
    through). Sells are ordered before buys per sleeve so freed cash can fund
    buys downstream at execution time.
    """
    plan: dict[str, list[IntendedOrder]] = {}
    for d in desired:
        orders = target_orders(
            sleeve_id=d.sleeve_id,
            equity=d.equity,
            target_weights=d.target_weights,
            current_positions=d.current_positions,
            prices=prices,
            drift_tolerance=drift_tolerance,
        )
        sells = [o for o in orders if o.side == "sell"]
        buys: list[IntendedOrder] = []
        for o in orders:
            if o.side != "buy":
                continue
            fitted = fit_to_free_cash(o, d.free_cash)
            if fitted is not None:
                buys.append(fitted)
        plan[d.sleeve_id] = sells + buys
    return plan
