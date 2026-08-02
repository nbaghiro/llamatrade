"""Turn target weights into intended orders — the single sizing implementation.

Live and backtest both call :func:`size_orders` with a :class:`SizingMode`, so they
size positions identically.

The sizing is path-dependent (it reads current holdings and equity), so it is applied
per evaluation against the live/simulated portfolio state — it is *not* part of the pure
weight computation in :class:`CompiledStrategy`.
"""

from __future__ import annotations

import logging
import math
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum

# 0.1 pp minimum weight change to open/close; 0.05 (5%) drift band before a resize is worth doing.
DEFAULT_MIN_WEIGHT_CHANGE = 0.1
DEFAULT_DRIFT_TOLERANCE = 0.05
# Alpaca rejects an order under $1 of notional; 0 disables the guard.
DEFAULT_MIN_ORDER_NOTIONAL = 1.0
# Alpaca accepts at most 9 decimal places on a fractional-share quantity.
DEFAULT_SHARE_DECIMALS = 9

logger = logging.getLogger(__name__)


def quantize_quantity(
    quantity: float, *, fractional: bool = True, decimals: int = DEFAULT_SHARE_DECIMALS
) -> float:
    """Round an order quantity DOWN to a tradable share increment.

    Fractional symbols round to ``decimals`` places (Alpaca rejects more than 9); whole-share
    symbols round to integer shares. Rounding down never overshoots the cash or holdings the
    quantity was sized against, and it makes a backtest fill the same quantity the broker would
    accept live rather than the raw many-decimal float the simulator otherwise fills.
    """
    if quantity <= 0:
        return 0.0
    if not fractional:
        return float(math.floor(quantity))
    scale = 10.0**decimals
    return math.floor(quantity * scale) / scale


@dataclass(frozen=True)
class ShareQuantization:
    """Share-increment rounding applied to the sizer's emitted quantities.

    A single setting for the batch; a per-asset fractionable lookup is a future refinement.
    """

    fractional: bool = True
    decimals: int = DEFAULT_SHARE_DECIMALS

    def apply(self, quantity: float) -> float:
        return quantize_quantity(quantity, fractional=self.fractional, decimals=self.decimals)


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


@dataclass
class SizingState:
    """Per-call sizing counters the caller folds into its own run totals.

    Mirrors ``EvaluationState.degraded_evaluations``: the sizer records here, the session
    accumulates and surfaces the run total (``StrategySession.sub_notional_skip_count``).
    """

    # Orders dropped under ``min_order_notional``, including buys the post-skip cash fit
    # leaves under it.
    sub_notional_skips: int = 0


def affordable_quantity(
    quantity: float, price: float, cash: float, commission: float = 0.0
) -> float:
    """The part of ``quantity`` that ``cash`` covers at ``price`` after ``commission``.

    Shared by the sizer's post-skip cash fit and the simulated book's fill trim, so a buy
    short of funding is reduced to what the cash affords rather than dropped whole.
    """
    if price <= 0:
        return 0.0
    return min(quantity, max((cash - commission) / price, 0.0))


