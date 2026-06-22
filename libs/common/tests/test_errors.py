"""Tests for the shared DSL/gRPC error mapping (llamatrade_common.errors)."""

from __future__ import annotations

from llamatrade_common.errors import (
    DSLError,
    DSLErrorCode,
    classify_error,
    create_dsl_error,
    grpc_status_from_dsl_code,
)


class _ParseError(Exception):
    """Stand-in for a parser error carrying location info."""

    def __init__(self, message: str, line: int, column: int) -> None:
        super().__init__(message)
        self.line = line
        self.column = column


def test_classify_known_and_unknown() -> None:
    assert classify_error(ValueError("x")) == DSLErrorCode.VALIDATION_ERROR
    assert classify_error(KeyError("x")) == DSLErrorCode.MARKET_DATA_ERROR
    # Unknown exception types fall back to VALIDATION_ERROR.
    assert classify_error(RuntimeError("x")) == DSLErrorCode.VALIDATION_ERROR


def test_create_dsl_error_extracts_location() -> None:
    err = create_dsl_error(_ParseError("bad token", line=4, column=7), path="strategy.children[0]")
    assert err.code == DSLErrorCode.VALIDATION_ERROR  # _ParseError name not in map
    assert err.message == "bad token"
    assert err.path == "strategy.children[0]"
    assert err.line == 4
    assert err.column == 7


def test_create_dsl_error_without_location() -> None:
    err = create_dsl_error(ValueError("nope"), suggestions=["fix it"])
    assert err.line is None
    assert err.column is None
    assert err.suggestions == ["fix it"]


def test_to_dict_includes_only_present_fields() -> None:
    minimal = DSLError(code=DSLErrorCode.PARSE_ERROR, message="m").to_dict()
    assert minimal == {"code": 100, "code_name": "PARSE_ERROR", "message": "m"}

    full = DSLError(
        code=DSLErrorCode.INVALID_SYNTAX,
        message="m",
        path="p",
        line=1,
        column=2,
        suggestions=["s"],
    ).to_dict()
    assert full["path"] == "p"
    assert full["line"] == 1
    assert full["column"] == 2
    assert full["suggestions"] == ["s"]


def test_grpc_status_mapping() -> None:
    assert grpc_status_from_dsl_code(DSLErrorCode.PARSE_ERROR) == 3  # INVALID_ARGUMENT
    assert grpc_status_from_dsl_code(DSLErrorCode.VALIDATION_ERROR) == 3
    assert grpc_status_from_dsl_code(DSLErrorCode.COMPILATION_ERROR) == 13  # INTERNAL
    assert grpc_status_from_dsl_code(DSLErrorCode.MARKET_DATA_ERROR) == 5  # NOT_FOUND
    assert grpc_status_from_dsl_code(DSLErrorCode.EXECUTION_ERROR) == 13
