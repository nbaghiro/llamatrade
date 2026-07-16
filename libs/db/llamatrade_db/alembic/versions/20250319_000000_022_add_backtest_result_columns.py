"""Add backtest_results columns the model declared but no migration created.

Adds max_drawdown_duration, exposure_time and monthly_returns (nullable, types
per BacktestResult) so the read/write paths stop working around absent columns.

Revision ID: 022_add_backtest_result_columns
Revises: 021_add_backtest_reaper_indexes
Create Date: 2025-03-19 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision: str = "022_add_backtest_result_columns"
down_revision: str | None = "021_add_backtest_reaper_indexes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the drifted metric columns to backtest_results."""
    op.add_column(
        "backtest_results",
        sa.Column("max_drawdown_duration", sa.Integer(), nullable=True),
    )
    op.add_column(
        "backtest_results",
        sa.Column("exposure_time", sa.Numeric(precision=5, scale=2), nullable=True),
    )
    op.add_column(
        "backtest_results",
        sa.Column("monthly_returns", JSONB, nullable=True),
    )


def downgrade() -> None:
    """Remove the metric columns from backtest_results."""
    op.drop_column("backtest_results", "monthly_returns")
    op.drop_column("backtest_results", "exposure_time")
    op.drop_column("backtest_results", "max_drawdown_duration")
