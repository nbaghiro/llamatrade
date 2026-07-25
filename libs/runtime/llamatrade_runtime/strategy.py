"""Strategy session construction for the runtime.

Builds a :class:`StrategySession` (the shared evaluation+sizing path) from a strategy
S-expression. The runtime drives the session directly — no per-engine adapter closure.
"""

from llamatrade_runtime.rebalance import should_rebalance as should_rebalance
from llamatrade_runtime.session import StrategySession
from llamatrade_runtime.sizing import SizingMode

__all__ = ["build_session", "should_rebalance"]


def build_session(
    config_sexpr: str,
    *,
    sizing_mode: SizingMode = SizingMode.DRIFT,
) -> tuple[StrategySession, set[str], int]:
    """Compile a strategy into a session.

    Args:
        config_sexpr: the strategy S-expression in allocation format.
        sizing_mode: BINARY (all-or-nothing) or DRIFT (resize within a band).

    Returns:
        ``(session, required_symbols, min_bars)`` — the session, the symbols it needs
        (traded + indicator-only), and the warm-up bar count.

    Raises:
        ValueError: if the strategy cannot be parsed, is invalid, or fails to compile.
    """
    session = StrategySession(config_sexpr, sizing_mode=sizing_mode)
    return session, set(session.symbols), session.min_bars
