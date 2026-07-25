"""Strategy evaluation: compile the AST, compute indicators, fold blocks into weights."""

from llamatrade_dsl.analysis import (
    IndicatorSpec,
    extract_indicators,
    get_max_lookback,
    get_required_symbols,
)
from llamatrade_runtime.evaluation.compiled import Allocation, CompiledStrategy, compile_strategy

__all__ = [
    "Allocation",
    "CompiledStrategy",
    "IndicatorSpec",
    "compile_strategy",
    "extract_indicators",
    "get_max_lookback",
    "get_required_symbols",
]
