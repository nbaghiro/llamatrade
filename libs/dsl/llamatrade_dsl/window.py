"""History windowing — bound how many bars the evaluator keeps in memory.

The bar-by-bar evaluator recomputes indicators over its accumulated bar history on every
step, so an unbounded history makes a long backtest O(N^2). Capping the history to the
largest window any part of the strategy actually reads keeps it O(N * window) while
producing identical results.

Bounding is always applied. When every read has a bounded window the cap is exactly that
window. A no-period metric such as ``(return SPY)`` or ``(drawdown SPY)`` reads the *entire*
history; rather than grow without bound, :func:`compute_window` caps it at ``_MAX_WINDOW``
bars — a deliberate, bounded approximation of "all history" that keeps memory and per-bar
recompute bounded.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence

from llamatrade_dsl.ast import (
    Block,
    Comparison,
    Condition,
    Crossover,
    Filter,
    Group,
    If,
    Metric,
    Strategy,
    Value,
    Weight,
)

# Defaults the evaluator applies when a block omits an explicit lookback (must match
# CompiledStrategy's weight/filter logic).
_MOMENTUM_LOOKBACK = 90
_VOL_LOOKBACK = 60
_FILTER_LOOKBACK = 90
# Headroom so off-by-one reads (e.g. prev bar for crossovers, history[-lookback]) never
# fall off the end of the window.
_WINDOW_BUFFER = 10

_VOL_METHODS = {"inverse-volatility", "risk-parity", "min-variance"}

# Hard cap on retained history when a strategy reads unbounded history (a period-less
# metric). ~8 years of daily bars. Without it, history grows forever and the per-bar
# indicator recompute degrades to O(N^2).
_MAX_WINDOW = 2000

logger = logging.getLogger(__name__)


def collect_lookbacks(strategy: Strategy, indicator_min_bars: int) -> tuple[int, bool]:
    """Largest bounded lookback the strategy reads (indicators + weight/filter/metric), plus a flag
    for whether it reads unbounded history (a period-less metric)."""
    lookbacks = [indicator_min_bars]
    unbounded = _walk_block(strategy, lookbacks)
    return max(lookbacks), unbounded


def max_lookback(strategy: Strategy, indicator_min_bars: int) -> int:
    """Warm-up requirement in bars: the largest bounded lookback across indicators + weight/filter/metric."""
    return collect_lookbacks(strategy, indicator_min_bars)[0]


def compute_window(strategy: Strategy, min_bars: int, max_window: int = _MAX_WINDOW) -> int:
    """Largest bar window the strategy reads, always capped at ``max_window``.

    Args:
        strategy: the parsed strategy AST.
        min_bars: the warm-up requirement (max lookback across indicators + weight/filter/metric).
        max_window: hard cap applied when the strategy reads unbounded history.

    Returns:
        A bar count to cap retained history at. For a strategy whose reads are all
        bounded this is exactly the largest window read; for one that reads unbounded
        history (a no-period metric) it is ``max_window`` (never below the warm-up need),
        trading exactness over the full series for bounded memory and O(N * window) recompute.
    """
    needed_max, unbounded = collect_lookbacks(strategy, min_bars)
    needed = needed_max + _WINDOW_BUFFER
    if unbounded:
        capped = max(needed, max_window)
        logger.debug(
            "strategy %r reads unbounded history; capping retained bars at %d",
            strategy.name,
            capped,
        )
        return capped
    return needed


def _walk_children(children: Sequence[Block], acc: list[int]) -> bool:
    """Walk every child — short-circuiting would drop later siblings' lookbacks from ``acc``."""
    unbounded = False
    for child in children:
        unbounded |= _walk_block(child, acc)
    return unbounded


def _walk_block(block: Block, acc: list[int]) -> bool:
    """Collect lookbacks into ``acc``; return True if an unbounded read is found."""
    if isinstance(block, Weight):
        if block.method == "momentum":
            acc.append(block.lookback or _MOMENTUM_LOOKBACK)
        elif block.method in _VOL_METHODS:
            acc.append(block.lookback or _VOL_LOOKBACK)
        return _walk_children(block.children, acc)

    if isinstance(block, Filter):
        acc.append(block.lookback or _FILTER_LOOKBACK)
        return _walk_children(block.children, acc)

    if isinstance(block, Group | Strategy):
        return _walk_children(block.children, acc)

    if isinstance(block, If):
        unbounded = _walk_condition(block.condition, acc)
        unbounded |= _walk_block(block.then_block, acc)
        if block.else_block is not None:
            unbounded |= _walk_block(block.else_block, acc)
        return unbounded

    # Asset: no history reads.
    return False


def _walk_condition(condition: Condition, acc: list[int]) -> bool:
    if isinstance(condition, Comparison):
        return _walk_value(condition.left, acc) | _walk_value(condition.right, acc)
    if isinstance(condition, Crossover):
        return _walk_value(condition.fast, acc) | _walk_value(condition.slow, acc)
    # The Condition union is exhausted: this is a LogicalOp (and / or / not).
    unbounded = False
    for operand in condition.operands:
        unbounded |= _walk_condition(operand, acc)
    return unbounded


def _walk_value(value: Value, acc: list[int]) -> bool:
    # Indicator lookbacks are already covered by min_bars; only metrics can be unbounded.
    if isinstance(value, Metric):
        if value.period is None:
            return True  # reads the entire history
        acc.append(value.period)
    return False
