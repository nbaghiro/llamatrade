"""Sleeve-aware sizing (Phase 3): target weights → intended orders.

Pure helpers the execution layer calls instead of the legacy account-equity
sizing. Key properties:

- size against **sleeve equity**, never the whole account (the multi-strategy
  double-counting fix);
- **drift tolerance** — only trade when a holding has drifted past a band
  (replaces the binary all-or-nothing signal logic);
- **FIFO lot selection** for sells, so a sleeve only ever sells its own lots and
  realizes P&L against its own cost basis;
- **free-cash fit** — scale a buy down to the sleeve's free cash rather than
  overdraw.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

ZERO = Decimal("0")
DEFAULT_DRIFT_TOLERANCE = Decimal("0.05")  # 5%
_QTY = Decimal("0.00000001")


@dataclass(frozen=True)
class IntendedOrder:
    """A desired trade for one sleeve (pre-netting, pre-submission)."""

    sleeve_id: str
    symbol: str
    side: str  # "buy" | "sell"
    qty: Decimal
    est_price: Decimal


def sleeve_equity(
    cash: Decimal, positions: dict[str, Decimal], prices: dict[str, Decimal]
) -> Decimal:
    """A sleeve's equity = cash + Σ(position qty × current price)."""
    value = cash
    for symbol, qty in positions.items():
        price = prices.get(symbol)
        if price is not None:
            value += qty * price
    return value


def target_orders(
    *,
    sleeve_id: str,
    equity: Decimal,
    target_weights: dict[str, Decimal],
    current_positions: dict[str, Decimal],
    prices: dict[str, Decimal],
    drift_tolerance: Decimal = DEFAULT_DRIFT_TOLERANCE,
) -> list[IntendedOrder]:
    """Compute the delta orders to move a sleeve toward its target weights.

    ``target_weights`` are percentages of *sleeve equity*. Symbols held but not
    in the target get a full exit. Trades within ``drift_tolerance`` of target
    are skipped to avoid churn.
    """
    orders: list[IntendedOrder] = []
    symbols = set(target_weights) | set(current_positions)

    for symbol in sorted(symbols):
        price = prices.get(symbol)
        if price is None or price <= ZERO:
            continue
        weight = target_weights.get(symbol, ZERO)
        cur_qty = current_positions.get(symbol, ZERO)

        # Full exit: no longer targeted but still held.
        if weight <= ZERO:
            if cur_qty > ZERO:
                orders.append(IntendedOrder(sleeve_id, symbol, "sell", cur_qty, price))
            continue

        target_value = equity * weight / Decimal("100")
        target_qty = target_value / price
        delta_qty = target_qty - cur_qty
        if delta_qty == ZERO:
            continue

        # Drift band: skip small adjustments relative to target value.
        if target_value > ZERO:
            drift = abs(delta_qty * price) / target_value
            if drift < drift_tolerance:
                continue

        side = "buy" if delta_qty > ZERO else "sell"
        orders.append(IntendedOrder(sleeve_id, symbol, side, abs(delta_qty).quantize(_QTY), price))
    return orders


def fit_to_free_cash(order: IntendedOrder, free_cash: Decimal) -> IntendedOrder | None:
    """Scale a buy down to the sleeve's free cash; sells pass through.

    Returns the (possibly scaled) order, or ``None`` if the sleeve can't afford
    any of it.
    """
    if order.side != "buy":
        return order
    cost = order.qty * order.est_price
    if cost <= free_cash:
        return order
    if free_cash <= ZERO or order.est_price <= ZERO:
        return None
    affordable_qty = (free_cash / order.est_price).quantize(_QTY)
    if affordable_qty <= ZERO:
        return None
    return IntendedOrder(order.sleeve_id, order.symbol, "buy", affordable_qty, order.est_price)


@dataclass(frozen=True)
class Lot:
    """A lot available to sell (FIFO ordering by ``opened_seq``)."""

    qty: Decimal
    cost_basis: Decimal  # total cost of this lot's qty
    opened_seq: int


@dataclass(frozen=True)
class FifoResult:
    """Outcome of FIFO lot selection for a sell."""

    closed_cost_basis: Decimal
    consumed_qty: Decimal
    remaining_lots: list[Lot]


def select_lots_fifo(lots: list[Lot], sell_qty: Decimal) -> FifoResult:
    """Consume the oldest lots first to cover ``sell_qty``; compute closed cost.

    Returns the cost basis of the closed quantity (for realized-P&L) and the
    remaining open lots. Raises ``ValueError`` if the lots can't cover the sell.
    """
    if sell_qty <= ZERO:
        raise ValueError(f"sell_qty must be positive, got {sell_qty}")
    remaining = sell_qty
    closed_cost = ZERO
    out: list[Lot] = []
    for lot in sorted(lots, key=lambda lot: lot.opened_seq):
        if remaining <= ZERO:
            out.append(lot)
            continue
        if lot.qty <= remaining:
            closed_cost += lot.cost_basis
            remaining -= lot.qty
        else:
            unit_cost = lot.cost_basis / lot.qty
            closed_cost += unit_cost * remaining
            out.append(
                Lot(
                    qty=lot.qty - remaining,
                    cost_basis=lot.cost_basis - unit_cost * remaining,
                    opened_seq=lot.opened_seq,
                )
            )
            remaining = ZERO
    if remaining > ZERO:
        raise ValueError(f"insufficient lots: short {remaining} of {sell_qty}")
    return FifoResult(closed_cost_basis=closed_cost, consumed_qty=sell_qty, remaining_lots=out)
