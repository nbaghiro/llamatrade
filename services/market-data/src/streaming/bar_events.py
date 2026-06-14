"""Wire codec for live minute bars on the internal EventBus.

The ingest role publishes closed minute bars to a single Redis stream; the
serving role's fan-out tails it and routes to subscribed clients. Fields are
flat strings (Redis Streams' native model). Kept pure + symmetric so the codec
is unit-testable without Redis.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from src.store.models import BarRow

# Single global stream for live minute bars; routing by symbol happens in the
# fan-out (XREADGROUP has no pattern-subscribe, and one stream preserves order).
BAR_STREAM = "market:bars:1m"
BAR_STREAM_MAXLEN = 50_000


def encode_bar_event(row: BarRow) -> dict[str, str]:
    """Serialize a minute bar to flat stream fields."""
    fields = {
        "symbol": row.symbol,
        "t": row.time.isoformat(),
        "o": str(row.open),
        "h": str(row.high),
        "l": str(row.low),
        "c": str(row.close),
        "v": str(row.volume),
    }
    if row.vwap is not None:
        fields["vw"] = str(row.vwap)
    if row.trade_count is not None:
        fields["n"] = str(row.trade_count)
    return fields


def decode_bar_event(fields: dict[str, str]) -> BarRow:
    """Inverse of :func:`encode_bar_event`."""
    return BarRow(
        symbol=fields["symbol"],
        time=datetime.fromisoformat(fields["t"]),
        open=Decimal(fields["o"]),
        high=Decimal(fields["h"]),
        low=Decimal(fields["l"]),
        close=Decimal(fields["c"]),
        volume=int(fields["v"]),
        vwap=Decimal(fields["vw"]) if "vw" in fields else None,
        trade_count=int(fields["n"]) if "n" in fields else None,
    )
