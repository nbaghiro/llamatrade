"""Standardized error handling for DSL and gRPC services.

Provides consistent error mapping between DSL errors and gRPC status codes,
with structured error details including source location information.
"""

from dataclasses import dataclass
from enum import IntEnum


class DSLErrorCode(IntEnum):
    """DSL error codes for client-facing error responses."""

    # Parse errors (1xx)
    PARSE_ERROR = 100
    INVALID_SYNTAX = 101
    UNEXPECTED_TOKEN = 102
    MISSING_REQUIRED = 103

    # Validation errors (2xx)
    VALIDATION_ERROR = 200
    INVALID_INDICATOR = 201
    INVALID_WEIGHT_METHOD = 202
    INVALID_REBALANCE = 203
    WEIGHT_SUM_ERROR = 204
    INVALID_FILTER = 205
    EMPTY_STRATEGY = 206

    # Compilation errors (3xx)
    COMPILATION_ERROR = 300
    INDICATOR_COMPUTE_ERROR = 301
    CONDITION_EVAL_ERROR = 302

    # Execution errors (4xx)
    EXECUTION_ERROR = 400
    MARKET_DATA_ERROR = 401
    INSUFFICIENT_BARS = 402


@dataclass
class DSLError:
    """Structured DSL error with location and suggestions.

    Attributes:
        code: The DSLErrorCode
        message: Human-readable error message
        path: AST path where error occurred (e.g., "strategy.children[0].method")
        line: Source line number (1-indexed, if available)
        column: Source column number (1-indexed, if available)
        suggestions: List of suggested fixes
    """

    code: DSLErrorCode
    message: str
    path: str = ""
    line: int | None = None
    column: int | None = None
    suggestions: list[str] | None = None

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        result = {
            "code": self.code.value,
            "code_name": self.code.name,
            "message": self.message,
        }
        if self.path:
            result["path"] = self.path
        if self.line is not None:
            result["line"] = self.line
        if self.column is not None:
            result["column"] = self.column
        if self.suggestions:
            result["suggestions"] = self.suggestions
        return result


# Mapping from exception types to DSL error codes
DSL_ERROR_MAP: dict[str, DSLErrorCode] = {
    # Parser errors
    "ParseError": DSLErrorCode.PARSE_ERROR,
    "SyntaxError": DSLErrorCode.INVALID_SYNTAX,
    "TokenError": DSLErrorCode.UNEXPECTED_TOKEN,
    # Validation errors
    "ValidationError": DSLErrorCode.VALIDATION_ERROR,
    # Evaluation errors
    "EvaluationError": DSLErrorCode.CONDITION_EVAL_ERROR,
    # General
    "ValueError": DSLErrorCode.VALIDATION_ERROR,
    "KeyError": DSLErrorCode.MARKET_DATA_ERROR,
}


def classify_error(error: Exception) -> DSLErrorCode:
    """Classify an exception into a DSLErrorCode.

    Args:
        error: The exception to classify

    Returns:
        Appropriate DSLErrorCode
    """
    error_type = type(error).__name__
    return DSL_ERROR_MAP.get(error_type, DSLErrorCode.VALIDATION_ERROR)


def create_dsl_error(
    error: Exception,
    path: str = "",
    line: int | None = None,
    column: int | None = None,
    suggestions: list[str] | None = None,
) -> DSLError:
    """Create a DSLError from an exception.

    Args:
        error: The exception
        path: AST path where error occurred
        line: Source line number
        column: Source column number
        suggestions: Suggested fixes

    Returns:
        Structured DSLError
    """
    code = classify_error(error)

    # Try to extract location from ParseError
    if hasattr(error, "line"):
        line = line or getattr(error, "line", None)
    if hasattr(error, "column"):
        column = column or getattr(error, "column", None)

    return DSLError(
        code=code,
        message=str(error),
        path=path,
        line=line,
        column=column,
        suggestions=suggestions,
    )


def grpc_status_from_dsl_code(code: DSLErrorCode) -> int:
    """Map DSLErrorCode to gRPC status code.

    Args:
        code: The DSL error code

    Returns:
        gRPC status code (from grpc.StatusCode values)

    gRPC status codes:
        0: OK
        3: INVALID_ARGUMENT
        5: NOT_FOUND
        13: INTERNAL
    """
    if 100 <= code.value < 200:
        # Parse errors -> INVALID_ARGUMENT
        return 3
    if 200 <= code.value < 300:
        # Validation errors -> INVALID_ARGUMENT
        return 3
    if 300 <= code.value < 400:
        # Compilation errors -> INTERNAL
        return 13
    if 400 <= code.value < 500:
        # Execution errors -> varies
        if code == DSLErrorCode.MARKET_DATA_ERROR:
            return 5  # NOT_FOUND
        return 13  # INTERNAL

    return 13  # INTERNAL for unknown
