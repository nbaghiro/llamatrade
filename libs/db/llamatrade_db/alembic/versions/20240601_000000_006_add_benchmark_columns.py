"""Add benchmark comparison columns to backtest_results.

Revision ID: 006
Revises: 005
Create Date: 2024-06-01 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision: str = "006"
down_revision: str | None = "005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add benchmark comparison columns to backtest_results table."""
    # Add benchmark comparison columns
    op.add_column(
        "backtest_results",
        sa.Column("benchmark_return", sa.Numeric(precision=18, scale=6), nullable=True),
    )
    op.add_column(
        "backtest_results",
        sa.Column("benchmark_symbol", sa.String(10), nullable=True),
    )
    op.add_column(
        "backtest_results",
        sa.Column("alpha", sa.Numeric(precision=10, scale=6), nullable=True),
    )
    op.add_column(
        "backtest_results",
        sa.Column("beta", sa.Numeric(precision=10, scale=6), nullable=True),
    )
    op.add_column(
        "backtest_results",
        sa.Column("information_ratio", sa.Numeric(precision=10, scale=6), nullable=True),
    )
    op.add_column(
        "backtest_results",
        sa.Column("benchmark_equity_curve", JSONB, nullable=True),
    )


def downgrade() -> None:
    """Remove benchmark comparison columns from backtest_results table."""
    op.drop_column("backtest_results", "benchmark_equity_curve")
    op.drop_column("backtest_results", "information_ratio")
    op.drop_column("backtest_results", "beta")
    op.drop_column("backtest_results", "alpha")
    op.drop_column("backtest_results", "benchmark_symbol")
    op.drop_column("backtest_results", "benchmark_return")
