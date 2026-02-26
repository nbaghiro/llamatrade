"""Strategy compiler - re-exports from shared llamatrade-compiler library.

The compiler takes a parsed Strategy AST and produces a CompiledStrategy
that can efficiently evaluate entry/exit conditions against market data.
"""

# Re-export everything from the shared library
from llamatrade_compiler import (
    Bar,
    CompiledStrategy,
    EvaluationError,
    EvaluationState,
    IndicatorSpec,
    Position,
    PriceData,
    Signal,
    SignalMetadata,
    SignalType,
    compile_strategy,
    compute_all_indicators,
    compute_indicator,
    evaluate_condition,
    evaluate_entry,
    evaluate_exit,
    extract_indicators,
    get_max_lookback,
    get_required_sources,
)

__all__ = [
    # Core types
    "Bar",
    "CompiledStrategy",
    "EvaluationState",
    "IndicatorSpec",
    "Position",
    "PriceData",
    "Signal",
    "SignalMetadata",
    "SignalType",
    # Exceptions
    "EvaluationError",
    # Functions
    "compile_strategy",
    "compute_all_indicators",
    "compute_indicator",
    "evaluate_condition",
    "evaluate_entry",
    "evaluate_exit",
    "extract_indicators",
    "get_max_lookback",
    "get_required_sources",
]
