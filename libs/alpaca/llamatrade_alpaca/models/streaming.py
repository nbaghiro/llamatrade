"""Models for Alpaca real-time streaming (WebSocket) payloads.

Two distinct Alpaca streams are represented here:

- **Market data stream** (``wss://stream.data.alpaca.markets``): trades, quotes,
  and bars delivered as lightweight ``TypedDict`` payloads (``TradeData``,
  ``QuoteData``, ``BarData``).
- **Trading (account) stream** (``wss://api.alpaca.markets/stream``):
  ``trade_updates`` order-lifecycle events represented as ``TradeEvent`` /
  ``FillData`` dataclasses.

These mirror Alpaca's wire schema and are the single source of truth shared by
the market-data and trading services.
"""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Literal, TypedDict

# =============================================================================
# Market data stream payloads
# =============================================================================


class TradeData(TypedDict):
    """Real-time trade tick from the market data stream."""

    price: float
    size: int
    exchange: str
    timestamp: str | datetime  # ISO string or datetime from Alpaca


class QuoteData(TypedDict):
    """Real-time quote (NBBO) from the market data stream."""

    bid_price: float
    bid_size: int
    ask_price: float
    ask_size: int
    timestamp: str | datetime  # ISO string or datetime from Alpaca


class BarData(TypedDict):
    """Real-time aggregate bar from the market data stream."""

    open: float
    high: float
    low: float
    close: float
    volume: int
    timestamp: str | datetime  # ISO string or datetime from Alpaca


# Union of all market data stream payload types
StreamData = TradeData | QuoteData | BarData


@dataclass
class StreamBar:
    """A real-time aggregate bar delivered as a self-contained object.

    Used by generator-style consumers (e.g. a live strategy runner) that want
    the symbol and enrichment fields on the bar itself, rather than the
    callback-style ``BarData`` payload where the symbol is passed separately.
    """

    symbol: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int
    vwap: float | None = None
    trade_count: int | None = None


# =============================================================================
# Trading (account) stream events
# =============================================================================


class TradeEventType(Enum):
    """Types of ``trade_updates`` events from Alpaca's account stream."""

    NEW = "new"
    FILL = "fill"
    PARTIAL_FILL = "partial_fill"
    CANCELED = "canceled"
    EXPIRED = "expired"
    DONE_FOR_DAY = "done_for_day"
    REPLACED = "replaced"
    REJECTED = "rejected"
    PENDING_NEW = "pending_new"
    STOPPED = "stopped"
    PENDING_CANCEL = "pending_cancel"
    PENDING_REPLACE = "pending_replace"
    CALCULATED = "calculated"
    SUSPENDED = "suspended"
    ORDER_REPLACE_REJECTED = "order_replace_rejected"
    ORDER_CANCEL_REJECTED = "order_cancel_rejected"


@dataclass
class FillData:
    """Data for a fill (or partial fill) event."""

    order_id: str
    client_order_id: str
    symbol: str
    side: Literal["buy", "sell"]
    fill_qty: Decimal
    fill_price: Decimal
    total_filled_qty: Decimal
    remaining_qty: Decimal
    timestamp: datetime
    position_qty: Decimal | None = None  # Current position after fill


@dataclass
class TradeEvent:
    """A ``trade_updates`` order-lifecycle event from Alpaca."""

    event_type: TradeEventType
    order_id: str
    client_order_id: str
    symbol: str
    side: Literal["buy", "sell"]
    order_type: str
    qty: Decimal
    filled_qty: Decimal
    filled_avg_price: Decimal | None
    timestamp: datetime
    # Fill-specific fields (only populated for fill events)
    fill: FillData | None = None
