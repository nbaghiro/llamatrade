"""Strategy compiler for vectorized backtest engine.

This module provides a thin wrapper around the shared llamatrade_compiler
library's vectorized compilation functionality.
"""

# Re-export from shared library for backward compatibility
from llamatrade_compiler import (
    VectorizedCompiledStrategy,
    should_use_vectorized_engine,
)
from llamatrade_compiler import (
    compile_vectorized_strategy as compile_strategy,
)

# Re-export internal functions for tests (these are implementation details
# but tests rely on them for verification)
from llamatrade_compiler.vectorized_compiler import (
    _build_indicator_key as _build_indicator_key,  # pyright: ignore[reportPrivateUsage]
)
from llamatrade_compiler.vectorized_compiler import (
    _compute_all_indicators as _compute_all_indicators,  # pyright: ignore[reportPrivateUsage]
)
from llamatrade_compiler.vectorized_compiler import (
    _compute_single_indicator as _compute_single_indicator,  # pyright: ignore[reportPrivateUsage]
)
from llamatrade_compiler.vectorized_compiler import (
    _evaluate_condition_vectorized as _evaluate_condition_vectorized,  # pyright: ignore[reportPrivateUsage]
)
from llamatrade_compiler.vectorized_compiler import (
    _get_vectorized_value as _get_vectorized_value,  # pyright: ignore[reportPrivateUsage]
)

__all__ = [
    # Main API
    "compile_strategy",
    "should_use_vectorized_engine",
    "VectorizedCompiledStrategy",
    # Internal functions (for tests)
    "_build_indicator_key",
    "_compute_all_indicators",
    "_compute_single_indicator",
    "_evaluate_condition_vectorized",
    "_get_vectorized_value",
]
