"""Market Data Service - Pydantic schemas and exceptions.

Core data models (Bar, Quote, Trade, etc.) and error types are imported from
the shared llamatrade_alpaca library. Service-specific request/response schemas
and streaming types are defined here.
"""

from datetime import UTC, datetime

from pydantic import BaseModel, Field

# Re-export shared models and errors for convenience. Streaming payload types
# (TradeData/QuoteData/BarData/StreamData) live in the shared llamatrade_alpaca
# library and are the single source of truth for the WebSocket wire schema.
from llamatrade_alpaca import (
    AlpacaError,
    AlpacaRateLimitError,
    AlpacaServerError,
    Bar,
    BarData,
    CircuitOpenError,
    InvalidRequestError,
    MarketClock,
    Quote,
    QuoteData,
    Snapshot,
    StreamData,
    SymbolNotFoundError,
    Timeframe,
    Trade,
    TradeData,
)

__all__ = [
    # From shared lib
    "AlpacaError",
    "AlpacaRateLimitError",
    "AlpacaServerError",
    "Bar",
    "BarData",
    "CircuitOpenError",
    "InvalidRequestError",
    "MarketClock",
    "Quote",
    "QuoteData",
    "Snapshot",
    "StreamData",
    "SymbolNotFoundError",
    "Timeframe",
    "Trade",
    "TradeData",
    # Service-specific
    "BarsRequest",
    "BarsResponse",
    "QuotesRequest",
    "StreamMessage",
    "StreamSubscription",
]


# === Service-specific Request/Response Schemas ===


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
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
