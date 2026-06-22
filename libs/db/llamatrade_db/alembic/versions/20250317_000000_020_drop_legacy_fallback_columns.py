"""Drop legacy off-ledger cash/value fallback columns.

The ledger event log is the sole source of truth: a sleeve's cash, reserved,
and unsettled balances are projected from events (never stored on the row), and
a strategy execution's live value + position count are derived from its sleeve
projection. The old denormalized columns were only ever read as a legacy
fallback and never written, so they are dropped.

One-way cleanup: the app is pre-production and keeps no backwards compatibility.

Revision ID: 020_drop_legacy_fallback_columns
Revises: 019_drop_legacy_portfolio_tables
Create Date: 2025-03-17 00:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "020_drop_legacy_fallback_columns"
down_revision: str | None = "019_drop_legacy_portfolio_tables"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# (table, column) pairs superseded by ledger projections.
_LEGACY_COLUMNS = (
    ("ledger_sleeves", "cash_balance"),
    ("ledger_sleeves", "reserved_cash"),
    ("ledger_sleeves", "unsettled_cash"),
    ("strategy_executions", "current_value"),
    ("strategy_executions", "positions_count"),
)


def upgrade() -> None:
    for table, column in _LEGACY_COLUMNS:
        op.drop_column(table, column)


def downgrade() -> None:
    raise NotImplementedError(
        "One-way migration: these denormalized columns were removed when the "
        "ledger became the sole source of truth. There is no downgrade."
    )
