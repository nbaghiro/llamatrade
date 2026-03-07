"""LlamaTrade Alpaca API client library.

This library provides ready-to-use clients for interacting with the Alpaca Markets API,
including market data retrieval, order submission, and position management.

Example usage:

    from llamatrade_alpaca import TradingClient, MarketDataClient

    # Trading
    trading = TradingClient(paper=True)
    order = await trading.submit_order("AAPL", qty=10, side="buy", type="market")
    positions = await trading.get_positions()

    # Market Data
    market = MarketDataClient(paper=True)
    bars = await market.get_bars("AAPL", timeframe=Timeframe.DAY_1, start=yesterday)
"""

from .client_base import AlpacaClientBase
from .clients import (
    MarketDataClient,
    TradingClient,
    close_all_clients,
    close_market_data_client,
    close_trading_client,
    get_market_data_client,
    get_market_data_client_async,
    get_trading_client,
    get_trading_client_async,
)
from .config import AlpacaCredentials, AlpacaEnvironment, AlpacaUrls
from .errors import (
    AlpacaError,
    AlpacaRateLimitError,
    AlpacaServerError,
    AuthenticationError,
    CircuitOpenError,
    InvalidRequestError,
    OrderNotFoundError,
    PositionNotFoundError,
    SymbolNotFoundError,
)
from .metrics import (
    ALPACA_API_CALLS_TOTAL,
    ALPACA_API_DURATION_SECONDS,
    HAS_PROMETHEUS,
    record_api_call,
    time_alpaca_call,
)
from .models import (
    Account,
    Bar,
    MarketClock,
    Order,
    OrderSide,
    OrderStatus,
    OrderType,
    Position,
    PositionSide,
    Quote,
    Snapshot,
    Timeframe,
    TimeInForce,
    Trade,
    parse_account,
    parse_bar,
    parse_clock,
    parse_order,
    parse_position,
    parse_quote,
    parse_snapshot,
    parse_timestamp,
    parse_trade,
)
from .resilience import (
    CircuitBreaker,
    CircuitState,
    RateLimiter,
    RetryConfig,
    create_market_data_resilience,
    create_trading_resilience,
    parse_alpaca_error,
    retry_with_backoff,
)

__all__ = [
    # Base client
    "AlpacaClientBase",
    # Config
    "AlpacaCredentials",
    "AlpacaEnvironment",
    "AlpacaUrls",
    # Errors
    "AlpacaError",
    "AlpacaRateLimitError",
    "AlpacaServerError",
    "AuthenticationError",
    "CircuitOpenError",
    "InvalidRequestError",
    "OrderNotFoundError",
    "PositionNotFoundError",
    "SymbolNotFoundError",
    # Market Data Models
    "Bar",
    "Quote",
    "Snapshot",
    "Timeframe",
    "Trade",
    "parse_bar",
    "parse_quote",
    "parse_snapshot",
    "parse_timestamp",
    "parse_trade",
    # Trading Models
    "Account",
    "MarketClock",
    "Order",
    "OrderSide",
    "OrderStatus",
    "OrderType",
    "Position",
    "PositionSide",
    "TimeInForce",
    "parse_account",
    "parse_clock",
    "parse_order",
    "parse_position",
    # Resilience
    "CircuitBreaker",
    "CircuitState",
    "RateLimiter",
    "RetryConfig",
    "create_market_data_resilience",
    "create_trading_resilience",
    "parse_alpaca_error",
    "retry_with_backoff",
    # Metrics
    "ALPACA_API_CALLS_TOTAL",
    "ALPACA_API_DURATION_SECONDS",
    "HAS_PROMETHEUS",
    "record_api_call",
    "time_alpaca_call",
    # Clients
    "MarketDataClient",
    "TradingClient",
    # Singleton helpers (sync - for FastAPI Depends)
    "get_trading_client",
    "get_market_data_client",
    # Singleton helpers (async - for gRPC/concurrent contexts)
    "get_trading_client_async",
    "get_market_data_client_async",
    # Close helpers
    "close_trading_client",
    "close_market_data_client",
    "close_all_clients",
]

__version__ = "0.1.0"
