"""Strategy management models.

Enum columns use PostgreSQL native ENUM types with TypeDecorators for transparent
conversion between proto int values and DB enum strings.

StrategyType remains as a Python Enum because it represents business categories
(TREND_FOLLOWING, MOMENTUM, etc.) which are not proto-defined.

See libs/db/llamatrade_db/models/_enum_types.py for TypeDecorator implementations.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum as PyEnum
from typing import Any
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from llamatrade_db.base import Base, TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin
from llamatrade_db.models._enum_types import (
    ExecutionModeType,
    ExecutionStatusType,
    StrategyStatusType,
)
from llamatrade_proto.generated import common_pb2, strategy_pb2


class StrategyType(PyEnum):
    """Types of trading strategies (business categorization, not proto-defined)."""

    TREND_FOLLOWING = "trend_following"
    MEAN_REVERSION = "mean_reversion"
    MOMENTUM = "momentum"
    BREAKOUT = "breakout"
    CUSTOM = "custom"


class Strategy(Base, UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin):
    """
    Trading strategy definition.

    Stores metadata about a strategy. The actual configuration is stored
    in StrategyVersion records, with current_version pointing to the active version.
    """

    __tablename__ = "strategies"
    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_strategy_tenant_name"),
        Index("ix_strategies_tenant_name", "tenant_id", "name"),
        Index("ix_strategies_tenant_status", "tenant_id", "status"),
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[strategy_pb2.StrategyStatus.ValueType] = mapped_column(
        StrategyStatusType(), nullable=False, default=1
    )  # DRAFT=1
    is_public: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    current_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_by: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)

    # Relationships
    versions: Mapped[list[StrategyVersion]] = relationship(
        "StrategyVersion",
        back_populates="strategy",
        cascade="all, delete-orphan",
        order_by="StrategyVersion.version.desc()",
    )
    executions: Mapped[list[StrategyExecution]] = relationship(
        "StrategyExecution",
        back_populates="strategy",
        cascade="all, delete-orphan",
    )


class StrategyVersion(Base, UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin):
    """Immutable version snapshot of a strategy.

    ``config_sexpr`` (the DSL string) is the single source of truth; the JSON IR and visual tree
    are derived from it on demand. ``symbols``/``rebalance`` are projections recomputed from it on
    write (for list display/filtering). tenant_id is defense-in-depth isolation (already scoped via
    strategy_id).
    """

    __tablename__ = "strategy_versions"
    __table_args__ = (
        UniqueConstraint("strategy_id", "version", name="uq_version_strategy_version"),
        CheckConstraint("version > 0", name="ck_version_positive"),
        Index("ix_strategy_versions_strategy_version", "strategy_id", "version", unique=True),
        Index("ix_strategy_versions_symbols", "symbols", postgresql_using="gin"),
        Index("ix_strategy_versions_tenant", "tenant_id"),
    )

    strategy_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("strategies.id"), nullable=False, index=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)

    # The DSL string — the single stored representation of the strategy.
    config_sexpr: Mapped[str] = mapped_column(Text, nullable=False)

    # Projections derived from the DSL on write, for efficient filtering (symbols is GIN-indexed).
    symbols: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    rebalance: Mapped[str] = mapped_column(String(20), nullable=False, default="daily")

    changelog: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)

    # Relationships
    strategy: Mapped[Strategy] = relationship("Strategy", back_populates="versions")


class StrategyExecution(Base, UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin):
    """
    Links a strategy version to live or paper trading.

    Tracks the execution state of a strategy - whether it's running,
    paused, or stopped, and which version is being executed.
    """

    __tablename__ = "strategy_executions"
    __table_args__ = (
        Index("ix_executions_tenant_status", "tenant_id", "status"),
        Index("ix_executions_strategy", "strategy_id"),
    )

    strategy_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("strategies.id"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)

    mode: Mapped[common_pb2.ExecutionMode.ValueType] = mapped_column(
        ExecutionModeType(), nullable=False
    )
    status: Mapped[common_pb2.ExecutionStatus.ValueType] = mapped_column(
        ExecutionStatusType(), nullable=False, default=1
    )  # PENDING=1

    started_at: Mapped[datetime | None] = mapped_column(nullable=True)
    stopped_at: Mapped[datetime | None] = mapped_column(nullable=True)

    # Runtime configuration overrides (e.g., different symbols, risk params)
    config_override: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    # Error info if status is ERROR
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Capital allocated when the execution is funded. Live value + position count
    # are derived from the ledger sleeve projection, not stored here.
    allocated_capital: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    color: Mapped[str | None] = mapped_column(String(20), nullable=True)  # UI color for charts

    # Ledger identity (set when the execution is funded; trading threads these
    # into orders/fills — see ledger.proto and portfolio-ledger.md)
    credentials_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    sleeve_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    account_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)

    # Relationships
    strategy: Mapped[Strategy] = relationship("Strategy", back_populates="executions")
