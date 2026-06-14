"""The rebalance clock — the single source of truth for "is today a rebalance day?".

This replaces the two byte-identical copies of ``should_rebalance`` that used to live
in the backtest adapter (``services/backtest/.../strategy_adapter.py``) and the live
adapter (``services/trading/.../compiler_adapter.py``). Both the live runner and the
backtest engine now gate on this one function via :class:`StrategySession`, so a strategy
rebalances on exactly the same calendar days in simulation and in production.
"""

from __future__ import annotations

from datetime import date

from llamatrade_dsl import RebalanceFrequency


def should_rebalance(
    current_date: date,
    last_rebalance: date | None,
    frequency: RebalanceFrequency | None,
) -> bool:
    """Return True if a rebalance should occur on ``current_date``.

    The clock is **portfolio-level**: ``last_rebalance`` is one date for the whole
    strategy, not per symbol. The first evaluation always rebalances; the same calendar
    day never rebalances twice; otherwise the strategy's ``:rebalance`` frequency decides.

    Args:
        current_date: the date of the bar being evaluated.
        last_rebalance: the date of the previous rebalance, or None if never.
        frequency: the strategy's rebalance frequency (defaults to daily when unset).
    """
    # First evaluation always rebalances.
    if last_rebalance is None:
        return True

    # Never rebalance twice on the same calendar day.
    if current_date == last_rebalance:
        return False

    freq = frequency or "daily"

    match freq:
        case "daily":
            return current_date > last_rebalance

        case "weekly":
            # Rebalance on Monday (weekday 0), as long as a day has actually passed.
            is_monday = current_date.weekday() == 0
            days_passed = (current_date - last_rebalance).days
            return is_monday and days_passed >= 1

        case "monthly":
            return (
                current_date.month != last_rebalance.month
                or current_date.year != last_rebalance.year
            )

        case "quarterly":
            current_quarter = (current_date.month - 1) // 3
            last_quarter = (last_rebalance.month - 1) // 3
            return current_quarter != last_quarter or current_date.year != last_rebalance.year

        case "annually":
            return current_date.year != last_rebalance.year

    # Unknown frequency: be conservative and rebalance daily.
    return current_date > last_rebalance
