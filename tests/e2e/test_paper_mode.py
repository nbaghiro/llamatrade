"""E2E paper-mode suite — real runs against the live mesh.

Each test drives one leg of the harness (see harness.py) and asserts every
check passed. Marked ``e2e``; requires the running stack + backtest worker +
seeded demo (the ``session`` fixture skips the suite otherwise). Run with:

    pytest tests/e2e            # or standalone: python tests/e2e/harness.py
"""

from __future__ import annotations

import pytest

from . import harness

pytestmark = pytest.mark.e2e


def test_backtest_leg(session: harness.JSON) -> None:
    """A real RunBacktest → worker → GetBacktest produces persisted results."""
    harness.reset()
    harness.leg_backtest(session)
    assert not harness.failures(), f"e2e checks failed: {harness.failures()}"


def test_trading_leg(session: harness.JSON) -> None:
    """Fund a strategy → a fill lands → the portfolio projects/flattens the position."""
    harness.reset()
    harness.leg_trading(session)
    assert not harness.failures(), f"e2e checks failed: {harness.failures()}"
