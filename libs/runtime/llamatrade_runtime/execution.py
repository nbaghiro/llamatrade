"""Execution adapters — turn intended orders into fills against a portfolio.

``SimulatedExecution`` is the backtest fill engine (slippage + flat per-fill commission) — it
fills synchronously at the bar close. Live trading provides an Alpaca-backed adapter behind the
same async ``ExecutionAdapter`` seam, where ``execute`` submits an order and the fill arrives
later (delivered via the runtime's observer), so ``execute`` returns no inline fill.
"""

from datetime import datetime
from typing import Protocol

from llamatrade_runtime.models import ExecutionOutcome, RejectedSignal
from llamatrade_runtime.portfolio import Portfolio
from llamatrade_runtime.sizing import IntendedOrder
from llamatrade_runtime.types import Bar


class ExecutionAdapter(Protocol):
    """Applies an intended order to the book, and liquidates open positions at run end.

    Async so a live adapter can await a broker submit; backtest fills synchronously and returns
    the fill inline, live returns an accepted acknowledgement and fills later via the observer.
    """

    async def execute(
        self, order: IntendedOrder, bar: Bar, portfolio: Portfolio, date: datetime
    ) -> ExecutionOutcome: ...

    async def liquidate(self, portfolio: Portfolio, date: datetime) -> list[ExecutionOutcome]: ...


class SimulatedExecution:
    """Backtest fill engine: fills at the bar close (± slippage) with a flat per-fill fee."""

    def __init__(self, commission_rate: float = 0.0, slippage_rate: float = 0.0) -> None:
        self.commission_rate = commission_rate
        self.slippage_rate = slippage_rate

    async def execute(
        self, order: IntendedOrder, bar: Bar, portfolio: Portfolio, date: datetime
    ) -> ExecutionOutcome:
        price = bar.close
        if self.slippage_rate > 0:
            if order.side == "buy":
                price *= 1 + self.slippage_rate
            elif order.side == "sell":
                price *= 1 - self.slippage_rate

        if order.side == "buy":
            return portfolio.open(date, order.symbol, price, order.quantity, self.commission_rate)
        if order.side == "sell":
            quantity = order.quantity if order.quantity > 0 else None
            return portfolio.close(date, order.symbol, price, quantity, self.commission_rate)

        return ExecutionOutcome(
            rejected=RejectedSignal(
                date=date,
                symbol=order.symbol,
                signal_type=str(order.side),
                quantity=order.quantity,
                price=price,
                reason=f"Unsupported signal type: {order.side!r} (engine is long-only)",
            )
        )

    async def liquidate(self, portfolio: Portfolio, date: datetime) -> list[ExecutionOutcome]:
        """Close every open position at its last known price (no slippage on liquidation)."""
        outcomes: list[ExecutionOutcome] = []
        for symbol in list(portfolio.positions.keys()):
            price = portfolio.last_price(symbol)
            if price:
                outcomes.append(portfolio.close(date, symbol, price, None, self.commission_rate))
            else:
                pos = portfolio.positions[symbol]
                outcomes.append(
                    ExecutionOutcome(
                        rejected=RejectedSignal(
                            date=date or pos.entry_date,
                            symbol=symbol,
                            signal_type="close",
                            quantity=pos.quantity,
                            price=0.0,
                            reason="Could not close position at end of run: no last price available",
                        )
                    )
                )
        return outcomes
