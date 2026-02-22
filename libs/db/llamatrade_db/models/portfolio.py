"""Portfolio management models."""

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Date, DateTime, Index, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from llamatrade_db.base import Base, TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin


class PortfolioSummary(Base, UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin):
    """Aggregated portfolio summary for a tenant."""

    __tablename__ = "portfolio_summary"

    # Account values
    equity: Mapped[Decimal] = mapped_column(Numeric(precision=18, scale=2), nullable=False)
    cash: Mapped[Decimal] = mapped_column(Numeric(precision=18, scale=2), nullable=False)
    buying_power: Mapped[Decimal] = mapped_column(Numeric(precision=18, scale=2), nullable=False)
    portfolio_value: Mapped[Decimal] = mapped_column(Numeric(precision=18, scale=2), nullable=False)

    # P&L
    daily_pl: Mapped[Decimal] = mapped_column(
        Numeric(precision=18, scale=2), default=Decimal("0"), nullable=False
    )
    daily_pl_percent: Mapped[Decimal] = mapped_column(
        Numeric(precision=10, scale=6), default=Decimal("0"), nullable=False
    )
    total_pl: Mapped[Decimal] = mapped_column(
        Numeric(precision=18, scale=2), default=Decimal("0"), nullable=False
    )
    total_pl_percent: Mapped[Decimal] = mapped_column(
        Numeric(precision=10, scale=6), default=Decimal("0"), nullable=False
    )

    # Positions summary
    positions: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    position_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Transaction(Base, UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin):
    """Individual transaction record."""

    __tablename__ = "transactions"
    __table_args__ = (
        Index("ix_transactions_tenant_date", "tenant_id", "transaction_date"),
        Index("ix_transactions_symbol", "symbol"),
        Index("ix_transactions_type", "transaction_type"),
    )

    session_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    order_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    transaction_type: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # fill, dividend, fee, transfer, etc.
    symbol: Mapped[str | None] = mapped_column(String(20), nullable=True)
    side: Mapped[str | None] = mapped_column(String(10), nullable=True)  # buy, sell
    qty: Mapped[Decimal | None] = mapped_column(Numeric(precision=18, scale=8), nullable=True)
    price: Mapped[Decimal | None] = mapped_column(Numeric(precision=18, scale=8), nullable=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(precision=18, scale=2), nullable=False)
    fees: Mapped[Decimal] = mapped_column(
        Numeric(precision=18, scale=4), default=Decimal("0"), nullable=False
    )
    net_amount: Mapped[Decimal] = mapped_column(Numeric(precision=18, scale=2), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    transaction_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    settlement_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    external_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)


class PortfolioHistory(Base, UUIDPrimaryKeyMixin, TenantMixin):
    """Daily portfolio snapshots for historical tracking."""

    __tablename__ = "portfolio_history"
    __table_args__ = (
        Index("ix_portfolio_history_tenant_date", "tenant_id", "snapshot_date", unique=True),
    )

    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False)
    equity: Mapped[Decimal] = mapped_column(Numeric(precision=18, scale=2), nullable=False)
    cash: Mapped[Decimal] = mapped_column(Numeric(precision=18, scale=2), nullable=False)
    portfolio_value: Mapped[Decimal] = mapped_column(Numeric(precision=18, scale=2), nullable=False)
    daily_return: Mapped[Decimal | None] = mapped_column(
        Numeric(precision=10, scale=6), nullable=True
    )
    cumulative_return: Mapped[Decimal | None] = mapped_column(
        Numeric(precision=10, scale=6), nullable=True
    )
    positions_snapshot: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default="now()", nullable=False
    )


class PerformanceMetrics(Base, UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin):
    """Calculated performance metrics for a tenant."""

    __tablename__ = "performance_metrics"
    __table_args__ = (
        Index("ix_performance_metrics_tenant_period", "tenant_id", "period_type", "period_start"),
    )

    period_type: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # daily, weekly, monthly, yearly, all_time
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)

    # Returns
    total_return: Mapped[Decimal] = mapped_column(Numeric(precision=18, scale=6), nullable=False)
    annualized_return: Mapped[Decimal | None] = mapped_column(
        Numeric(precision=18, scale=6), nullable=True
    )

    # Risk metrics
    volatility: Mapped[Decimal | None] = mapped_column(
        Numeric(precision=10, scale=6), nullable=True
    )
    sharpe_ratio: Mapped[Decimal | None] = mapped_column(
        Numeric(precision=10, scale=4), nullable=True
    )
    sortino_ratio: Mapped[Decimal | None] = mapped_column(
        Numeric(precision=10, scale=4), nullable=True
    )
    max_drawdown: Mapped[Decimal | None] = mapped_column(
        Numeric(precision=10, scale=6), nullable=True
    )
    calmar_ratio: Mapped[Decimal | None] = mapped_column(
        Numeric(precision=10, scale=4), nullable=True
    )

    # Trade statistics
    total_trades: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    winning_trades: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    losing_trades: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    win_rate: Mapped[Decimal | None] = mapped_column(Numeric(precision=5, scale=4), nullable=True)
    profit_factor: Mapped[Decimal | None] = mapped_column(
        Numeric(precision=10, scale=4), nullable=True
    )

    # P&L
    realized_pl: Mapped[Decimal] = mapped_column(
        Numeric(precision=18, scale=2), default=Decimal("0"), nullable=False
    )
    unrealized_pl: Mapped[Decimal] = mapped_column(
        Numeric(precision=18, scale=2), default=Decimal("0"), nullable=False
    )
