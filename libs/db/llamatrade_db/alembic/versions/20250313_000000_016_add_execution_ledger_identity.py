"""Add ledger identity columns to strategy_executions.

When a strategy execution is funded, the portfolio LedgerService opens a
strategy sleeve and the execution stores its identity (credentials_id →
account anchor, sleeve_id + account_id from AllocateCapital). The trading
service reads them when starting the runner and threads them into orders,
fills, sizing, and risk. All nullable: unfunded/legacy executions are valid.

See .docs/planning/CONTRACTS.md §5 (identity threading).

Revision ID: 016_add_exec_ledger_identity
Revises: 015_add_portfolio_ledger_tables
Create Date: 2025-03-13
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "016_add_exec_ledger_identity"
down_revision: str | None = "015_add_portfolio_ledger_tables"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add credentials_id / sleeve_id / account_id to strategy_executions."""
    op.add_column(
        "strategy_executions",
        sa.Column("credentials_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "strategy_executions",
        sa.Column("sleeve_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "strategy_executions",
        sa.Column("account_id", postgresql.UUID(as_uuid=True), nullable=True),
    )


def downgrade() -> None:
    """Drop the ledger identity columns."""
    op.drop_column("strategy_executions", "account_id")
    op.drop_column("strategy_executions", "sleeve_id")
    op.drop_column("strategy_executions", "credentials_id")
