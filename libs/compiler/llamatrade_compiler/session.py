"""StrategySession — the single evaluation+sizing path for live and backtest.

This is the unification point. A session owns **one** :class:`CompiledStrategy` fed the
latest bars for **all** symbols together (merged history), applies **one** portfolio-level
rebalance gate, computes target weights, and sizes them into intended orders.

It replaces the two divergent adapters:
- ``services/trading/.../compiler_adapter.py`` (one CompiledStrategy *per symbol* + a gate
  consumed by whichever symbol's bar arrived first → cross-symbol conditions broke and
  multi-symbol strategies rebalanced only one leg per period).
- ``services/backtest/.../strategy_adapter.py`` (merged history, correct — kept here).

Both the live runner and the backtest engine call :meth:`evaluate` with the latest bars
for every symbol, current holdings, and equity, and receive the same intended orders — so
backtest faithfully predicts live by construction.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date

from llamatrade_compiler.evaluation.compiled import CompiledStrategy, compile_strategy
from llamatrade_compiler.evaluation.extractor import get_required_symbols
from llamatrade_compiler.rebalance import should_rebalance
from llamatrade_compiler.sizing import (
    DEFAULT_DRIFT_TOLERANCE,
    Holding,
    IntendedOrder,
    SizingMode,
    size_orders,
)
from llamatrade_compiler.types import Bar
from llamatrade_dsl import RebalanceFrequency, Strategy, parse_strategy, validate_strategy


class StrategySession:
    """A live or simulated run of one strategy over a single account/sleeve.

    Stateful across calls: it accumulates merged bar history (for indicators) and tracks
    the portfolio-level last-rebalance date and last target weights.
    """

    def __init__(
        self,
        strategy: str | Strategy,
        *,
        sizing_mode: SizingMode = SizingMode.DRIFT,
        drift_tolerance: float = DEFAULT_DRIFT_TOLERANCE,
    ) -> None:
        """Build a session from a strategy S-expression or an already-parsed AST.

        Args:
            strategy: the strategy DSL (S-expression text) or a parsed :class:`Strategy`.
            sizing_mode: BINARY (all-or-nothing) or DRIFT (resize within a band).
            drift_tolerance: DRIFT-mode band before a resize trade is worth doing.

        Raises:
            ValueError: if the strategy cannot be parsed, is invalid, or fails to compile.
        """
        if isinstance(strategy, str):
            try:
                ast = parse_strategy(strategy)
            except Exception as e:
                raise ValueError(f"Failed to parse strategy: {e}") from e
        else:
            ast = strategy

        validation = validate_strategy(ast)
        if not validation.valid:
            errors = "; ".join(str(e) for e in validation.errors)
            raise ValueError(f"Invalid strategy: {errors}")

        try:
            self._compiled: CompiledStrategy = compile_strategy(ast)
        except Exception as e:
            raise ValueError(f"Failed to compile strategy: {e}") from e

        self._ast = ast
        self._symbols: set[str] = get_required_symbols(ast)
        self._rebalance_freq: RebalanceFrequency | None = ast.rebalance
        self._sizing_mode = sizing_mode
        self._drift_tolerance = drift_tolerance

        # Portfolio-level rebalance/weights state (NOT per-symbol).
        self._last_rebalance: date | None = None
        self._current_weights: dict[str, float] = {}

    def evaluate(
        self,
        bars: Mapping[str, Bar],
        holdings: Mapping[str, Holding],
        equity: float,
        *,
        warm_up: bool = False,
    ) -> list[IntendedOrder]:
        """Evaluate the strategy for one timestep and return intended orders.

        Feed the latest bar for **every** subscribed symbol. On non-rebalance days the bars
        are still fed to the indicators (kept warm) but no orders are produced. On a
        rebalance day with enough history, target weights are computed across all symbols
        and sized against ``holdings``/``equity``.

        Args:
            bars: latest bar per symbol (all symbols together).
            holdings: current positions keyed by symbol.
            equity: total portfolio (or sleeve) equity to size against.
            warm_up: when True, feed the bars to indicators but never trade or advance the
                rebalance clock (used to prime history before the live/backtest window so
                the first real bar always rebalances).

        Returns:
            Intended orders (possibly empty). Empty during warm-up, on non-rebalance days,
            or when no holding needs to change.
        """
        if not bars:
            return []

        current_date = _latest_date(bars)

        # Warm-up or non-rebalance day: keep indicators warm, emit nothing, hold the clock.
        if warm_up or not should_rebalance(
            current_date, self._last_rebalance, self._rebalance_freq
        ):
            self._compiled.add_bars(dict(bars))
            return []

        # Rebalance day: compute_allocation also feeds the bars to history internally.
        allocation = self._compiled.compute_allocation(dict(bars))
        weights = allocation["weights"]
        if not weights:
            # Still warming up (insufficient history) — do not advance the clock.
            return []

        prices = {symbol: bar.close for symbol, bar in bars.items()}
        orders = size_orders(
            weights,
            holdings,
            prices,
            equity,
            mode=self._sizing_mode,
            drift_tolerance=self._drift_tolerance,
            current_weights=self._current_weights,
        )

        self._current_weights = dict(weights)
        self._last_rebalance = current_date
        return orders

    def reset(self) -> None:
        """Reset all state (history, rebalance clock, weights) for a fresh run."""
        self._compiled.reset()
        self._last_rebalance = None
        self._current_weights = {}

    @property
    def symbols(self) -> list[str]:
        """Symbols the strategy requires (traded + indicator-only)."""
        return sorted(self._symbols)

    @property
    def min_bars(self) -> int:
        """Minimum bars of history before the strategy can evaluate."""
        return int(self._compiled.min_bars)

    @property
    def name(self) -> str:
        return str(self._ast.name)

    @property
    def rebalance_frequency(self) -> RebalanceFrequency | None:
        return self._rebalance_freq

    @property
    def current_weights(self) -> dict[str, float]:
        """Last computed target weights (empty before the first rebalance)."""
        return dict(self._current_weights)

    @property
    def last_rebalance(self) -> date | None:
        return self._last_rebalance


def _latest_date(bars: Mapping[str, Bar]) -> date:
    """The (max) calendar date across the provided bars."""
    return max(bar.timestamp.date() for bar in bars.values())
