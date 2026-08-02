"""Swap the strategy_versions ``timeframe`` projection for ``rebalance``.

``timeframe`` was derived from the strategy's rebalance frequency (daily->1D, weekly->1W, ...) and
carried no information the rebalance cadence didn't already; it was also mislabeled as a bar
granularity. Replace it with the ``rebalance`` projection (the real field), backfilling by reversing
the old mapping. Execution granularity is a backtest-run parameter, not a stored strategy field.

Revision ID: 033_swap_timeframe_for_rebalance
Revises: 032_drop_version_derived_cols
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "033_swap_timeframe_for_rebalance"
down_revision: str | None = "032_drop_version_derived_cols"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "strategy_versions",
        sa.Column("rebalance", sa.String(length=20), nullable=True),
    )
    op.execute(
        """
        UPDATE strategy_versions SET rebalance = CASE timeframe
            WHEN '1W' THEN 'weekly'
            WHEN '1M' THEN 'monthly'
            WHEN '3M' THEN 'quarterly'
            WHEN '1Y' THEN 'annually'
            ELSE 'daily'
        END
        """
    )
    op.alter_column("strategy_versions", "rebalance", nullable=False, server_default="daily")
    op.drop_column("strategy_versions", "timeframe")


def downgrade() -> None:
    op.add_column(
        "strategy_versions",
        sa.Column("timeframe", sa.String(length=10), nullable=True),
    )
    op.execute(
        """
        UPDATE strategy_versions SET timeframe = CASE rebalance
            WHEN 'weekly' THEN '1W'
            WHEN 'monthly' THEN '1M'
            WHEN 'quarterly' THEN '3M'
            WHEN 'annually' THEN '1Y'
            ELSE '1D'
        END
        """
    )
    op.alter_column("strategy_versions", "timeframe", nullable=False)
    op.drop_column("strategy_versions", "rebalance")
