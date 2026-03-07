"""Add strategy performance tables and rename deployments to executions.

Revision ID: 008_strategy_performance
Revises: 007
Create Date: 2024-08-01 00:00:00.000000

This migration:
1. Renames strategy_deployments to strategy_executions
2. Renames environment column to mode
3. Creates strategy_performance_snapshots table
4. Creates strategy_performance_metrics table
5. Adds performance-related columns to strategy_executions
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "008_strategy_performance"
down_revision: str | None = "007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add strategy performance tables and rename deployments to executions."""
    # 1. Rename strategy_deployments table to strategy_executions
    op.rename_table("strategy_deployments", "strategy_executions")

    # 2. Rename environment column to mode and update enum
    # First, rename the enum type
    op.execute("ALTER TYPE deployment_environment_enum RENAME TO execution_mode_enum")
    op.execute("ALTER TYPE deployment_status_enum RENAME TO execution_status_enum")

    # Rename the column
    op.alter_column("strategy_executions", "environment", new_column_name="mode")

    # 3. Rename indexes
    op.execute("ALTER INDEX ix_deployments_tenant_status RENAME TO ix_executions_tenant_status")
    op.execute("ALTER INDEX ix_deployments_strategy RENAME TO ix_executions_strategy")

    # 4. Add new columns to strategy_executions for performance tracking
    op.add_column(
        "strategy_executions",
        sa.Column("allocated_capital", sa.Numeric(18, 2), nullable=True),
    )
    op.add_column(
        "strategy_executions",
        sa.Column("current_value", sa.Numeric(18, 2), nullable=True),
    )
    op.add_column(
        "strategy_executions",
        sa.Column("positions_count", sa.Integer(), nullable=True, server_default="0"),
    )
    op.add_column(
        "strategy_executions",
        sa.Column("color", sa.String(20), nullable=True),  # UI color for charts
    )

    # 5. Create strategy_performance_snapshots table
    op.create_table(
        "strategy_performance_snapshots",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "execution_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("strategy_executions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("snapshot_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("equity", sa.Numeric(18, 2), nullable=False),
        sa.Column("cash", sa.Numeric(18, 2), nullable=False),
        sa.Column("positions_value", sa.Numeric(18, 2), nullable=False),
        sa.Column("daily_return", sa.Numeric(10, 6), nullable=True),
        sa.Column("cumulative_return", sa.Numeric(10, 6), nullable=True),
        sa.Column("drawdown", sa.Numeric(10, 6), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("execution_id", "snapshot_time", name="uq_snapshot_execution_time"),
    )

    # Add indexes for strategy_performance_snapshots
    op.create_index(
        "ix_perf_snapshots_tenant",
        "strategy_performance_snapshots",
        ["tenant_id"],
    )
    op.create_index(
        "ix_perf_snapshots_execution",
        "strategy_performance_snapshots",
        ["execution_id"],
    )
    op.create_index(
        "ix_perf_snapshots_time",
        "strategy_performance_snapshots",
        ["snapshot_time"],
    )

    # 6. Create strategy_performance_metrics table
    op.create_table(
        "strategy_performance_metrics",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "execution_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("strategy_executions.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,  # One metrics record per execution
        ),
        # Period returns
        sa.Column("return_1d", sa.Numeric(10, 6), nullable=True),
        sa.Column("return_1w", sa.Numeric(10, 6), nullable=True),
        sa.Column("return_1m", sa.Numeric(10, 6), nullable=True),
        sa.Column("return_3m", sa.Numeric(10, 6), nullable=True),
        sa.Column("return_6m", sa.Numeric(10, 6), nullable=True),
        sa.Column("return_1y", sa.Numeric(10, 6), nullable=True),
        sa.Column("return_ytd", sa.Numeric(10, 6), nullable=True),
        sa.Column("return_all", sa.Numeric(10, 6), nullable=True),
        # Risk metrics
        sa.Column("sharpe_ratio", sa.Numeric(10, 6), nullable=True),
        sa.Column("sortino_ratio", sa.Numeric(10, 6), nullable=True),
        sa.Column("calmar_ratio", sa.Numeric(10, 6), nullable=True),
        sa.Column("max_drawdown", sa.Numeric(10, 6), nullable=True),
        sa.Column("current_drawdown", sa.Numeric(10, 6), nullable=True),
        sa.Column("volatility", sa.Numeric(10, 6), nullable=True),
        # Trade stats
        sa.Column("total_trades", sa.Integer(), nullable=True, server_default="0"),
        sa.Column("winning_trades", sa.Integer(), nullable=True, server_default="0"),
        sa.Column("losing_trades", sa.Integer(), nullable=True, server_default="0"),
        sa.Column("win_rate", sa.Numeric(10, 4), nullable=True),
        sa.Column("profit_factor", sa.Numeric(10, 4), nullable=True),
        sa.Column("average_win", sa.Numeric(18, 2), nullable=True),
        sa.Column("average_loss", sa.Numeric(18, 2), nullable=True),
        # Capital
        sa.Column("starting_capital", sa.Numeric(18, 2), nullable=True),
        sa.Column("current_equity", sa.Numeric(18, 2), nullable=True),
        sa.Column("peak_equity", sa.Numeric(18, 2), nullable=True),
        sa.Column("total_pnl", sa.Numeric(18, 2), nullable=True),
        # Benchmark
        sa.Column("benchmark_symbol", sa.String(10), nullable=True),
        sa.Column("alpha", sa.Numeric(10, 6), nullable=True),
        sa.Column("beta", sa.Numeric(10, 6), nullable=True),
        sa.Column("correlation", sa.Numeric(10, 6), nullable=True),
        # Timestamps
        sa.Column(
            "calculated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    # Add indexes for strategy_performance_metrics
    op.create_index(
        "ix_perf_metrics_tenant",
        "strategy_performance_metrics",
        ["tenant_id"],
    )
    op.create_index(
        "ix_perf_metrics_execution",
        "strategy_performance_metrics",
        ["execution_id"],
        unique=True,
    )


def downgrade() -> None:
    """Remove strategy performance tables and rename executions back to deployments."""
    # 1. Drop strategy_performance_metrics table
    op.drop_index("ix_perf_metrics_execution", table_name="strategy_performance_metrics")
    op.drop_index("ix_perf_metrics_tenant", table_name="strategy_performance_metrics")
    op.drop_table("strategy_performance_metrics")

    # 2. Drop strategy_performance_snapshots table
    op.drop_index("ix_perf_snapshots_time", table_name="strategy_performance_snapshots")
    op.drop_index("ix_perf_snapshots_execution", table_name="strategy_performance_snapshots")
    op.drop_index("ix_perf_snapshots_tenant", table_name="strategy_performance_snapshots")
    op.drop_table("strategy_performance_snapshots")

    # 3. Remove new columns from strategy_executions
    op.drop_column("strategy_executions", "color")
    op.drop_column("strategy_executions", "positions_count")
    op.drop_column("strategy_executions", "current_value")
    op.drop_column("strategy_executions", "allocated_capital")

    # 4. Rename indexes back
    op.execute("ALTER INDEX ix_executions_strategy RENAME TO ix_deployments_strategy")
    op.execute("ALTER INDEX ix_executions_tenant_status RENAME TO ix_deployments_tenant_status")

    # 5. Rename column back
    op.alter_column("strategy_executions", "mode", new_column_name="environment")

    # 6. Rename enum types back
    op.execute("ALTER TYPE execution_status_enum RENAME TO deployment_status_enum")
    op.execute("ALTER TYPE execution_mode_enum RENAME TO deployment_environment_enum")

    # 7. Rename table back
    op.rename_table("strategy_executions", "strategy_deployments")
