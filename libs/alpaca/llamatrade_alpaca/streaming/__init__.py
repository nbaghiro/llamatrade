"""Alpaca WebSocket streaming clients.

- ``MarketDataStreamClient`` — real-time trades/quotes/bars (callback delivery).
- ``TradingStreamClient`` — ``trade_updates`` order events (generator delivery).
- ``MockTradeStream`` — in-memory trade stream for tests.
"""

from .base import AlpacaWebSocketBase
from .market_data_stream import (
    BarCallback,
    BarStreamClient,
    MarketDataStreamClient,
    MessageType,
    MockBarStream,
    QuoteCallback,
    TradeCallback,
    close_market_data_stream,
    get_market_data_stream,
    init_market_data_stream,
)
from .trading_stream import MockTradeStream, TradingStreamClient

__all__ = [
    "AlpacaWebSocketBase",
    # Market data stream
    "MarketDataStreamClient",
    "MessageType",
    "TradeCallback",
    "QuoteCallback",
    "BarCallback",
    "get_market_data_stream",
    "init_market_data_stream",
    "close_market_data_stream",
    # Bar stream (generator-based)
    "BarStreamClient",
    "MockBarStream",
    # Trading stream
    "TradingStreamClient",
    "MockTradeStream",
]
