"""Market Data Service - Pydantic schemas and exceptions."""

from datetime import datetime
from enum import StrEnum
from typing import TypedDict

from pydantic import BaseModel, Field

# === Custom Exceptions ===


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


class InvalidRequestError(AlpacaError):
    """Raised when request parameters are invalid (400)."""

    def __init__(self, message: str = "Invalid request"):
        super().__init__(message, status_code=400)


class CircuitOpenError(Exception):
    """Raised when circuit breaker is open and requests are blocked."""

    def __init__(self, message: str = "Circuit breaker is open"):
        super().__init__(message)
        self.message = message


class TradeData(TypedDict):
    """Trade data for streaming."""

    price: float
    size: int
    exchange: str
    timestamp: str


class QuoteData(TypedDict):
    """Quote data for streaming."""

    bid_price: float
    bid_size: int
    ask_price: float
    ask_size: int
    timestamp: str


class BarData(TypedDict):
    """Bar data for streaming."""

    open: float
    high: float
    low: float
    close: float
    volume: int
    timestamp: str


# Union of all streaming data types
StreamData = TradeData | QuoteData | BarData


class Timeframe(StrEnum):
    """Supported timeframes."""

    MINUTE_1 = "1Min"
    MINUTE_5 = "5Min"
    MINUTE_15 = "15Min"
    MINUTE_30 = "30Min"
    HOUR_1 = "1Hour"
    HOUR_4 = "4Hour"
    DAY_1 = "1Day"
    WEEK_1 = "1Week"


class Bar(BaseModel):
    """OHLCV bar data."""

    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int
    vwap: float | None = None
    trade_count: int | None = None


class Quote(BaseModel):
    """Quote data."""

    symbol: str
    bid_price: float
    bid_size: int
    ask_price: float
    ask_size: int
    timestamp: datetime


class Trade(BaseModel):
    """Trade data."""

    symbol: str
    price: float
    size: int
    timestamp: datetime
    exchange: str | None = None


class Snapshot(BaseModel):
    """Market snapshot for a symbol."""

    symbol: str
    latest_trade: Trade | None = None
    latest_quote: Quote | None = None
    minute_bar: Bar | None = None
    daily_bar: Bar | None = None
    prev_daily_bar: Bar | None = None


class BarsRequest(BaseModel):
    """Request for historical bars."""

    symbols: list[str]
    timeframe: Timeframe = Timeframe.DAY_1
    start: datetime
    end: datetime | None = None
    limit: int = Field(default=1000, ge=1, le=10000)
    adjustment: str = "raw"  # raw, split, dividend, all


class BarsResponse(BaseModel):
    """Response containing historical bars."""

    bars: dict[str, list[Bar]]
    next_page_token: str | None = None


class QuotesRequest(BaseModel):
    """Request for latest quotes."""

    symbols: list[str]


class StreamSubscription(BaseModel):
    """WebSocket stream subscription request."""

    action: str  # subscribe, unsubscribe
    trades: list[str] | None = None
    quotes: list[str] | None = None
    bars: list[str] | None = None


class StreamMessage(BaseModel):
    """WebSocket stream message."""

    type: str  # trade, quote, bar, error
    symbol: str | None = None
    data: StreamData | dict[str, str] = Field(
        default_factory=dict
    )  # dict[str, str] for error messages
    timestamp: datetime = Field(default_factory=datetime.utcnow)
