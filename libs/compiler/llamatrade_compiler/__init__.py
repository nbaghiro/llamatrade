"""LlamaTrade Strategy Compiler - compiles DSL strategies into executable form.

The compiler takes a parsed Strategy AST and produces a CompiledStrategy
that can efficiently evaluate entry/exit conditions against market data.

Pipeline:
1. Extractor: Extract indicator specifications from AST
2. Pipeline: Compute indicator values from price data
3. Evaluator: Evaluate conditions against computed values
4. CompiledStrategy: Orchestrates the full evaluation cycle
"""

from llamatrade_compiler.compiled import CompiledStrategy, compile_strategy
from llamatrade_compiler.evaluator import (
    EvaluationError,
    evaluate_condition,
    evaluate_entry,
    evaluate_exit,
)
from llamatrade_compiler.extractor import (
    IndicatorSpec,
    extract_indicators,
    get_max_lookback,
    get_required_sources,
)
from llamatrade_compiler.pipeline import PriceData, compute_all_indicators, compute_indicator
from llamatrade_compiler.state import EvaluationState, Position
from llamatrade_compiler.types import Bar, Signal, SignalMetadata, SignalType

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
