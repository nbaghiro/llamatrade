"""Bridge the backtest engine to the shared StrategySession.

The strategy evaluation (rebalance clock, weight computation, sizing) lives in the shared
``llamatrade_compiler`` library so backtest and live trading evaluate identically. This
module only adapts the engine's per-date callback to drive a :class:`StrategySession`:
convert the engine's bar dicts to compiler bars, read holdings/equity from the engine, and
turn the session's intended orders into the engine's ``SignalData``.

The previous hand-rolled copy of the rebalance gate and drift sizing has been removed —
those now have a single implementation in ``llamatrade_compiler`` (``should_rebalance`` and
``size_orders``), shared with the live runner.
"""

from llamatrade_compiler import Bar, Holding, SizingMode, StrategySession
from llamatrade_compiler import should_rebalance as should_rebalance  # re-export for callers

from src.engine.backtester import BacktestEngine, BarData, SignalData, StrategyFn

__all__ = [
    "create_multi_symbol_strategy",
    "should_rebalance",
]


def _convert_bar(bar: BarData) -> Bar:
    """Convert backtest BarData (TypedDict) to a compiler Bar."""
    return Bar(
        timestamp=bar["timestamp"],
        open=bar["open"],
        high=bar["high"],
        low=bar["low"],
        close=bar["close"],
        volume=bar["volume"],
    )


def create_multi_symbol_strategy(
    config_sexpr: str,
) -> tuple[StrategyFn, set[str], int]:
    """Build a multi-symbol strategy callback backed by a shared StrategySession.

    The returned callback receives ALL symbols' bars for each date and drives one
    :class:`StrategySession`, which evaluates cross-symbol conditions and rebalances on a
    portfolio-level clock — identical to live trading.

    Args:
        config_sexpr: the strategy S-expression in allocation format.

    Returns:
        ``(strategy_fn, required_symbols, min_bars)`` — the per-date callback, the symbols
        the strategy needs (traded + indicator-only), and the warm-up bar count.

    Raises:
        ValueError: if the strategy cannot be parsed, is invalid, or fails to compile.
    """
    session = StrategySession(config_sexpr, sizing_mode=SizingMode.DRIFT)
    required_symbols = set(session.symbols)
    min_bars = session.min_bars

    def strategy_fn(
        engine: BacktestEngine, bars_dict: dict[str, BarData], warm_up: bool
    ) -> list[SignalData]:
        compiler_bars = {symbol: _convert_bar(bar) for symbol, bar in bars_dict.items()}

        if warm_up:
            # Prime indicators without trading or advancing the rebalance clock.
            session.evaluate(compiler_bars, {}, engine.get_equity(), warm_up=True)
            return []

        holdings = {
            symbol: Holding(symbol, pos.quantity)
            for symbol, pos in engine.positions.items()
            if pos.quantity > 0
        }
        orders = session.evaluate(compiler_bars, holdings, engine.get_equity())
        return [
            SignalData(type=o.side, symbol=o.symbol, quantity=o.quantity, price=o.price)
            for o in orders
        ]

    return strategy_fn, required_symbols, min_bars
