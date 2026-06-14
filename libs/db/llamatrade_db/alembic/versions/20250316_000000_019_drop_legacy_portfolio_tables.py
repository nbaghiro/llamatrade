"""Drop the legacy (pre-ledger) portfolio tables.

The portfolio service is now entirely backed by the event-sourced ledger
(``ledger_events`` folded into projections + ``ledger_sleeve_snapshots`` for the
equity curve). The old float/JSONB read-model tables — portfolio summary,
history, transactions, performance metrics, and the strategy-performance
snapshot/metrics tables — have no remaining readers or writers, so they are
dropped. One-way cleanup: the app is pre-production and keeps no backwards
compatibility with these tables.

Revision ID: 019_drop_legacy_portfolio_tables
Revises: 018_drop_trading_events
Create Date: 2025-03-16 00:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "019_drop_legacy_portfolio_tables"
down_revision: str | None = "018_drop_trading_events"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Legacy tables superseded by the ledger. Strategy-performance tables are dropped
# first (they FK strategy_executions); the rest have no inbound foreign keys.
_LEGACY_TABLES = (
    "strategy_performance_snapshots",
    "strategy_performance_metrics",
    "performance_metrics",
    "transactions",
    "portfolio_history",
    "portfolio_summary",
)


def upgrade() -> None:
    for table in _LEGACY_TABLES:
        # DROP TABLE removes the table's own indexes/constraints in PostgreSQL.
        op.drop_table(table)


def downgrade() -> None:
    raise NotImplementedError(
        "One-way migration: the legacy portfolio tables were removed when the "
        "ledger became the sole source of truth. There is no downgrade."
    )
