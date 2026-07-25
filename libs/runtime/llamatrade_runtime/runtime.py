"""StrategyRuntime — the async loop that unifies backtest and live execution.

Drives one :class:`StrategySession` over a :class:`BarFeed`, applies its intended orders through
an :class:`ExecutionAdapter` against a :class:`Portfolio`, and emits every lifecycle event to a
:class:`RuntimeObserver`. Backtest and live share the per-tick core (:meth:`_evaluate_and_execute`)
and differ only at the ends:

- :meth:`run` — backtest: a bounded feed, liquidates open positions at the end, returns a
  ``RunResult``. ``execute`` fills synchronously and returns the fill inline.
- :meth:`stream` — live: an unbounded feed, never liquidates, no ``RunResult``. ``execute`` submits
  an order and returns "accepted"; the fill arrives out-of-band and is applied to the portfolio +
  emitted by the caller's fill loop.
"""

import asyncio
from collections.abc import Callable
from datetime import datetime

from llamatrade_runtime.execution import ExecutionAdapter
from llamatrade_runtime.feed import BarFeed
from llamatrade_runtime.models import ExecutionOutcome, RejectedSignal
from llamatrade_runtime.observer import NullObserver, RuntimeObserver
from llamatrade_runtime.portfolio import Portfolio
from llamatrade_runtime.result import RunResult, assemble_result
from llamatrade_runtime.session import StrategySession
from llamatrade_runtime.types import Bar


class RuntimeCancelled(Exception):  # domain signal, not an error
    """Raised when a run is cooperatively cancelled mid-loop."""


class StrategyRuntime:
    """Runs a strategy session over a feed, executing orders and tracking a portfolio."""

    def __init__(
        self,
        session: StrategySession,
        portfolio: Portfolio,
        execution: ExecutionAdapter,
        *,
        risk_free_rate: float = 0.02,
        observer: RuntimeObserver | None = None,
    ) -> None:
        self.session = session
        self.portfolio = portfolio
        self.execution = execution
        self.risk_free_rate = risk_free_rate
        self.observer: RuntimeObserver = observer or NullObserver()

    async def run(
        self,
        feed: BarFeed,
        should_abort: Callable[[], bool] | None = None,
    ) -> RunResult:
        """Replay a bounded ``feed`` to completion and return the assembled result (backtest).

        Warm-up ticks prime indicators without trading. On each trading tick the session is
        evaluated against current holdings/equity, its orders are executed, and equity is
        recorded. Open positions are liquidated at the last known prices at the end.

        Raises:
            RuntimeCancelled: if ``should_abort`` returns True mid-run.
        """
        equity_curve: list[tuple[datetime, float]] = []
        rejected_signals: list[RejectedSignal] = []
        days_with_position = 0
        total_days = 0

        total_ticks = feed.total_ticks
        self.observer.on_start(total_ticks)

        index = 0
        last_date: datetime | None = None

        async for date, bars, warm_up in feed:
            self.portfolio.update_prices({symbol: bar.close for symbol, bar in bars.items()})
            last_date = date

            if warm_up:
                # Prime indicators without trading or advancing the rebalance clock.
                self.session.evaluate(bars, {}, self.portfolio.equity(), warm_up=True)
                continue

            if should_abort is not None and should_abort():
                raise RuntimeCancelled(f"Run cancelled at {date.isoformat()}")

            total_days += 1
            await self._evaluate_and_execute(date, bars, rejected_signals)

            if self.portfolio.positions:
                days_with_position += 1

            equity_curve.append((date, self.portfolio.equity()))
            index += 1
            self.observer.on_tick(index, total_ticks, date, equity_curve[-1][1])

        # Close all remaining positions at the last known prices.
        if last_date is not None:
            for outcome in await self.execution.liquidate(self.portfolio, last_date):
                self._emit(outcome, rejected_signals)

        # Replace the last equity point (pre-liquidation mark) with realized equity.
        if equity_curve:
            ld = equity_curve[-1][0]
            equity_curve[-1] = (ld, self.portfolio.equity())

        result = assemble_result(
            self.portfolio.initial_capital,
            equity_curve,
            self.portfolio.trades,
            rejected_signals,
            days_with_position,
            total_days,
            self.risk_free_rate,
        )
        self.observer.on_complete(result)
        return result

    async def stream(
        self,
        feed: BarFeed,
        should_stop: Callable[[], bool] | None = None,
    ) -> None:
        """Drive the per-tick evaluate→submit loop over an unbounded live ``feed``.

        Unlike :meth:`run`, live never liquidates and produces no ``RunResult`` — the loop ends
        only when the feed is exhausted (session stopped) or ``should_stop`` returns True.
        ``execute`` submits orders; fills arrive out-of-band and are applied to the portfolio (and
        emitted via the observer) by the caller's fill loop, not here.
        """
        total_ticks = feed.total_ticks
        self.observer.on_start(total_ticks)
        rejected: list[RejectedSignal] = []
        index = 0

        async for date, bars, warm_up in feed:
            self.portfolio.update_prices({symbol: bar.close for symbol, bar in bars.items()})

            if warm_up:
                self.session.evaluate(bars, {}, self.portfolio.equity(), warm_up=True)
                continue

            if should_stop is not None and should_stop():
                break

            await self._evaluate_and_execute(date, bars, rejected, offload=True)
            index += 1
            self.observer.on_tick(index, total_ticks, date, self.portfolio.equity())

    async def _evaluate_and_execute(
        self,
        date: datetime,
        bars: dict[str, Bar],
        rejected: list[RejectedSignal],
        *,
        offload: bool = False,
    ) -> None:
        """Evaluate the session and execute its orders — the per-tick core shared by run + stream.

        ``offload`` runs the (NumPy-heavy) evaluation in a worker thread so it never blocks the
        event loop driving live fill/equity loops; backtest keeps it inline (no per-tick thread).
        """
        equity = self.portfolio.equity()
        holdings = self.portfolio.holdings()
        if offload:
            orders = await asyncio.to_thread(self.session.evaluate, bars, holdings, equity)
        else:
            orders = self.session.evaluate(bars, holdings, equity)
        for order in orders:
            bar = bars.get(order.symbol)
            if bar is None:
                continue
            outcome = await self.execution.execute(order, bar, self.portfolio, date)
            self._emit(outcome, rejected)

    def _emit(self, outcome: ExecutionOutcome, rejected: list[RejectedSignal]) -> None:
        if outcome.fill is not None:
            self.observer.on_fill(outcome.fill)
        if outcome.trade is not None:
            self.observer.on_trade(outcome.trade)
        if outcome.rejected is not None:
            rejected.append(outcome.rejected)
            self.observer.on_reject(outcome.rejected)
