"""Market Data Service - shared-model re-exports.

Core data models (Bar, Quote, Trade, Snapshot, …), streaming payload types
(TradeData/QuoteData/BarData/StreamData), and error types are the single source
of truth in the shared llamatrade_alpaca library. They are re-exported here for
import convenience. The service has no local Pydantic request/response schemas —
its API is gRPC/Connect (proto), and streaming state lives in
``src/streaming/manager.py``.
"""

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
]
