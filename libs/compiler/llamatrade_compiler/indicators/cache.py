"""History windowing — bound how many bars the evaluator keeps in memory.

The bar-by-bar evaluator recomputes indicators over its accumulated bar history on every
step, so an unbounded history makes a long backtest O(N^2). Capping the history to the
largest window any part of the strategy actually reads keeps it O(N * window) while
producing identical results.

Bounding is only safe when every read has a bounded window. A no-period metric such as
``(return SPY)`` or ``(drawdown SPY)`` reads the *entire* history, so if a strategy uses one
:func:`compute_window` returns ``None`` and the evaluator keeps the full history.
"""

from __future__ import annotations

from llamatrade_dsl import (
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
from llamatrade_dsl.ast import Block

# Defaults the evaluator applies when a block omits an explicit lookback (must match
# CompiledStrategy's weight/filter logic).
_MOMENTUM_LOOKBACK = 90
_VOL_LOOKBACK = 60
_FILTER_LOOKBACK = 90
# Headroom so off-by-one reads (e.g. prev bar for crossovers, history[-lookback]) never
# fall off the end of the window.
_WINDOW_BUFFER = 10

_VOL_METHODS = {"inverse-volatility", "risk-parity", "min-variance"}


def compute_window(strategy: Strategy, min_bars: int) -> int | None:
    """Largest bar window the strategy reads, or None if it reads unbounded history.

    Args:
        strategy: the parsed strategy AST.
        min_bars: the indicator warm-up requirement (max indicator lookback).

    Returns:
        A bar count to cap history at, or None when an unbounded read (a no-period metric)
        means the full history must be kept.
    """
    lookbacks = [min_bars]
    if _walk_block(strategy, lookbacks):
        return None
    return max(lookbacks) + _WINDOW_BUFFER


def _walk_block(block: Block, acc: list[int]) -> bool:
    """Collect lookbacks into ``acc``; return True if an unbounded read is found."""
    if isinstance(block, Weight):
        if block.method == "momentum":
            acc.append(block.lookback or _MOMENTUM_LOOKBACK)
        elif block.method in _VOL_METHODS:
            acc.append(block.lookback or _VOL_LOOKBACK)
        return any(_walk_block(c, acc) for c in block.children)

    if isinstance(block, Filter):
        acc.append(block.lookback or _FILTER_LOOKBACK)
        return any(_walk_block(c, acc) for c in block.children)

    if isinstance(block, Group | Strategy):
        return any(_walk_block(c, acc) for c in block.children)

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
        return _walk_value(condition.left, acc) or _walk_value(condition.right, acc)
    if isinstance(condition, Crossover):
        return _walk_value(condition.fast, acc) or _walk_value(condition.slow, acc)
    # The Condition union is exhausted: this is a LogicalOp (and / or / not).
    return any(_walk_condition(op, acc) for op in condition.operands)


def _walk_value(value: Value, acc: list[int]) -> bool:
    # Indicator lookbacks are already covered by min_bars; only metrics can be unbounded.
    if isinstance(value, Metric):
        if value.period is None:
            return True  # reads the entire history
        acc.append(value.period)
    return False
