"""Alpaca API exception hierarchy."""


class AlpacaError(Exception):
    """Base exception for Alpaca API errors."""

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class AlpacaRateLimitError(AlpacaError):
    """Raised when Alpaca API rate limit is exceeded (429)."""

    def __init__(self, message: str = "Rate limit exceeded", retry_after: int | None = None):
        super().__init__(message, status_code=429)
        self.retry_after = retry_after


class AlpacaServerError(AlpacaError):
    """Raised when Alpaca API returns a server error (5xx)."""

    def __init__(self, message: str = "Alpaca server error", status_code: int = 500):
        super().__init__(message, status_code=status_code)


class SymbolNotFoundError(AlpacaError):
    """Raised when a symbol is not found or invalid (404/422)."""

    def __init__(self, symbol: str, message: str | None = None):
        super().__init__(message or f"Symbol not found: {symbol}", status_code=404)
        self.symbol = symbol


class OrderNotFoundError(AlpacaError):
    """Raised when an order is not found (404)."""

    def __init__(self, order_id: str, message: str | None = None):
        super().__init__(message or f"Order not found: {order_id}", status_code=404)
        self.order_id = order_id


class PositionNotFoundError(AlpacaError):
    """Raised when a position is not found (404)."""

    def __init__(self, symbol: str, message: str | None = None):
        super().__init__(message or f"Position not found: {symbol}", status_code=404)
        self.symbol = symbol


class InvalidRequestError(AlpacaError):
    """Raised when request parameters are invalid (400)."""

    def __init__(self, message: str = "Invalid request"):
        super().__init__(message, status_code=400)


class AuthenticationError(AlpacaError):
    """Raised when Alpaca API authentication fails (401/403)."""

    def __init__(self, message: str = "Authentication failed"):
        super().__init__(message, status_code=401)


class CircuitOpenError(Exception):
    """Raised when circuit breaker is open and requests are blocked."""

    def __init__(self, message: str = "Circuit breaker is open"):
        super().__init__(message)
        self.message = message