def size_orders(
    target_weights: Mapping[str, float],
    holdings: Mapping[str, Holding],
    prices: Mapping[str, float],
    equity: float,
    *,
    mode: SizingMode = SizingMode.DRIFT,
    drift_tolerance: float = DEFAULT_DRIFT_TOLERANCE,
    min_weight_change: float = DEFAULT_MIN_WEIGHT_CHANGE,
    min_order_notional: float = DEFAULT_MIN_ORDER_NOTIONAL,
    current_weights: Mapping[str, float] | None = None,
    free_cash: float | None = None,
    quantization: ShareQuantization | None = None,
    state: SizingState | None = None,
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
        min_order_notional: drop orders worth less than this many dollars, which the broker
            would reject anyway; 0 disables the guard.
        current_weights: optional previous weights, used only for the ``min_weight_change``
            churn guard. When omitted, the guard is derived from held/flat state alone.
        free_cash: cash available before this rebalance. When provided, the buy side is fit
            to ``free_cash`` plus the proceeds of the sells that land, so the batch is
            affordable in both modes (a per-symbol drift band or a marked-up equity can
            otherwise emit buys the account cannot fund). When omitted, the buys are assumed
            to be funded exclusively by same-tick sells.
        quantization: when provided, round every emitted order DOWN to a tradable share
            increment (re-checking the notional floor after rounding) so backtest fills the
            same quantity the broker accepts live. When omitted, quantities are unrounded.
        state: optional counters the sizer records skips on for the caller to accumulate.

    Returns:
        Intended orders for every symbol whose holding must change, **sells before buys** so
        freed cash funds the buys within the same rebalance. Considers the union of target and
        held symbols, so a symbol dropped to weight 0 is closed.
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

    # Sells before buys so a rebalance frees cash (from closes/trims) before spending it.
    orders.sort(key=lambda o: (o.side != "sell", o.symbol))
    orders = _apply_notional_floor(orders, min_order_notional, free_cash, state)
    if quantization is not None:
        orders = _quantize_orders(orders, quantization, min_order_notional, state)
    return orders


def _notional(order: IntendedOrder) -> float:
    return order.quantity * order.price


def _record_sub_notional_skip(
    order: IntendedOrder, floor: float, state: SizingState | None
) -> None:
    """Record an order dropped for falling under the broker's minimum notional."""
    if state is not None:
        state.sub_notional_skips += 1
    logger.debug(
        "order below minimum notional (%s %s qty=%s @ %s = %s < %s); skipping",
        order.side,
        order.symbol,
        order.quantity,
        order.price,
        _notional(order),
        floor,
    )


def _apply_notional_floor(
    orders: list[IntendedOrder],
    floor: float,
    free_cash: float | None,
    state: SizingState | None,
) -> list[IntendedOrder]:
    """Drop orders under ``floor``, then fit the buys to the cash that funds them.

    With ``free_cash`` known, the buys are fit to ``free_cash`` plus the proceeds of the
    sells that land, so the batch is affordable regardless of the drift band or marked-up
    equity. Without it, the fit falls back to covering only a skipped-sell shortfall (buys
    assumed funded exclusively by same-tick sells). A skipped buy just leaves its cash unspent.
    """
    sells: list[IntendedOrder] = []
    buys: list[IntendedOrder] = []
    # The dropped-sell shortfall only funds the legacy (free_cash is None) budget, so it is
    # accumulated only on that path.
    track_shortfall = free_cash is None
    shortfall = 0.0

    for order in orders:
        if _notional(order) < floor:
            _record_sub_notional_skip(order, floor, state)
            if track_shortfall and order.side == "sell":
                shortfall += _notional(order)
            continue
        (buys if order.side == "buy" else sells).append(order)

    if free_cash is not None:
        budget = free_cash + sum(_notional(o) for o in sells)
        return sells + _fit_buys_to_budget(buys, budget, floor, state)

    if shortfall <= 0:
        return sells + buys

    budget = sum(_notional(o) for o in buys) - shortfall
    return sells + _fit_buys_to_budget(buys, budget, floor, state)


def _quantize_orders(
    orders: list[IntendedOrder],
    quantization: ShareQuantization,
    floor: float,
    state: SizingState | None,
) -> list[IntendedOrder]:
    """Round each order DOWN to a tradable share increment, then re-check the floor.

    Rounding down never overshoots what the order was sized against; an order that rounds to
    zero shares or below the notional floor is dropped and counted, mirroring the live path.
    """
    kept: list[IntendedOrder] = []
    for order in orders:
        quantity = quantization.apply(order.quantity)
        rounded = IntendedOrder(
            symbol=order.symbol, side=order.side, quantity=quantity, price=order.price
        )
        if quantity <= 0 or _notional(rounded) < floor:
            _record_sub_notional_skip(rounded, floor, state)
            continue
        kept.append(rounded)
    return kept


def _fit_buys_to_budget(
    buys: list[IntendedOrder], budget: float, floor: float, state: SizingState | None
) -> list[IntendedOrder]:
    """Scale buys to what ``budget`` affords, then drop any left under ``floor``.

    A shortfall trims every buy by the same fraction (``budget / total``) so their relative
    sizes (the target weights) are preserved, rather than fully funding the first buys in sort
    order and starving the rest.
    """
    total = sum(_notional(o) for o in buys)
    if total <= 0:
        return []
    scale = min(1.0, budget / total) if budget > 0 else 0.0

    fitted: list[IntendedOrder] = []
    for order in buys:
        quantity = order.quantity * scale
        trimmed = IntendedOrder(
            symbol=order.symbol, side="buy", quantity=quantity, price=order.price
        )
        if quantity <= 0 or _notional(trimmed) < floor:
            _record_sub_notional_skip(trimmed, floor, state)
            continue
        fitted.append(trimmed)
    return fitted


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
