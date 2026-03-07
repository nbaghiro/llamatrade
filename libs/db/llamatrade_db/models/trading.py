"""Trading execution models.

Enum columns use PostgreSQL native ENUM types with TypeDecorators for transparent
conversion between proto int values and DB enum strings.

Service code uses proto int constants (ORDER_STATUS_FILLED = 5), while the database
stores human-readable enum values ('filled').

See libs/db/llamatrade_db/models/enum_types.py for TypeDecorator implementations.
"""

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from llamatrade_db.base import Base, TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin
from llamatrade_db.models._enum_types import (
    ExecutionModeType,
    OrderSideType,
    OrderStatusType,
    OrderTypeType,
    PositionSideType,
    SessionStatusType,
    TimeInForceType,
)


class TradingSession(Base, UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin):
    """Live or paper trading session."""

    __tablename__ = "trading_sessions"
    __table_args__ = (
        Index("ix_trading_sessions_tenant_status", "tenant_id", "status"),
        Index("ix_trading_sessions_strategy", "strategy_id"),
    )

    strategy_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    strategy_version: Mapped[int] = mapped_column(Integer, nullable=False)
    credentials_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    mode: Mapped[int] = mapped_column(ExecutionModeType(), nullable=False)
    status: Mapped[int] = mapped_column(SessionStatusType(), default=3, nullable=False)  # STOPPED=3
    config: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    symbols: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    stopped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_heartbeat: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)

    # Relationships
    orders: Mapped[list[Order]] = relationship("Order", back_populates="session")
    positions: Mapped[list[Position]] = relationship("Position", back_populates="session")


class Order(Base, UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin):
    """Order placed through trading session."""

    __tablename__ = "orders"
    __table_args__ = (
        Index("ix_orders_tenant_status", "tenant_id", "status"),
        Index("ix_orders_session", "session_id"),
        Index("ix_orders_symbol", "symbol"),
        Index("ix_orders_alpaca_order_id", "alpaca_order_id"),
        Index("ix_orders_parent", "parent_order_id"),
    )

    session_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("trading_sessions.id"), nullable=False
    )
    alpaca_order_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    client_order_id: Mapped[str] = mapped_column(String(100), nullable=False)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    side: Mapped[int] = mapped_column(OrderSideType(), nullable=False)
    order_type: Mapped[int] = mapped_column(OrderTypeType(), nullable=False)
    time_in_force: Mapped[int] = mapped_column(TimeInForceType(), nullable=False)
    qty: Mapped[Decimal] = mapped_column(Numeric(precision=18, scale=8), nullable=False)
    limit_price: Mapped[Decimal | None] = mapped_column(
        Numeric(precision=18, scale=8), nullable=True
    )
    stop_price: Mapped[Decimal | None] = mapped_column(
        Numeric(precision=18, scale=8), nullable=True
    )
    status: Mapped[int] = mapped_column(OrderStatusType(), nullable=False)
    filled_qty: Mapped[Decimal] = mapped_column(
        Numeric(precision=18, scale=8), default=Decimal("0"), nullable=False
    )
    filled_avg_price: Mapped[Decimal | None] = mapped_column(
        Numeric(precision=18, scale=8), nullable=True
    )
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    filled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    canceled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    signal_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSONB, nullable=True)

    # Bracket order fields (stop-loss/take-profit)
    parent_order_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("orders.id"), nullable=True
    )
    bracket_type: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )  # BracketType: stop_loss=1, take_profit=2
    stop_loss_price: Mapped[Decimal | None] = mapped_column(
        Numeric(precision=18, scale=8), nullable=True
    )
    take_profit_price: Mapped[Decimal | None] = mapped_column(
        Numeric(precision=18, scale=8), nullable=True
    )

    # Relationships
    session: Mapped[TradingSession] = relationship("TradingSession", back_populates="orders")
    parent_order: Mapped[Order | None] = relationship(
        "Order",
        remote_side="Order.id",
        back_populates="bracket_orders",
        foreign_keys=[parent_order_id],
    )
    bracket_orders: Mapped[list[Order]] = relationship(
        "Order", back_populates="parent_order", foreign_keys=[parent_order_id]
    )


class Position(Base, UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin):
    """Current position in a trading session."""

    __tablename__ = "positions"
    __table_args__ = (Index("ix_positions_session_symbol", "session_id", "symbol", unique=True),)

    session_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("trading_sessions.id"), nullable=False
    )
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    side: Mapped[int] = mapped_column(PositionSideType(), nullable=False)
    qty: Mapped[Decimal] = mapped_column(Numeric(precision=18, scale=8), nullable=False)
    avg_entry_price: Mapped[Decimal] = mapped_column(Numeric(precision=18, scale=8), nullable=False)
    current_price: Mapped[Decimal | None] = mapped_column(
        Numeric(precision=18, scale=8), nullable=True
    )
    market_value: Mapped[Decimal | None] = mapped_column(
        Numeric(precision=18, scale=2), nullable=True
    )
    cost_basis: Mapped[Decimal] = mapped_column(Numeric(precision=18, scale=2), nullable=False)
    unrealized_pl: Mapped[Decimal | None] = mapped_column(
        Numeric(precision=18, scale=2), nullable=True
    )
    unrealized_plpc: Mapped[Decimal | None] = mapped_column(
        Numeric(precision=10, scale=6), nullable=True
    )
    realized_pl: Mapped[Decimal] = mapped_column(
        Numeric(precision=18, scale=2), default=Decimal("0"), nullable=False
    )
    is_open: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    session: Mapped[TradingSession] = relationship("TradingSession", back_populates="positions")
