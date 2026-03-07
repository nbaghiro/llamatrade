"""Tests for errors module."""

from llamatrade_alpaca import (
    AlpacaError,
    AlpacaRateLimitError,
    AlpacaServerError,
    AuthenticationError,
    CircuitOpenError,
    InvalidRequestError,
    SymbolNotFoundError,
)


class TestAlpacaError:
    """Tests for AlpacaError base class."""

    def test_basic_error(self) -> None:
        """Test basic error creation."""
        error = AlpacaError("test message")
        assert str(error) == "test message"
        assert error.message == "test message"
        assert error.status_code is None

    def test_error_with_status_code(self) -> None:
        """Test error with status code."""
        error = AlpacaError("test message", status_code=500)
        assert error.status_code == 500


class TestAlpacaRateLimitError:
    """Tests for AlpacaRateLimitError."""

    def test_default_message(self) -> None:
        """Test default error message."""
        error = AlpacaRateLimitError()
        assert error.message == "Rate limit exceeded"
        assert error.status_code == 429
        assert error.retry_after is None

    def test_custom_message_and_retry_after(self) -> None:
        """Test custom message with retry_after."""
        error = AlpacaRateLimitError("Custom message", retry_after=60)
        assert error.message == "Custom message"
        assert error.retry_after == 60


class TestAlpacaServerError:
    """Tests for AlpacaServerError."""

    def test_default_values(self) -> None:
        """Test default error values."""
        error = AlpacaServerError()
        assert error.message == "Alpaca server error"
        assert error.status_code == 500

    def test_custom_status_code(self) -> None:
        """Test custom status code."""
        error = AlpacaServerError("Gateway timeout", status_code=504)
        assert error.status_code == 504


class TestSymbolNotFoundError:
    """Tests for SymbolNotFoundError."""

    def test_with_symbol_only(self) -> None:
        """Test error with just symbol."""
        error = SymbolNotFoundError("INVALID")
        assert error.symbol == "INVALID"
        assert error.message == "Symbol not found: INVALID"
        assert error.status_code == 404

    def test_with_custom_message(self) -> None:
        """Test error with custom message."""
        error = SymbolNotFoundError("XYZ", "No data available for XYZ")
        assert error.symbol == "XYZ"
        assert error.message == "No data available for XYZ"


class TestInvalidRequestError:
    """Tests for InvalidRequestError."""

    def test_default_message(self) -> None:
        """Test default error message."""
        error = InvalidRequestError()
        assert error.message == "Invalid request"
        assert error.status_code == 400

    def test_custom_message(self) -> None:
        """Test custom error message."""
        error = InvalidRequestError("Missing required parameter: symbol")
        assert error.message == "Missing required parameter: symbol"


class TestAuthenticationError:
    """Tests for AuthenticationError."""

    def test_default_message(self) -> None:
        """Test default error message."""
        error = AuthenticationError()
        assert error.message == "Authentication failed"
        assert error.status_code == 401

    def test_custom_message(self) -> None:
        """Test custom error message."""
        error = AuthenticationError("Invalid API key")
        assert error.message == "Invalid API key"


class TestCircuitOpenError:
    """Tests for CircuitOpenError."""

    def test_default_message(self) -> None:
        """Test default error message."""
        error = CircuitOpenError()
        assert error.message == "Circuit breaker is open"
        assert str(error) == "Circuit breaker is open"

    def test_custom_message(self) -> None:
        """Test custom error message."""
        error = CircuitOpenError("Service unavailable, retry in 60s")
        assert error.message == "Service unavailable, retry in 60s"

    def test_not_alpaca_error_subclass(self) -> None:
        """Test CircuitOpenError is not an AlpacaError subclass."""
        error = CircuitOpenError()
        assert not isinstance(error, AlpacaError)
