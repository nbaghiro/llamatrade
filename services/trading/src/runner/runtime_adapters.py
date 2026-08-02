"""Live-execution adapters — run a live session through the shared ``llamatrade_runtime``.

These wrap the runner's already-hardened pieces (its ``_process_signal`` submit path, its
fill-maintained position/equity state, its bar stream) behind the runtime's async seams, so live
trading runs the SAME ``StrategyRuntime`` loop as backtest. Nothing here reimplements order / fill /
ledger logic — it delegates to the runner's existing methods. Fills arrive out-of-band on the
``trade_updates`` stream (the runner's fill loop), so ``execute`` returns an accepted outcome with
no inline fill.
"""

from collections.abc import AsyncIterator, Awaitable, Callable, Mapping, Sequence
from datetime import datetime
from typing import Protocol

from llamatrade_alpaca import StreamBar as BarData
from llamatrade_runtime import (
    Bar,
    ExecutionOutcome,
    FormingBarAggregator,
    FormingBarFeed,
    Holding,
    IntendedOrder,
    Portfolio,
)

# Submit a sized order through the runner's hardened path: (side, symbol, quantity, price, ts).
SubmitOrder = Callable[[str, str, float, float, datetime], Awaitable[None]]


class BarStream(Protocol):
    """The subset of the live bar-stream client the feed needs."""

    def stream(self) -> AsyncIterator[BarData]: ...


def to_compiler_bar(bar: BarData) -> Bar:
    """Convert a live stream bar to a compiler bar."""
    return Bar(
        timestamp=bar.timestamp,
        open=bar.open,
        high=bar.high,
        low=bar.low,
        close=bar.close,
        volume=int(bar.volume),
    )


class StreamBarFeed(FormingBarFeed):
    """``FormingBarFeed`` over the Alpaca-shaped live bar stream.

    Translation only: each streamed bar becomes ``(symbol, Bar)`` for the shared feed, which folds
    the one-minute stream into the strategy's period grid, applies the all-symbols/once-per-period
    gate, and yields the snapshot. ``on_bar`` runs the runner's per-bar side effects (history +
    latency metric) on every raw bar, including symbols the strategy does not subscribe to.
    """

    def __init__(
        self,
        bar_stream: BarStream,
        symbols: Sequence[str],
        *,
        aggregator: FormingBarAggregator | None = None,
        gate: Callable[[datetime], bool] | None = None,
        on_bar: Callable[[BarData], None] | None = None,
        is_running: Callable[[], bool] | None = None,
    ) -> None:
        self._bar_stream = bar_stream
        self._on_bar = on_bar
        super().__init__(
            self._translated(),
            symbols,
            aggregator=aggregator,
            gate=gate,
            is_running=is_running,
        )

    async def _translated(self) -> AsyncIterator[tuple[str, Bar]]:
        async for bar in self._bar_stream.stream():
            if self._on_bar is not None:
                self._on_bar(bar)
            yield bar.symbol, to_compiler_bar(bar)


class LedgerPortfolio(Portfolio):
    """Live portfolio view: ``holdings`` + ``equity`` delegate to the runner's fill-maintained state.

    The runtime reads ``holdings()`` / ``equity()`` each tick for sizing; mutation happens
    out-of-band in the runner's fill + equity-sync loops, not here. ``update_prices`` is a no-op —
    live equity comes from the sleeve (book of record), not marked-to-market local prices.
    """

    def __init__(
        self,
        holdings_provider: Callable[[], dict[str, Holding]],
        equity_provider: Callable[[], float],
    ) -> None:
        super().__init__(0.0)
        self._holdings_provider = holdings_provider
        self._equity_provider = equity_provider

    def holdings(self) -> dict[str, Holding]:
        return self._holdings_provider()

    def equity(self) -> float:
        return self._equity_provider()

    def update_prices(self, prices: Mapping[str, float]) -> None:
        return None


class RunnerExecution:
    """``ExecutionAdapter`` that submits via the runner's hardened path; fills arrive out-of-band."""

    def __init__(self, submit: SubmitOrder) -> None:
        self._submit = submit

    async def execute(
        self, order: IntendedOrder, bar: Bar, portfolio: Portfolio, date: datetime
    ) -> ExecutionOutcome:
        await self._submit(order.side, order.symbol, order.quantity, order.price, date)
        return ExecutionOutcome()  # accepted; the fill lands later on the trade_updates stream

    async def liquidate(self, portfolio: Portfolio, date: datetime) -> list[ExecutionOutcome]:
        return []  # live never liquidates
