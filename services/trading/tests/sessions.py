"""Shared StrategySession builders for runner tests."""

from llamatrade_runtime import StrategySession

# A single-symbol hold strategy: emits no rebalance signal, so runners whose tests
# drive fills or orders directly are not perturbed by evaluation.
QUIET_STRATEGY = '(strategy "Quiet" :rebalance daily (asset SPY :weight 100))'


def quiet_session() -> StrategySession:
    """A session over QUIET_STRATEGY for runner construction."""
    return StrategySession(QUIET_STRATEGY)
