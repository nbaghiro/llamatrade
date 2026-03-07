"""Tests for authentication context extraction and symbol validation."""

from unittest.mock import MagicMock
from uuid import UUID

import pytest
from connectrpc.code import Code
from connectrpc.errors import ConnectError

from src.grpc.servicer import (
    RequestTenantContext,
    _extract_tenant_context,
    _validate_symbol,
    _validate_symbols,
)


class TestTenantContextExtraction:
    """Tests for _extract_tenant_context function."""

    def test_extract_with_valid_headers(self):
        """Test extraction with valid tenant and user headers."""
        ctx = MagicMock()
        ctx.request_headers.return_value = {
            "x-tenant-id": "12345678-1234-1234-1234-123456789012",
            "x-user-id": "87654321-4321-4321-4321-210987654321",
        }

        result = _extract_tenant_context(ctx)

        assert result.tenant_id == UUID("12345678-1234-1234-1234-123456789012")
        assert result.user_id == UUID("87654321-4321-4321-4321-210987654321")
        assert result.is_authenticated is True

    def test_extract_with_uppercase_headers(self):
        """Test extraction with uppercase header names."""
        ctx = MagicMock()
        ctx.request_headers.return_value = {
            "X-Tenant-ID": "12345678-1234-1234-1234-123456789012",
            "X-User-ID": "87654321-4321-4321-4321-210987654321",
        }

        result = _extract_tenant_context(ctx)

        assert result.tenant_id == UUID("12345678-1234-1234-1234-123456789012")
        assert result.is_authenticated is True

    def test_extract_without_headers(self):
        """Test extraction when no auth headers present."""
        ctx = MagicMock()
        ctx.request_headers.return_value = {}

        result = _extract_tenant_context(ctx)

        assert result.tenant_id is None
        assert result.user_id is None
        assert result.is_authenticated is False

    def test_extract_with_invalid_uuid(self):
        """Test extraction with invalid UUID format."""
        ctx = MagicMock()
        ctx.request_headers.return_value = {
            "x-tenant-id": "not-a-valid-uuid",
            "x-user-id": "also-not-valid",
        }

        result = _extract_tenant_context(ctx)

        assert result.tenant_id is None
        assert result.user_id is None
        assert result.is_authenticated is False

    def test_extract_with_nil_uuid(self):
        """Test extraction rejects nil UUID."""
        ctx = MagicMock()
        ctx.request_headers.return_value = {
            "x-tenant-id": "00000000-0000-0000-0000-000000000000",
            "x-user-id": "87654321-4321-4321-4321-210987654321",
        }

        result = _extract_tenant_context(ctx)

        # Nil UUID should be treated as not authenticated
        assert result.tenant_id is None
        assert result.is_authenticated is False


class TestRequestTenantContext:
    """Tests for RequestTenantContext dataclass."""

    def test_log_context_authenticated(self):
        """Test log context for authenticated request."""
        ctx = RequestTenantContext(
            tenant_id=UUID("12345678-1234-1234-1234-123456789012"),
            user_id=UUID("87654321-4321-4321-4321-210987654321"),
            is_authenticated=True,
        )

        log_ctx = ctx.log_context()

        assert log_ctx["tenant_id"] == "12345678-1234-1234-1234-123456789012"
        assert log_ctx["user_id"] == "87654321-4321-4321-4321-210987654321"
        assert log_ctx["authenticated"] == "True"

    def test_log_context_anonymous(self):
        """Test log context for anonymous request."""
        ctx = RequestTenantContext(
            tenant_id=None,
            user_id=None,
            is_authenticated=False,
        )

        log_ctx = ctx.log_context()

        assert log_ctx["tenant_id"] == "anonymous"
        assert log_ctx["user_id"] == "anonymous"
        assert log_ctx["authenticated"] == "False"


class TestSymbolValidation:
    """Tests for symbol validation functions."""

    @pytest.mark.parametrize(
        "symbol,expected",
        [
            ("AAPL", "AAPL"),
            ("aapl", "AAPL"),  # Lowercase normalized
            ("TSLA", "TSLA"),
            ("A", "A"),  # Single letter
            ("GOOGL", "GOOGL"),  # 5 letters
            (" AAPL ", "AAPL"),  # Whitespace stripped
        ],
    )
    def test_validate_valid_symbols(self, symbol, expected):
        """Test validation accepts valid symbols."""
        result = _validate_symbol(symbol)
        assert result == expected

    @pytest.mark.parametrize(
        "symbol,expected",
        [
            ("BTC/USD", "BTC/USD"),  # Crypto pair
            ("ETH/EUR", "ETH/EUR"),
            ("btc/usd", "BTC/USD"),  # Lowercase crypto
        ],
    )
    def test_validate_crypto_symbols(self, symbol, expected):
        """Test validation accepts crypto pair symbols."""
        result = _validate_symbol(symbol)
        assert result == expected

    @pytest.mark.parametrize(
        "invalid_symbol",
        [
            "",  # Empty
            "   ",  # Whitespace only
            "TOOLONG",  # 7 letters
            "AAPL123",  # Contains numbers
            "AA-PL",  # Contains hyphen
            "AA PL",  # Contains space
            "AA.PL",  # Contains dot
            "@AAPL",  # Contains special char
            "AAPL!",  # Trailing special char
        ],
    )
    def test_validate_invalid_symbols(self, invalid_symbol):
        """Test validation rejects invalid symbols."""
        with pytest.raises(ConnectError) as exc_info:
            _validate_symbol(invalid_symbol)

        assert exc_info.value.code == Code.INVALID_ARGUMENT

    def test_validate_symbol_error_message(self):
        """Test validation error includes helpful message."""
        with pytest.raises(ConnectError) as exc_info:
            _validate_symbol("INVALID123")

        assert "Invalid symbol format" in str(exc_info.value.message)
        assert "INVALID123" in str(exc_info.value.message)


class TestSymbolsValidation:
    """Tests for _validate_symbols (list validation)."""

    def test_validate_multiple_symbols(self):
        """Test validation of multiple valid symbols."""
        symbols = ["AAPL", "tsla", "GOOGL"]

        result = _validate_symbols(symbols)

        assert result == ["AAPL", "TSLA", "GOOGL"]

    def test_validate_empty_list(self):
        """Test validation rejects empty list."""
        with pytest.raises(ConnectError) as exc_info:
            _validate_symbols([])

        assert exc_info.value.code == Code.INVALID_ARGUMENT
        assert "At least one symbol is required" in str(exc_info.value.message)

    def test_validate_list_with_invalid_symbol(self):
        """Test validation fails if any symbol is invalid."""
        symbols = ["AAPL", "INVALID123", "TSLA"]

        with pytest.raises(ConnectError) as exc_info:
            _validate_symbols(symbols)

        assert exc_info.value.code == Code.INVALID_ARGUMENT
        assert "INVALID123" in str(exc_info.value.message)

    def test_validate_single_symbol_list(self):
        """Test validation of single-symbol list."""
        result = _validate_symbols(["aapl"])

        assert result == ["AAPL"]
