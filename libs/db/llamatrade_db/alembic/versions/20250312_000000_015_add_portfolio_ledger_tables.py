"""Add portfolio ledger tables (accounts, sleeves, lots, events, snapshots).

Foundation for multi-strategy fund allocation (Phase 0 of the Portfolio Ledger).
The portfolio service is the book of record: an account is partitioned into
sleeves (strategy/manual/unmanaged/unallocated), each holding cash and lots; the
append-only double-entry ledger_events log is the single source of truth.

Type columns (sleeve type/status, lot side, event type) are stored as VARCHAR;
the canonical value sets live in ledger.proto. No behavior change — these tables
are net-new and not yet wired into any service.

See .docs/portfolio-ledger.md

Revision ID: 015_add_portfolio_ledger_tables
Revises: 014_add_agent_memory_tables
Create Date: 2025-03-12
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "015_add_portfolio_ledger_tables"
down_revision: str | None = "014_add_agent_memory_tables"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _timestamps() -> list[sa.Column]:
    """created_at / updated_at columns matching TimestampMixin."""
    return [
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    ]


def upgrade() -> None:
    """Create portfolio ledger tables."""

    # =========================================================================
    # ledger_accounts
    # =========================================================================
    op.create_table(
        "ledger_accounts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("credentials_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("base_currency", sa.String(3), nullable=False, server_default="USD"),
        *_timestamps(),
        sa.UniqueConstraint("credentials_id", name="uq_ledger_accounts_credentials"),
    )
    op.create_index("ix_ledger_accounts_tenant_id", "ledger_accounts", ["tenant_id"])

    # =========================================================================
    # ledger_sleeves
    # =========================================================================
    op.create_table(
        "ledger_sleeves",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "account_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("ledger_accounts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("type", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("strategy_execution_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("allocated_capital", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("cash_balance", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("reserved_cash", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("unsettled_cash", sa.Numeric(18, 2), nullable=False, server_default="0"),
        *_timestamps(),
    )
    op.create_index("ix_ledger_sleeves_tenant_id", "ledger_sleeves", ["tenant_id"])
    op.create_index("ix_ledger_sleeves_account", "ledger_sleeves", ["account_id"])
    op.create_index("ix_ledger_sleeves_account_type", "ledger_sleeves", ["account_id", "type"])
    op.create_index(
        "ix_ledger_sleeves_strategy_execution", "ledger_sleeves", ["strategy_execution_id"]
    )

    # =========================================================================
    # ledger_lots
    # =========================================================================
    op.create_table(
        "ledger_lots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "sleeve_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("ledger_sleeves.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("symbol", sa.String(20), nullable=False),
        sa.Column("side", sa.String(10), nullable=False, server_default="long"),
        sa.Column("qty", sa.Numeric(18, 8), nullable=False),
        sa.Column("avg_price", sa.Numeric(18, 8), nullable=False),
        sa.Column("cost_basis", sa.Numeric(18, 2), nullable=False),
        sa.Column("realized_pnl", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("is_open", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("opened_by_order_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
    )
    op.create_index("ix_ledger_lots_tenant_id", "ledger_lots", ["tenant_id"])
    op.create_index("ix_ledger_lots_sleeve", "ledger_lots", ["sleeve_id"])
    op.create_index("ix_ledger_lots_sleeve_symbol", "ledger_lots", ["sleeve_id", "symbol"])
    op.create_index("ix_ledger_lots_open", "ledger_lots", ["sleeve_id", "is_open"])

    # =========================================================================
    # ledger_events  (append-only; BIGSERIAL sequence PK, unique event_id)
    # =========================================================================
    op.create_table(
        "ledger_events",
        sa.Column("sequence", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sleeve_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column("data", postgresql.JSONB(), nullable=False),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        *_timestamps(),
    )
    op.create_index("uq_ledger_events_event_id", "ledger_events", ["event_id"], unique=True)
    op.create_index("ix_ledger_events_tenant_id", "ledger_events", ["tenant_id"])
    op.create_index("ix_ledger_events_account", "ledger_events", ["account_id"])
    op.create_index("ix_ledger_events_account_seq", "ledger_events", ["account_id", "sequence"])
    op.create_index("ix_ledger_events_sleeve", "ledger_events", ["sleeve_id"])
    op.create_index("ix_ledger_events_type", "ledger_events", ["event_type"])

    # =========================================================================
    # ledger_sleeve_snapshots
    # =========================================================================
    op.create_table(
        "ledger_sleeve_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "sleeve_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("ledger_sleeves.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("as_of_sequence", sa.BigInteger(), nullable=False),
        sa.Column("cash_balance", sa.Numeric(18, 2), nullable=False),
        sa.Column("reserved_cash", sa.Numeric(18, 2), nullable=False),
        sa.Column("equity", sa.Numeric(18, 2), nullable=False),
        sa.Column("lots", postgresql.JSONB(), nullable=False),
        *_timestamps(),
    )
    op.create_index(
        "ix_ledger_sleeve_snapshots_tenant_id", "ledger_sleeve_snapshots", ["tenant_id"]
    )
    op.create_index(
        "ix_ledger_sleeve_snapshots_sleeve_seq",
        "ledger_sleeve_snapshots",
        ["sleeve_id", "as_of_sequence"],
    )


def downgrade() -> None:
    """Drop portfolio ledger tables (reverse FK order)."""
    op.drop_table("ledger_sleeve_snapshots")
    op.drop_table("ledger_events")
    op.drop_table("ledger_lots")
    op.drop_table("ledger_sleeves")
    op.drop_table("ledger_accounts")
