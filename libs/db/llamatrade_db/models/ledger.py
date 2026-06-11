"""Portfolio ledger models — multi-strategy fund allocation on one account.

The portfolio service is the book of record. An ``Account`` (one per broker
credential set) is partitioned into ``Sleeve``s (strategy / manual / unmanaged /
unallocated); each sleeve holds cash and provenance-bearing ``Lot``s. The
append-only, double-entry ``LedgerEvent`` log is the single source of truth;
sleeves / lots / cash are projections of it. ``SleeveSnapshot`` materializes a
sleeve's state at a sequence to avoid full replays.

Enum string values mirror the canonical proto enums in ``ledger.proto``
(``SleeveType``, ``SleeveStatus``, ``LotSide``, ``LedgerEventType``). Type
columns are stored as VARCHAR (not PG native ENUMs): the event taxonomy evolves,
and string storage avoids ``ALTER TYPE`` churn — proto remains the source of
truth for the value set.

See .docs/portfolio-ledger.md
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from llamatrade_db.base import Base, TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin

# =============================================================================
# Enum value sets (mirror ledger.proto; stored as VARCHAR)
# =============================================================================


class SleeveType(StrEnum):
    """Type of sleeve (virtual sub-portfolio)."""

    STRATEGY = "strategy"
    MANUAL = "manual"
    UNMANAGED = "unmanaged"
    UNALLOCATED = "unallocated"


class SleeveStatus(StrEnum):
    """Lifecycle status of a sleeve."""

    ACTIVE = "active"
    FROZEN = "frozen"
    CLOSED = "closed"


class LotSide(StrEnum):
    """Side of a lot."""

    LONG = "long"
    SHORT = "short"


class LedgerEventType(StrEnum):
    """Canonical event types for the append-only ledger (mirrors proto)."""

    # Capital
    FUNDS_DEPOSITED = "funds_deposited"
    FUNDS_WITHDRAWN = "funds_withdrawn"
    CAPITAL_ALLOCATED = "capital_allocated"
    CAPITAL_TRANSFERRED = "capital_transferred"
    # Trading
    ORDER_INTENDED = "order_intended"
    ORDER_SUBMITTED = "order_submitted"
    ORDER_ACCEPTED = "order_accepted"
    ORDER_REJECTED = "order_rejected"
    ORDER_FILLED = "order_filled"
    ORDER_CANCELLED = "order_cancelled"
    # Positions
    LOT_OPENED = "lot_opened"
    LOT_INCREASED = "lot_increased"
    LOT_REDUCED = "lot_reduced"
    LOT_CLOSED = "lot_closed"
    # Cash
    CASH_DEBITED = "cash_debited"
    CASH_CREDITED = "cash_credited"
    DIVIDEND_RECEIVED = "dividend_received"
    FEE_CHARGED = "fee_charged"
    INTEREST_ACCRUED = "interest_accrued"
    # Corporate actions
    SPLIT_APPLIED = "split_applied"
    SYMBOL_CHANGED = "symbol_changed"
    # Reconciliation
    EXTERNAL_TRADE_DETECTED = "external_trade_detected"
    DRIFT_CORRECTED = "drift_corrected"
    RECONCILIATION_ADJUSTED = "reconciliation_adjusted"
    # Sleeve lifecycle
    SLEEVE_OPENED = "sleeve_opened"
    SLEEVE_CLOSED = "sleeve_closed"
    SLEEVE_FROZEN = "sleeve_frozen"
    SLEEVE_RESUMED = "sleeve_resumed"


# =============================================================================
# Models
# =============================================================================


class Account(Base, UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin):
    """A brokerage account (one per broker credential set) — reconciliation anchor."""

    __tablename__ = "ledger_accounts"
    __table_args__ = (
        UniqueConstraint("credentials_id", name="uq_ledger_accounts_credentials"),
        Index("ix_ledger_accounts_tenant_id", "tenant_id"),
    )

    credentials_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    base_currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")

    sleeves: Mapped[list[Sleeve]] = relationship("Sleeve", back_populates="account")


class Sleeve(Base, UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin):
    """A virtual sub-portfolio within an account (strategy/manual/unmanaged/unallocated)."""

    __tablename__ = "ledger_sleeves"
    __table_args__ = (
        Index("ix_ledger_sleeves_tenant_id", "tenant_id"),
        Index("ix_ledger_sleeves_account", "account_id"),
        Index("ix_ledger_sleeves_account_type", "account_id", "type"),
        Index("ix_ledger_sleeves_strategy_execution", "strategy_execution_id"),
    )

    account_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("ledger_accounts.id", ondelete="CASCADE"), nullable=False
    )
    type: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=SleeveStatus.ACTIVE.value
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # Set only for SLEEVE_TYPE_STRATEGY sleeves.
    strategy_execution_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)

    # Capital accounting (cash sub-ledger). free = balance - reserved (derived).
    allocated_capital: Mapped[Decimal] = mapped_column(
        Numeric(precision=18, scale=2), nullable=False, default=Decimal("0")
    )
    cash_balance: Mapped[Decimal] = mapped_column(
        Numeric(precision=18, scale=2), nullable=False, default=Decimal("0")
    )
    reserved_cash: Mapped[Decimal] = mapped_column(
        Numeric(precision=18, scale=2), nullable=False, default=Decimal("0")
    )
    unsettled_cash: Mapped[Decimal] = mapped_column(
        Numeric(precision=18, scale=2), nullable=False, default=Decimal("0")
    )

    account: Mapped[Account] = relationship("Account", back_populates="sleeves")
    lots: Mapped[list[Lot]] = relationship("Lot", back_populates="sleeve")


class Lot(Base, UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin):
    """A provenance-bearing unit of a holding owned by exactly one sleeve."""

    __tablename__ = "ledger_lots"
    __table_args__ = (
        Index("ix_ledger_lots_tenant_id", "tenant_id"),
        Index("ix_ledger_lots_sleeve", "sleeve_id"),
        Index("ix_ledger_lots_sleeve_symbol", "sleeve_id", "symbol"),
        Index("ix_ledger_lots_open", "sleeve_id", "is_open"),
    )

    sleeve_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("ledger_sleeves.id", ondelete="CASCADE"), nullable=False
    )
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    side: Mapped[str] = mapped_column(String(10), nullable=False, default=LotSide.LONG.value)
    qty: Mapped[Decimal] = mapped_column(Numeric(precision=18, scale=8), nullable=False)
    avg_price: Mapped[Decimal] = mapped_column(Numeric(precision=18, scale=8), nullable=False)
    cost_basis: Mapped[Decimal] = mapped_column(Numeric(precision=18, scale=2), nullable=False)
    realized_pnl: Mapped[Decimal] = mapped_column(
        Numeric(precision=18, scale=2), nullable=False, default=Decimal("0")
    )
    is_open: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    opened_by_order_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    sleeve: Mapped[Sleeve] = relationship("Sleeve", back_populates="lots")


class LedgerEvent(Base, TenantMixin, TimestampMixin):
    """Immutable, append-only, double-entry event — the single source of truth.

    ``sequence`` provides global ordering; ``event_id`` is the idempotency key.
    ``created_at`` (from TimestampMixin) is the recorded-at time; ``occurred_at``
    is the business time the event represents.
    """

    __tablename__ = "ledger_events"
    __table_args__ = (
        Index("ix_ledger_events_tenant_id", "tenant_id"),
        Index("ix_ledger_events_account", "account_id"),
        Index("ix_ledger_events_account_seq", "account_id", "sequence"),
        Index("ix_ledger_events_sleeve", "sleeve_id"),
        Index("ix_ledger_events_type", "event_type"),
    )

    sequence: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    event_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), nullable=False, unique=True, default=uuid4
    )
    account_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    # Empty for account-level events (e.g., deposits).
    sleeve_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    data: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class SleeveSnapshot(Base, UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin):
    """Materialized sleeve state at a ledger sequence, to avoid full replays."""

    __tablename__ = "ledger_sleeve_snapshots"
    __table_args__ = (
        Index("ix_ledger_sleeve_snapshots_tenant_id", "tenant_id"),
        Index("ix_ledger_sleeve_snapshots_sleeve_seq", "sleeve_id", "as_of_sequence"),
    )

    sleeve_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("ledger_sleeves.id", ondelete="CASCADE"), nullable=False
    )
    as_of_sequence: Mapped[int] = mapped_column(BigInteger, nullable=False)
    cash_balance: Mapped[Decimal] = mapped_column(Numeric(precision=18, scale=2), nullable=False)
    reserved_cash: Mapped[Decimal] = mapped_column(Numeric(precision=18, scale=2), nullable=False)
    equity: Mapped[Decimal] = mapped_column(Numeric(precision=18, scale=2), nullable=False)
    # Snapshot of open lots at this sequence (list of lot dicts).
    lots: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
