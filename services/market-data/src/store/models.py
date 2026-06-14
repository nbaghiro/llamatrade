"""Schema + domain types for the Timescale bar store.

SQLAlchemy Core (not ORM) is used deliberately: the write path is bulk upserts
of the per-minute fan-out burst, and Core ``insert().on_conflict_do_update``
expresses that cleanly without session/identity-map overhead. The tables here
mirror what the SQL migrations create; the migrations also convert them to
Timescale hypertables and attach continuous aggregates + retention policies
(which Core/DDL-reflection does not model).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, Protocol

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    Integer,
    MetaData,
    Numeric,
    String,
    Table,
    UniqueConstraint,
)

metadata = MetaData()

_PRICE = Numeric(precision=18, scale=8)


def _ohlcv_columns() -> list[Column[Any]]:
    """Fresh Column instances for the shared OHLCV shape.

    Must return new objects on each call — a Column may belong to only one
    Table, so the two bar tables cannot share instances.
    """
    return [
        Column("time", DateTime(timezone=True), nullable=False),
        Column("symbol", String(20), nullable=False),
        Column("open", _PRICE, nullable=False),
        Column("high", _PRICE, nullable=False),
        Column("low", _PRICE, nullable=False),
        Column("close", _PRICE, nullable=False),
        Column("volume", BigInteger, nullable=False),
        Column("vwap", _PRICE, nullable=True),
        Column("trade_count", Integer, nullable=True),
    ]


# Raw minute bars (unadjusted): hypertable, short retention + compression.
bars_1m = Table(
    "bars_1m",
    metadata,
    *_ohlcv_columns(),
    UniqueConstraint("symbol", "time", name="uq_bars_1m_symbol_time"),
)

# Official adjusted daily bars: hypertable, retained indefinitely. The
# ``adjustment``/``fetched_at`` columns drive the corporate-action self-heal.
bars_daily = Table(
    "bars_daily",
    metadata,
    *_ohlcv_columns(),
    Column("adjustment", String(10), nullable=False, server_default="raw"),
    Column("fetched_at", DateTime(timezone=True), nullable=True),
    UniqueConstraint("symbol", "time", name="uq_bars_daily_symbol_time"),
)

# Timeframes backed by a physical base table (others are continuous aggregates,
# read-only, queried by name — see repository.read_relation).
BASE_TABLE_BY_TIMEFRAME: dict[str, Table] = {
    "1Min": bars_1m,
    "1Day": bars_daily,
}

# Read-only relations for derived timeframes (continuous aggregates from
# migrations). Keys are the canonical Timeframe enum values, so the service can
# pass ``timeframe.value`` straight through with no translation.
AGGREGATE_RELATION_BY_TIMEFRAME: dict[str, str] = {
    "5Min": "bars_5m",
    "15Min": "bars_15m",
    "30Min": "bars_30m",
    "1Hour": "bars_1h",
    "4Hour": "bars_4h",
    "1Week": "bars_1w",
    "1Month": "bars_1mo",
}


@dataclass(frozen=True, slots=True)
class BarRow:
    """One stored bar. The store's domain type — independent of Alpaca/proto."""

    symbol: str
    time: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int
    vwap: Decimal | None = None
    trade_count: int | None = None


class _AlpacaBarLike(Protocol):
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int
    vwap: float | None
    trade_count: int | None


def _decimal(value: float | Decimal) -> Decimal:
    # via str so we store the decimal the source intended, not a float artifact
    return value if isinstance(value, Decimal) else Decimal(str(value))


def _to_decimal(value: float | Decimal | None) -> Decimal | None:
    return None if value is None else _decimal(value)


def bar_row_from_alpaca(symbol: str, bar: _AlpacaBarLike) -> BarRow:
    """Convert an Alpaca ``Bar`` (no symbol, float prices) into a ``BarRow``."""
    return BarRow(
        symbol=symbol,
        time=bar.timestamp,
        open=_decimal(bar.open),
        high=_decimal(bar.high),
        low=_decimal(bar.low),
        close=_decimal(bar.close),
        volume=int(bar.volume),
        vwap=_to_decimal(bar.vwap),
        trade_count=bar.trade_count,
    )
