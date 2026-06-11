"""Block-and-allocate netting (Phase 5).

When multiple sleeves trade the same symbol in one cycle, bunch their intents
into a single net broker order instead of firing competing orders. Offsetting
intents (one sleeve buying while another sells) net down — the overlap is an
internal cross that never reaches the broker. Per-sleeve allocations are
preserved so fills can be attributed back at the average fill price.

Pure: computes the netting plan; the executor submits broker orders and applies
allocations as fills arrive.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from src.ledger.sizing import IntendedOrder

ZERO = Decimal("0")


@dataclass(frozen=True)
class BrokerOrder:
    """A net order actually sent to the broker."""

    symbol: str
    side: str  # "buy" | "sell"
    qty: Decimal


@dataclass(frozen=True)
class SleeveAllocation:
    """A sleeve's share of a symbol's flow (for attributing fills back)."""

    sleeve_id: str
    symbol: str
    side: str
    qty: Decimal


@dataclass(frozen=True)
class NettingResult:
    broker_orders: list[BrokerOrder]
    allocations: list[SleeveAllocation]


def net_orders(orders: list[IntendedOrder]) -> NettingResult:
    """Bunch same-symbol intents into net broker orders + per-sleeve allocations.

    A symbol whose buys and sells fully offset produces **no** broker order (it
    is internally crossed), yet both sleeves still receive their allocation.
    """
    allocations = [SleeveAllocation(o.sleeve_id, o.symbol, o.side, o.qty) for o in orders]

    signed: dict[str, Decimal] = {}
    for o in orders:
        delta = o.qty if o.side == "buy" else -o.qty
        signed[o.symbol] = signed.get(o.symbol, ZERO) + delta

    broker_orders: list[BrokerOrder] = []
    for symbol, net in sorted(signed.items()):
        if net == ZERO:
            continue  # fully internalized cross — nothing hits the broker
        broker_orders.append(BrokerOrder(symbol, "buy" if net > ZERO else "sell", abs(net)))
    return NettingResult(broker_orders=broker_orders, allocations=allocations)
