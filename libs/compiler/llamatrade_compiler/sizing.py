"""Turn target weights into intended orders — the single sizing implementation.

This consolidates the two divergent copies that used to live in the backtest adapter
(always drift-resized) and the live adapter (binary unless ``sleeve_aware``). Now both
paths call :func:`size_orders` with a :class:`SizingMode`, so live and backtest size
positions identically.

The sizing is path-dependent (it reads current holdings and equity), so it is applied
per evaluation against the live/simulated portfolio state — it is *not* part of the pure
weight computation in :class:`CompiledStrategy`.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum

# Defaults mirror the previous adapters: 0.1 pp minimum weight change to open/close,
# 0.05 (5%) drift band before a resize trade is worth doing.
DEFAULT_MIN_WEIGHT_CHANGE = 0.1
DEFAULT_DRIFT_TOLERANCE = 0.05


class SizingMode(StrEnum):
    """How target weights become orders.

    - ``BINARY``: all-or-nothing — open when target > 0 and flat, close when target == 0
      and held. Weight changes (e.g. 60% -> 40%) do *not* resize. (Legacy live default.)
    - ``DRIFT``: trade the delta between target value and current value, skipping changes
      inside the drift band. Expresses resizes. (Backtest default and the sleeve-aware
      live default.)
    """

    BINARY = "binary"
    DRIFT = "drift"


@dataclass(frozen=True)
class Holding:
    """A currently-held position, as seen by the sizer."""

    symbol: str
    quantity: float


@dataclass(frozen=True)
class IntendedOrder:
    """An order the strategy wants to place this rebalance (before risk/execution)."""

    symbol: str
    side: str  # "buy" | "sell"
    quantity: float
    price: float  # reference price used for sizing (the bar close)


def size_orders(
    target_weights: Mapping[str, float],
    holdings: Mapping[str, Holding],
    prices: Mapping[str, float],
    equity: float,
    *,
    mode: SizingMode = SizingMode.DRIFT,
    drift_tolerance: float = DEFAULT_DRIFT_TOLERANCE,
    min_weight_change: float = DEFAULT_MIN_WEIGHT_CHANGE,
    current_weights: Mapping[str, float] | None = None,
) -> list[IntendedOrder]:
    """Diff target weights against current holdings → intended orders.

    Args:
        target_weights: desired allocation, percent (0-100) per symbol.
        holdings: current positions keyed by symbol.
        prices: reference price per symbol (bar close); symbols without a price are skipped.
        equity: total portfolio (or sleeve) equity to size against.
        mode: BINARY or DRIFT (see :class:`SizingMode`).
        drift_tolerance: DRIFT mode — skip resizes within this fraction of target value.
        min_weight_change: skip a symbol whose weight barely moved and whose held/flat
            state already matches the target (avoids no-op churn).
        current_weights: optional previous weights, used only for the ``min_weight_change``
            churn guard. When omitted, the guard is derived from held/flat state alone.

    Returns:
        Intended orders for every symbol whose holding must change. Considers the union of
        target and held symbols, so a symbol dropped to weight 0 is closed.
    """
    orders: list[IntendedOrder] = []
    symbols = set(target_weights) | set(holdings)

    for symbol in sorted(symbols):
        price = prices.get(symbol, 0.0)
        if price <= 0:
            continue

        target_weight = float(target_weights.get(symbol, 0.0))
        held_qty = holdings[symbol].quantity if symbol in holdings else 0.0
        has_position = held_qty > 0

        # Churn guard: weight essentially unchanged and held/flat already matches target.
        prev_weight = (current_weights or {}).get(symbol)
        if prev_weight is not None:
            if abs(target_weight - prev_weight) < min_weight_change and has_position == (
                target_weight > 0
            ):
                continue

        order = _size_one(symbol, target_weight, held_qty, price, equity, mode, drift_tolerance)
        if order is not None:
            orders.append(order)

    return orders


def _size_one(
    symbol: str,
    target_weight: float,
    held_qty: float,
    price: float,
    equity: float,
    mode: SizingMode,
    drift_tolerance: float,
) -> IntendedOrder | None:
    has_position = held_qty > 0

    if mode is SizingMode.BINARY:
        if target_weight > 0 and not has_position:
            qty = (equity * (target_weight / 100.0)) / price
            return _buy(symbol, qty, price)
        if target_weight == 0 and has_position:
            return _sell(symbol, held_qty, price)
        return None

    # DRIFT mode: trade the value delta, skipping changes within the drift band.
    target_value = equity * (target_weight / 100.0)
    current_value = held_qty * price
    delta_value = target_value - current_value

    if target_value > 0 and abs(delta_value) / target_value <= drift_tolerance:
        return None

    if delta_value > 0:
        return _buy(symbol, delta_value / price, price)

    # Reduce or close — never sell more than held.
    qty = min(-delta_value / price, held_qty)
    return _sell(symbol, qty, price)


def _buy(symbol: str, quantity: float, price: float) -> IntendedOrder | None:
    if quantity <= 0:
        return None
    return IntendedOrder(symbol=symbol, side="buy", quantity=quantity, price=price)


def _sell(symbol: str, quantity: float, price: float) -> IntendedOrder | None:
    if quantity <= 0:
        return None
    return IntendedOrder(symbol=symbol, side="sell", quantity=quantity, price=price)
