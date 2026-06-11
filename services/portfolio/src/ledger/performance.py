"""Per-sleeve performance & P&L (Phase 6), derived from the projection.

Realized P&L comes straight from the folded ledger; unrealized P&L and equity
are computed by marking the sleeve's open positions to current prices. Pure
over an :class:`AccountProjection` + a price map.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from src.ledger.projection import AccountProjection, SleeveProjection

ZERO = Decimal("0")


@dataclass(frozen=True)
class SleevePnL:
    """A sleeve's marked-to-market P&L snapshot."""

    sleeve_id: str
    cash: Decimal
    positions_value: Decimal
    equity: Decimal
    realized_pnl: Decimal
    unrealized_pnl: Decimal


def sleeve_pnl(sleeve_id: str, sleeve: SleeveProjection, prices: dict[str, Decimal]) -> SleevePnL:
    """Mark one sleeve to market. Positions without a price are valued at cost."""
    positions_value = ZERO
    unrealized = ZERO
    for symbol, pos in sleeve.positions.items():
        price = prices.get(symbol)
        market_value = pos.qty * price if price is not None else pos.cost_basis
        positions_value += market_value
        unrealized += market_value - pos.cost_basis
    return SleevePnL(
        sleeve_id=sleeve_id,
        cash=sleeve.cash,
        positions_value=positions_value,
        equity=sleeve.cash + positions_value,
        realized_pnl=sleeve.realized_pnl,
        unrealized_pnl=unrealized,
    )


def account_pnl(projection: AccountProjection, prices: dict[str, Decimal]) -> list[SleevePnL]:
    """Per-sleeve P&L for every sleeve in the account."""
    return [
        sleeve_pnl(sleeve_id, sleeve, prices)
        for sleeve_id, sleeve in sorted(projection.sleeves.items())
    ]
