"""LlamaTrade Strategy Compiler - compiles allocation strategies into executable form.

The compiler takes a parsed Strategy AST and produces a CompiledStrategy that
efficiently computes portfolio allocations from market data, bar by bar. The same
engine drives both live trading (one bar at a time off a stream) and backtesting
(historical bars replayed in order), so live and backtest evaluate identically.

Pipeline:
1. Extractor: extract indicator specifications from the AST.
2. Pipeline: compute indicator values from price data.
3. Evaluator: evaluate conditions against computed values.
4. CompiledStrategy: orchestrate the full allocation cycle.
"""

from llamatrade_compiler.evaluation.compiled import Allocation, CompiledStrategy, compile_strategy
from llamatrade_compiler.evaluation.conditions import (
    EvaluationError,
    evaluate_condition,
    evaluate_condition_safe,
    normalize_weights,
    safe_divide,
)
from llamatrade_compiler.evaluation.extractor import (
    IndicatorSpec,
    extract_indicators,
    get_max_lookback,
    get_required_sources,
    get_required_symbols,
)
from llamatrade_compiler.evaluation.state import EvaluationState, Position
from llamatrade_compiler.indicators.library import (
    PriceData,
    compute_all_indicators,
    compute_indicator,
)
from llamatrade_compiler.rebalance import should_rebalance
from llamatrade_compiler.session import StrategySession
from llamatrade_compiler.sizing import (
    DEFAULT_DRIFT_TOLERANCE,
    DEFAULT_MIN_WEIGHT_CHANGE,
    Holding,
    IntendedOrder,
    SizingMode,
    size_orders,
)
from llamatrade_compiler.types import Bar, Signal, SignalMetadata, SignalType

__all__ = [
    # Core types
    "Allocation",
    "Bar",
    "CompiledStrategy",
    "EvaluationState",
    "IndicatorSpec",
    "Position",
    "PriceData",
    "Signal",
    "SignalMetadata",
    "SignalType",
    # Unified evaluation + sizing
    "StrategySession",
    "Holding",
    "IntendedOrder",
    "SizingMode",
    "size_orders",
    "should_rebalance",
    "DEFAULT_DRIFT_TOLERANCE",
    "DEFAULT_MIN_WEIGHT_CHANGE",
    # Exceptions
    "EvaluationError",
    # Compilation
    "compile_strategy",
    # Pipeline functions
    "compute_all_indicators",
    "compute_indicator",
    "evaluate_condition",
    "evaluate_condition_safe",
    "extract_indicators",
    "get_max_lookback",
    "get_required_sources",
    "get_required_symbols",
    # Helper functions
    "normalize_weights",
    "safe_divide",
]
