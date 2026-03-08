"""LlamaTrade Strategy Compiler - compiles allocation strategies into executable form.

The compiler takes a parsed Strategy AST and produces a CompiledStrategy
that can efficiently compute portfolio allocations from market data.

Two compilation modes are available:
- Bar-by-bar (CompiledStrategy): For live trading, processes one bar at a time
- Vectorized (VectorizedCompiledStrategy): For backtesting, processes all bars at once

Pipeline:
1. Extractor: Extract indicator specifications from AST
2. Pipeline: Compute indicator values from price data
3. Evaluator: Evaluate conditions against computed values
4. CompiledStrategy: Orchestrates the full allocation cycle
"""

# Bar-by-bar compilation (for live trading)
from llamatrade_compiler.compiled import Allocation, CompiledStrategy, compile_strategy
from llamatrade_compiler.evaluator import (
    EvaluationError,
    evaluate_condition,
    evaluate_condition_safe,
    evaluate_condition_vectorized,
    normalize_weights,
    safe_divide,
)
from llamatrade_compiler.extractor import (
    IndicatorSpec,
    extract_indicators,
    get_max_lookback,
    get_required_sources,
    get_required_symbols,
)
from llamatrade_compiler.pipeline import PriceData, compute_all_indicators, compute_indicator
from llamatrade_compiler.state import EvaluationState, Position
from llamatrade_compiler.types import Bar, Signal, SignalMetadata, SignalType

# Vectorized compilation (for backtesting) - default for performance
from llamatrade_compiler.vectorized import (
    AllocationFn,
    VectorizedBarData,
    VectorizedCompiledStrategy,
    prepare_vectorized_bars,
    should_use_vectorized_engine,
)
from llamatrade_compiler.vectorized_compiler import compile_vectorized_strategy

__all__ = [
    # Core types
    "Allocation",
    "AllocationFn",
    "Bar",
    "CompiledStrategy",
    "EvaluationState",
    "IndicatorSpec",
    "Position",
    "PriceData",
    "Signal",
    "SignalMetadata",
    "SignalType",
    # Vectorized types (for backtesting)
    "VectorizedBarData",
    "VectorizedCompiledStrategy",
    # Exceptions
    "EvaluationError",
    # Bar-by-bar compilation (for live trading)
    "compile_strategy",
    # Vectorized compilation (for backtesting)
    "compile_vectorized_strategy",
    "prepare_vectorized_bars",
    "should_use_vectorized_engine",
    # Pipeline functions
    "compute_all_indicators",
    "compute_indicator",
    "evaluate_condition",
    "evaluate_condition_safe",
    "evaluate_condition_vectorized",
    "extract_indicators",
    "get_max_lookback",
    "get_required_sources",
    "get_required_symbols",
    # Helper functions
    "normalize_weights",
    "safe_divide",
]
