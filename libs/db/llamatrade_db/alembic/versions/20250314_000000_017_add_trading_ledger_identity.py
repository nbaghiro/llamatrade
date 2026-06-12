"""Add ledger identity columns to trading_sessions and orders.

Trading is the ledger's execution arm: sessions carry the sleeve/account of
the funded strategy execution, and every order fixes its attribution at
origination so fills can be posted to the right sleeve. Nullable: legacy and
unattributed rows are valid (reconciliation routes their effects to the
Unmanaged sleeve).

See .docs/planning/CONTRACTS.md §5 (identity threading).

Revision ID: 017_add_trading_ledger_identity
Revises: 016_add_execution_ledger_identity
Create Date: 2025-03-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "017_add_trading_ledger_identity"
down_revision: str | None = "016_add_execution_ledger_identity"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add sleeve_id / account_id to trading_sessions and orders."""
    op.add_column(
        "trading_sessions",
        sa.Column("sleeve_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "trading_sessions",
        sa.Column("account_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "orders",
        sa.Column("sleeve_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "orders",
        sa.Column("account_id", postgresql.UUID(as_uuid=True), nullable=True),
    )


def downgrade() -> None:
    """Drop the ledger identity columns."""
    op.drop_column("orders", "account_id")
    op.drop_column("orders", "sleeve_id")
    op.drop_column("trading_sessions", "account_id")
    op.drop_column("trading_sessions", "sleeve_id")
