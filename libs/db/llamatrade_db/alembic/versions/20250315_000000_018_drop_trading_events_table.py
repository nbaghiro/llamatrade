"""Drop the trading_events table (session-level event sourcing retired).

Revision ID: 018_drop_trading_events
Revises: 017_add_trading_ledger_identity
Create Date: 2025-03-15 00:00:00.000000

The trading service's session-level event-sourcing subsystem was never wired
into the live path and has been superseded by the portfolio ledger (the
account-grain, double-entry book of record) plus broker reconciliation. This
drops the now-unused append-only event log. Migration 005 is kept in history;
the table is recreated by downgrade for reversibility.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "018_drop_trading_events"
down_revision: str | None = "017_add_trading_ledger_identity"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_index("ix_trading_events_event_id", table_name="trading_events")
    op.drop_index("ix_trading_events_type_seq", table_name="trading_events")
    op.drop_index("ix_trading_events_tenant_seq", table_name="trading_events")
    op.drop_index("ix_trading_events_session_seq", table_name="trading_events")
    op.drop_table("trading_events")


def downgrade() -> None:
    # Recreate the table as it existed in migration 005 (reversibility only).
    op.create_table(
        "trading_events",
        sa.Column("sequence", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("event_id", postgresql.UUID(as_uuid=True), unique=True, nullable=False),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "stored_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("data", postgresql.JSONB, nullable=False),
    )
    op.create_index("ix_trading_events_session_seq", "trading_events", ["session_id", "sequence"])
    op.create_index("ix_trading_events_tenant_seq", "trading_events", ["tenant_id", "sequence"])
    op.create_index("ix_trading_events_type_seq", "trading_events", ["event_type", "sequence"])
    op.create_index("ix_trading_events_event_id", "trading_events", ["event_id"], unique=True)
