"""Shared real StrategySession builders for runner tests.

The runner requires a merged-symbol session as its evaluation source; these
helpers build small real sessions (no doubles) so tests exercise the same
evaluation path production uses.
"""

from collections.abc import Mapping

from llamatrade_runtime import Bar, Holding, IntendedOrder, StrategySession


def hold_session(*symbols: str) -> StrategySession:
    """A real session that targets an equal-weight hold of ``symbols``."""
    names = symbols or ("AAPL",)
    weight = 100 // len(names)
    assets = " ".join(f"(asset {s} :weight {weight})" for s in names)
    return StrategySession(f'(strategy "Hold" :rebalance daily {assets})')


class CountingSession(StrategySession):
    """Real session that also counts ``evaluate`` calls (for gate tests)."""

    def __init__(self, sexpr: str) -> None:
        super().__init__(sexpr)
        self.evaluate_calls = 0

    def evaluate(
        self,
        bars: Mapping[str, Bar],
        holdings: Mapping[str, Holding],
        equity: float,
        *,
        warm_up: bool = False,
    ) -> list[IntendedOrder]:
        self.evaluate_calls += 1
        return super().evaluate(bars, holdings, equity, warm_up=warm_up)
