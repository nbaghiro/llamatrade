"""Market data models (not tenant-scoped - shared data)."""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import BigInteger, DateTime, Index, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from llamatrade_db.base import Base


class Bar(Base):
    """OHLCV bar data for symbols."""

    __tablename__ = "bars"
    __table_args__ = (
        Index("ix_bars_symbol_timeframe_timestamp", "symbol", "timeframe", "timestamp"),
        Index("ix_bars_timestamp", "timestamp"),
        {"postgresql_partition_by": "RANGE (timestamp)"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    timeframe: Mapped[str] = mapped_column(
        String(10), nullable=False
    )  # 1min, 5min, 15min, 1hour, 1day
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    open: Mapped[Decimal] = mapped_column(Numeric(precision=18, scale=8), nullable=False)
    high: Mapped[Decimal] = mapped_column(Numeric(precision=18, scale=8), nullable=False)
    low: Mapped[Decimal] = mapped_column(Numeric(precision=18, scale=8), nullable=False)
    close: Mapped[Decimal] = mapped_column(Numeric(precision=18, scale=8), nullable=False)
    volume: Mapped[int] = mapped_column(BigInteger, nullable=False)
    vwap: Mapped[Decimal | None] = mapped_column(Numeric(precision=18, scale=8), nullable=True)
    trade_count: Mapped[int | None] = mapped_column(Integer, nullable=True)


class Quote(Base):
    """Quote (bid/ask) data for symbols."""

    __tablename__ = "quotes"
    __table_args__ = (
        Index("ix_quotes_symbol_timestamp", "symbol", "timestamp"),
        {"postgresql_partition_by": "RANGE (timestamp)"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    bid_price: Mapped[Decimal] = mapped_column(Numeric(precision=18, scale=8), nullable=False)
    bid_size: Mapped[int] = mapped_column(Integer, nullable=False)
    ask_price: Mapped[Decimal] = mapped_column(Numeric(precision=18, scale=8), nullable=False)
    ask_size: Mapped[int] = mapped_column(Integer, nullable=False)
    bid_exchange: Mapped[str | None] = mapped_column(String(10), nullable=True)
    ask_exchange: Mapped[str | None] = mapped_column(String(10), nullable=True)
    conditions: Mapped[str | None] = mapped_column(String(50), nullable=True)


class Trade(Base):
    """Individual trade tick data."""

    __tablename__ = "trades"
    __table_args__ = (
        Index("ix_trades_symbol_timestamp", "symbol", "timestamp"),
        {"postgresql_partition_by": "RANGE (timestamp)"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(precision=18, scale=8), nullable=False)
    size: Mapped[int] = mapped_column(Integer, nullable=False)
    exchange: Mapped[str | None] = mapped_column(String(10), nullable=True)
    trade_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    conditions: Mapped[str | None] = mapped_column(String(100), nullable=True)
    tape: Mapped[str | None] = mapped_column(String(5), nullable=True)
