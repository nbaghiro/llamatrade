"""In-memory portfolio book — cash, positions, mark-to-market equity, fill accounting.

This is the backtest / simulated book of record. Live trading substitutes a ledger-backed
view behind the same ``holdings()`` / ``equity()`` surface the runtime reads.
"""

from collections.abc import Mapping
from datetime import datetime

from llamatrade_runtime.models import ExecutionOutcome, Fill, Position, RejectedSignal, Trade
from llamatrade_runtime.sizing import Holding, affordable_quantity


class Portfolio:
    """The in-memory book. Owns cash + open positions + the realized trade ledger."""

    def __init__(self, initial_capital: float) -> None:
        self.initial_capital = initial_capital
        self.cash = initial_capital
        self.positions: dict[str, Position] = {}
        self.trades: list[Trade] = []
        self._last_prices: dict[str, float] = {}

    def update_prices(self, prices: Mapping[str, float]) -> None:
        """Record the latest known price per symbol (for O(1) equity/liquidation)."""
        for symbol, price in prices.items():
            self._last_prices[symbol] = price

    def last_price(self, symbol: str) -> float | None:
        return self._last_prices.get(symbol)

    def equity(self) -> float:
        """Cash plus marked-to-market positions (at last known prices)."""
        equity = self.cash
        for symbol, pos in self.positions.items():
            price = self._last_prices.get(symbol, pos.entry_price)
            equity += pos.quantity * price
        return equity

    def holdings(self) -> dict[str, Holding]:
        """Current positions as compiler ``Holding``s (for the session sizer)."""
        return {s: Holding(s, p.quantity) for s, p in self.positions.items() if p.quantity > 0}

    def open(
        self, date: datetime, symbol: str, price: float, quantity: float, commission: float
    ) -> ExecutionOutcome:
        """Open or add to a long position, trimming the buy to what free cash affords after the fee."""
        fill_qty = affordable_quantity(quantity, price, self.cash, commission)
        if fill_qty <= 0:
            return ExecutionOutcome(
                rejected=RejectedSignal(
                    date=date,
                    symbol=symbol,
                    signal_type="buy",
                    quantity=quantity,
                    price=price,
                    reason=f"Insufficient cash: need ${price * quantity + commission:.2f}, "
                    f"have ${self.cash:.2f}",
                )
            )
        quantity = fill_qty
        cost = price * quantity

        self.cash -= cost + commission

        existing = self.positions.get(symbol)
        if existing is not None:
            # Add to position: cost-weighted average entry price.
            total_quantity = existing.quantity + quantity
            existing.entry_price = (
                existing.entry_price * existing.quantity + price * quantity
            ) / total_quantity
            existing.quantity = total_quantity
            existing.entry_commission_remaining += commission
        else:
            self.positions[symbol] = Position(
                symbol=symbol,
                side="long",
                entry_price=price,
                quantity=quantity,
                entry_date=date,
                entry_commission_remaining=commission,
            )

        return ExecutionOutcome(
            fill=Fill(
                date=date,
                symbol=symbol,
                side="buy",
                price=price,
                quantity=quantity,
                commission=commission,
            )
        )

    def close(
        self,
        date: datetime,
        symbol: str,
        price: float,
        quantity: float | None,
        commission: float,
    ) -> ExecutionOutcome:
        """Close all or part of a position. Rejects a sell with no open position."""
        pos = self.positions.get(symbol)
        if pos is None:
            return ExecutionOutcome(
                rejected=RejectedSignal(
                    date=date,
                    symbol=symbol,
                    signal_type="sell",
                    quantity=quantity or 0.0,
                    price=price,
                    reason="Sell signal for a symbol with no open position",
                )
            )

        sell_quantity = pos.quantity if quantity is None else min(quantity, pos.quantity)
        if sell_quantity <= 0:
            return ExecutionOutcome()

        # Apportion the position's entry commission to this exit by the quantity sold.
        if sell_quantity >= pos.quantity:
            entry_commission_alloc = pos.entry_commission_remaining
        else:
            entry_commission_alloc = pos.entry_commission_remaining * (sell_quantity / pos.quantity)

        trade = Trade(
            entry_date=pos.entry_date,
            exit_date=date,
            symbol=symbol,
            side=pos.side,
            entry_price=pos.entry_price,
            exit_price=price,
            quantity=sell_quantity,
            commission=entry_commission_alloc + commission,
        )
        self.trades.append(trade)
        # Only the exit commission hits cash; the entry commission was debited on open.
        self.cash += price * sell_quantity - commission

        if sell_quantity >= pos.quantity:
            del self.positions[symbol]
        else:
            pos.entry_commission_remaining -= entry_commission_alloc
            pos.quantity -= sell_quantity

        return ExecutionOutcome(
            fill=Fill(
                date=date,
                symbol=symbol,
                side="sell",
                price=price,
                quantity=sell_quantity,
                commission=commission,
            ),
            trade=trade,
        )
