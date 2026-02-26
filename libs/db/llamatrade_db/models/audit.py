"""Audit and compliance models for trading event logging."""

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import DateTime, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from llamatrade_db.base import Base, TenantMixin, UUIDPrimaryKeyMixin


class AuditEventType(StrEnum):
    """Types of auditable events."""

    # Signal events
    SIGNAL_GENERATED = "signal_generated"
    SIGNAL_REJECTED = "signal_rejected"

    # Order events
    ORDER_SUBMITTED = "order_submitted"
    ORDER_FILLED = "order_filled"
    ORDER_PARTIAL_FILL = "order_partial_fill"
    ORDER_CANCELLED = "order_cancelled"
    ORDER_REJECTED = "order_rejected"
    ORDER_EXPIRED = "order_expired"

    # Position events
    POSITION_OPENED = "position_opened"
    POSITION_CLOSED = "position_closed"
    POSITION_UPDATED = "position_updated"

    # Risk events
    RISK_CHECK_PASSED = "risk_check_passed"
    RISK_CHECK_FAILED = "risk_check_failed"
    RISK_LIMIT_BREACH = "risk_limit_breach"

    # Session events
    SESSION_STARTED = "session_started"
    SESSION_PAUSED = "session_paused"
    SESSION_RESUMED = "session_resumed"
    SESSION_STOPPED = "session_stopped"
    SESSION_ERROR = "session_error"

    # System events
    STRATEGY_LOADED = "strategy_loaded"
    STRATEGY_ERROR = "strategy_error"
    CONNECTION_LOST = "connection_lost"
    CONNECTION_RESTORED = "connection_restored"


class AuditLog(Base, UUIDPrimaryKeyMixin, TenantMixin):
    """Immutable audit log for all trading events.

    This table is append-only for compliance purposes.
    Events are never updated or deleted.
    """

    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_logs_tenant_timestamp", "tenant_id", "timestamp"),
        Index("ix_audit_logs_session", "session_id"),
        Index("ix_audit_logs_event_type", "event_type"),
        Index("ix_audit_logs_symbol", "symbol"),
    )

    # Event identification
    session_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # Event context
    symbol: Mapped[str | None] = mapped_column(String(20), nullable=True)
    order_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)

    # Event details (JSON blob for flexibility)
    data: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    # Human-readable summary
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Source information
    source: Mapped[str | None] = mapped_column(String(100), nullable=True)


class RiskConfig(Base, UUIDPrimaryKeyMixin, TenantMixin):
    """Risk configuration per tenant or session.

    Defines trading limits and risk parameters.
    """

    __tablename__ = "risk_configs"
    __table_args__ = (Index("ix_risk_configs_tenant_session", "tenant_id", "session_id"),)

    # Optional session-specific config (null = tenant-wide default)
    session_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)

    # Position limits
    max_position_size_pct: Mapped[float | None] = mapped_column(nullable=True)
    max_position_value: Mapped[float | None] = mapped_column(nullable=True)
    max_positions: Mapped[int | None] = mapped_column(nullable=True)

    # Loss limits
    max_daily_loss_pct: Mapped[float | None] = mapped_column(nullable=True)
    max_daily_loss_value: Mapped[float | None] = mapped_column(nullable=True)
    max_drawdown_pct: Mapped[float | None] = mapped_column(nullable=True)

    # Order limits
    max_order_value: Mapped[float | None] = mapped_column(nullable=True)
    max_orders_per_minute: Mapped[int | None] = mapped_column(nullable=True)
    max_orders_per_day: Mapped[int | None] = mapped_column(nullable=True)

    # Symbol restrictions (null = all symbols allowed)
    allowed_symbols: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    blocked_symbols: Mapped[list | None] = mapped_column(JSONB, nullable=True)

    # Active flag
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)


class DailyPnL(Base, UUIDPrimaryKeyMixin, TenantMixin):
    """Daily P&L tracking for risk management.

    Tracks realized and unrealized P&L per session per day.
    """

    __tablename__ = "daily_pnl"
    __table_args__ = (
        Index("ix_daily_pnl_tenant_date", "tenant_id", "date"),
        Index("ix_daily_pnl_session_date", "session_id", "date", unique=True),
    )

    session_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # P&L components
    realized_pnl: Mapped[float] = mapped_column(default=0.0, nullable=False)
    unrealized_pnl: Mapped[float] = mapped_column(default=0.0, nullable=False)
    total_pnl: Mapped[float] = mapped_column(default=0.0, nullable=False)

    # High water mark tracking
    equity_start: Mapped[float] = mapped_column(nullable=False)
    equity_high: Mapped[float] = mapped_column(nullable=False)
    equity_low: Mapped[float] = mapped_column(nullable=False)
    equity_end: Mapped[float | None] = mapped_column(nullable=True)

    # Drawdown
    max_drawdown_pct: Mapped[float] = mapped_column(default=0.0, nullable=False)

    # Trade stats
    trades_count: Mapped[int] = mapped_column(default=0, nullable=False)
    winning_trades: Mapped[int] = mapped_column(default=0, nullable=False)
    losing_trades: Mapped[int] = mapped_column(default=0, nullable=False)
