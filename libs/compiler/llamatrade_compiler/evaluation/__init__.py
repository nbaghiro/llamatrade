"""Strategy evaluation: compile the AST, compute indicators, fold blocks into weights."""

from llamatrade_compiler.evaluation.compiled import Allocation, CompiledStrategy, compile_strategy
from llamatrade_compiler.evaluation.extractor import (
    IndicatorSpec,
    extract_indicators,
    get_max_lookback,
    get_required_symbols,
)

__all__ = [
    "Allocation",
    "CompiledStrategy",
    "IndicatorSpec",
    "compile_strategy",
    "extract_indicators",
    "get_max_lookback",
    "get_required_symbols",
]
