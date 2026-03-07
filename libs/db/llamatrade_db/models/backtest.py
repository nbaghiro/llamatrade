"""Backtesting models.

Enum columns use PostgreSQL native ENUM types with TypeDecorators for transparent
conversion between proto int values and DB enum strings.

See libs/db/llamatrade_db/models/enum_types.py for TypeDecorator implementations.
"""

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import Date, DateTime, ForeignKey, Index, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from llamatrade_db.base import Base, TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin
from llamatrade_db.models._enum_types import BacktestStatusType


class Backtest(Base, UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin):
    """Backtest run configuration and status."""

    __tablename__ = "backtests"
    __table_args__ = (
        Index("ix_backtests_tenant_status", "tenant_id", "status"),
        Index("ix_backtests_strategy", "strategy_id"),
    )

    strategy_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    strategy_version: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[int] = mapped_column(
        BacktestStatusType(), default=1, nullable=False
    )  # PENDING=1
    config: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    symbols: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    start_date: Mapped[datetime] = mapped_column(Date, nullable=False)
    end_date: Mapped[datetime] = mapped_column(Date, nullable=False)
    initial_capital: Mapped[Decimal] = mapped_column(Numeric(precision=18, scale=2), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)

    # Relationships
    results: Mapped[list[BacktestResult]] = relationship(
        "BacktestResult", back_populates="backtest"
    )


class BacktestResult(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Backtest execution results and metrics."""

    __tablename__ = "backtest_results"

    backtest_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("backtests.id"), nullable=False, unique=True
    )

    # Performance metrics
    total_return: Mapped[Decimal] = mapped_column(Numeric(precision=18, scale=6), nullable=False)
    annual_return: Mapped[Decimal] = mapped_column(Numeric(precision=18, scale=6), nullable=False)
    sharpe_ratio: Mapped[Decimal] = mapped_column(Numeric(precision=10, scale=4), nullable=False)
    sortino_ratio: Mapped[Decimal | None] = mapped_column(
        Numeric(precision=10, scale=4), nullable=True
    )
    max_drawdown: Mapped[Decimal] = mapped_column(Numeric(precision=10, scale=6), nullable=False)
    max_drawdown_duration: Mapped[int | None] = mapped_column(Integer, nullable=True, default=0)
    win_rate: Mapped[Decimal] = mapped_column(Numeric(precision=5, scale=4), nullable=False)
    profit_factor: Mapped[Decimal | None] = mapped_column(
        Numeric(precision=10, scale=4), nullable=True
    )
    exposure_time: Mapped[Decimal | None] = mapped_column(
        Numeric(precision=5, scale=2), nullable=True
    )

    # Trade statistics
    total_trades: Mapped[int] = mapped_column(Integer, nullable=False)
    winning_trades: Mapped[int] = mapped_column(Integer, nullable=False)
    losing_trades: Mapped[int] = mapped_column(Integer, nullable=False)
    avg_trade_return: Mapped[Decimal] = mapped_column(
        Numeric(precision=18, scale=6), nullable=False
    )

    # Final state
    final_equity: Mapped[Decimal] = mapped_column(Numeric(precision=18, scale=2), nullable=False)

    # Detailed data (stored as JSON)
    equity_curve: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB, nullable=True)
    trades: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB, nullable=True)
    daily_returns: Mapped[list[float] | None] = mapped_column(JSONB, nullable=True)
    monthly_returns: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    # Benchmark comparison data
    benchmark_return: Mapped[Decimal | None] = mapped_column(
        Numeric(precision=18, scale=6), nullable=True
    )
    benchmark_symbol: Mapped[str | None] = mapped_column(String(10), nullable=True)
    alpha: Mapped[Decimal | None] = mapped_column(Numeric(precision=10, scale=6), nullable=True)
    beta: Mapped[Decimal | None] = mapped_column(Numeric(precision=10, scale=6), nullable=True)
    information_ratio: Mapped[Decimal | None] = mapped_column(
        Numeric(precision=10, scale=6), nullable=True
    )
    benchmark_equity_curve: Mapped[list[dict[str, Any]] | None] = mapped_column(
        JSONB, nullable=True
    )

    # Relationships
    backtest: Mapped[Backtest] = relationship("Backtest", back_populates="results")
