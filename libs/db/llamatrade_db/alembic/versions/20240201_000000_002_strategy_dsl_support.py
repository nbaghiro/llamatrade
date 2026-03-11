"""Add S-expression DSL support to strategy models.

Revision ID: 002
Revises: 001
Create Date: 2024-02-01 00:00:00.000000

Changes:
- Add strategy_type_enum, strategy_status_enum, deployment_status_enum, deployment_environment_enum
- Add status column to strategies (replaces is_active logic)
- Add config_sexpr, symbols, timeframe columns to strategy_versions
- Rename config to config_json in strategy_versions
- Create strategy_deployments table
- Update strategy_templates with new fields
"""

from collections.abc import Sequence
from typing import cast

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql
from sqlalchemy.sql.schema import Column

# revision identifiers, used by Alembic.
revision: str = "002"
down_revision: str | None = "001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ===================
    # Create Enums
    # ===================

    strategy_type_enum = postgresql.ENUM(
        "trend_following",
        "mean_reversion",
        "momentum",
        "breakout",
        "custom",
        name="strategy_type_enum",
    )
    strategy_type_enum.create(op.get_bind(), checkfirst=True)

    strategy_status_enum = postgresql.ENUM(
        "draft",
        "active",
        "paused",
        "archived",
        name="strategy_status_enum",
    )
    strategy_status_enum.create(op.get_bind(), checkfirst=True)

    deployment_status_enum = postgresql.ENUM(
        "pending",
        "running",
        "paused",
        "stopped",
        "error",
        name="deployment_status_enum",
    )
    deployment_status_enum.create(op.get_bind(), checkfirst=True)

    deployment_environment_enum = postgresql.ENUM(
        "paper",
        "live",
        name="deployment_environment_enum",
    )
    deployment_environment_enum.create(op.get_bind(), checkfirst=True)

    # ===================
    # Update strategies table
    # ===================

    # Add status column
    op.add_column(
        "strategies",
        sa.Column(
            "status",
            strategy_status_enum,
            nullable=False,
            server_default="draft",
        ),
    )

    # Update strategy_type to use enum (requires data migration)
    # First add a new column with enum type
    op.add_column(
        "strategies",
        sa.Column(
            "strategy_type_new",
            strategy_type_enum,
            nullable=True,
        ),
    )

    # Migrate data from old string column to new enum column
    op.execute(
        """
        UPDATE strategies
        SET strategy_type_new = strategy_type::strategy_type_enum
        WHERE strategy_type IN ('trend_following', 'mean_reversion', 'momentum', 'breakout', 'custom')
        """
    )

    # Set default for any unmapped values
    op.execute(
        """
        UPDATE strategies
        SET strategy_type_new = 'custom'
        WHERE strategy_type_new IS NULL
        """
    )

    # Make the new column non-nullable
    op.alter_column("strategies", "strategy_type_new", nullable=False)

    # Drop old column and rename new one
    op.drop_column("strategies", "strategy_type")
    op.alter_column("strategies", "strategy_type_new", new_column_name="strategy_type")

    # Migrate is_active to status
    op.execute(
        """
        UPDATE strategies
        SET status = CASE
            WHEN is_active = false THEN 'archived'::strategy_status_enum
            ELSE 'draft'::strategy_status_enum
        END
        """
    )

    # Drop is_active and config columns (config moved to versions only)
    op.drop_column("strategies", "is_active")
    op.drop_column("strategies", "config")

    # Add new indexes
    op.create_index("ix_strategies_tenant_status", "strategies", ["tenant_id", "status"])
    op.create_index("ix_strategies_tenant_type", "strategies", ["tenant_id", "strategy_type"])

    # ===================
    # Update strategy_versions table
    # ===================

    # Add config_sexpr column
    op.add_column(
        "strategy_versions",
        sa.Column("config_sexpr", sa.Text(), nullable=True),
    )

    # Rename config to config_json
    op.alter_column("strategy_versions", "config", new_column_name="config_json")

    # Add symbols column (JSONB array)
    op.add_column(
        "strategy_versions",
        sa.Column("symbols", postgresql.JSONB(), nullable=True),
    )

    # Add timeframe column
    op.add_column(
        "strategy_versions",
        sa.Column("timeframe", sa.String(10), nullable=True),
    )

    # Set defaults for existing rows
    # Note: Using double colon escaping (\\:) to prevent SQLAlchemy from interpreting :name as a bind param
    op.execute(
        sa.text(
            """
            UPDATE strategy_versions
            SET config_sexpr = '(strategy \\:name "migrated" \\:symbols [] \\:timeframe "1D" \\:entry true \\:exit true)',
                symbols = '[]'::jsonb,
                timeframe = '1D'
            WHERE config_sexpr IS NULL
            """
        )
    )

    # Make columns non-nullable
    op.alter_column("strategy_versions", "config_sexpr", nullable=False)
    op.alter_column("strategy_versions", "symbols", nullable=False)
    op.alter_column("strategy_versions", "timeframe", nullable=False)

    # Add GIN index on symbols for efficient filtering
    op.create_index(
        "ix_strategy_versions_symbols",
        "strategy_versions",
        ["symbols"],
        postgresql_using="gin",
    )

    # ===================
    # Create strategy_deployments table
    # ===================

    # Create enum references with create_type=False since we already created them above
    deployment_env_enum_col = postgresql.ENUM(
        "paper", "live", name="deployment_environment_enum", create_type=False
    )
    deployment_status_enum_col = postgresql.ENUM(
        "pending",
        "running",
        "paused",
        "stopped",
        "error",
        name="deployment_status_enum",
        create_type=False,
    )

    op.create_table(
        "strategy_deployments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "strategy_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("strategies.id"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        cast(Column[str], sa.Column("environment", deployment_env_enum_col, nullable=False)),
        cast(
            Column[str],
            sa.Column(
                "status",
                deployment_status_enum_col,
                nullable=False,
                server_default="pending",
            ),
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("stopped_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("config_override", postgresql.JSONB(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    op.create_index("ix_deployments_tenant_id", "strategy_deployments", ["tenant_id"])
    op.create_index("ix_deployments_tenant_status", "strategy_deployments", ["tenant_id", "status"])
    op.create_index("ix_deployments_strategy", "strategy_deployments", ["strategy_id"])

    # ===================
    # Update strategy_templates table
    # ===================

    # Add config_sexpr column
    op.add_column(
        "strategy_templates",
        sa.Column("config_sexpr", sa.Text(), nullable=True),
    )

    # Rename config to config_json
    op.alter_column("strategy_templates", "config", new_column_name="config_json")

    # Add new metadata columns
    op.add_column(
        "strategy_templates",
        sa.Column("tags", postgresql.JSONB(), nullable=True),
    )
    op.add_column(
        "strategy_templates",
        sa.Column("difficulty", sa.String(20), nullable=False, server_default="beginner"),
    )

    # Drop old indicators column (now in config_json)
    op.drop_column("strategy_templates", "indicators")

    # Update strategy_type to use enum
    op.add_column(
        "strategy_templates",
        sa.Column("strategy_type_new", strategy_type_enum, nullable=True),
    )
    op.execute(
        """
        UPDATE strategy_templates
        SET strategy_type_new = strategy_type::strategy_type_enum
        WHERE strategy_type IN ('trend_following', 'mean_reversion', 'momentum', 'breakout', 'custom')
        """
    )
    op.execute(
        """
        UPDATE strategy_templates
        SET strategy_type_new = 'custom'
        WHERE strategy_type_new IS NULL
        """
    )
    op.alter_column("strategy_templates", "strategy_type_new", nullable=False)
    op.drop_column("strategy_templates", "strategy_type")
    op.alter_column("strategy_templates", "strategy_type_new", new_column_name="strategy_type")

    # Set default for existing rows
    # Note: Using double colon escaping (\\:) to prevent SQLAlchemy from interpreting :name as a bind param
    op.execute(
        sa.text(
            """
            UPDATE strategy_templates
            SET config_sexpr = '(strategy \\:name "template" \\:symbols [] \\:timeframe "1D" \\:entry true \\:exit true)'
            WHERE config_sexpr IS NULL
            """
        )
    )
    op.alter_column("strategy_templates", "config_sexpr", nullable=False)


def downgrade() -> None:
    # ===================
    # Revert strategy_templates
    # ===================

    # Add back old columns
    op.add_column(
        "strategy_templates",
        sa.Column("strategy_type_old", sa.String(50), nullable=True),
    )
    op.execute("UPDATE strategy_templates SET strategy_type_old = strategy_type::text")
    op.drop_column("strategy_templates", "strategy_type")
    op.alter_column("strategy_templates", "strategy_type_old", new_column_name="strategy_type")
    op.alter_column("strategy_templates", "strategy_type", nullable=False)

    op.alter_column("strategy_templates", "config_json", new_column_name="config")
    op.drop_column("strategy_templates", "config_sexpr")
    op.drop_column("strategy_templates", "tags")
    op.drop_column("strategy_templates", "difficulty")
    op.add_column("strategy_templates", sa.Column("indicators", postgresql.JSONB(), nullable=True))

    # ===================
    # Drop strategy_deployments
    # ===================

    op.drop_index("ix_deployments_strategy", table_name="strategy_deployments")
    op.drop_index("ix_deployments_tenant_status", table_name="strategy_deployments")
    op.drop_index("ix_deployments_tenant_id", table_name="strategy_deployments")
    op.drop_table("strategy_deployments")

    # ===================
    # Revert strategy_versions
    # ===================

    op.drop_index("ix_strategy_versions_symbols", table_name="strategy_versions")
    op.drop_column("strategy_versions", "timeframe")
    op.drop_column("strategy_versions", "symbols")
    op.drop_column("strategy_versions", "config_sexpr")
    op.alter_column("strategy_versions", "config_json", new_column_name="config")

    # ===================
    # Revert strategies
    # ===================

    op.drop_index("ix_strategies_tenant_type", table_name="strategies")
    op.drop_index("ix_strategies_tenant_status", table_name="strategies")

    # Add back old columns
    op.add_column(
        "strategies",
        sa.Column("strategy_type_old", sa.String(50), nullable=True),
    )
    op.execute("UPDATE strategies SET strategy_type_old = strategy_type::text")
    op.drop_column("strategies", "strategy_type")
    op.alter_column("strategies", "strategy_type_old", new_column_name="strategy_type")
    op.alter_column("strategies", "strategy_type", nullable=False)

    op.add_column(
        "strategies",
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
    )
    op.execute("UPDATE strategies SET is_active = (status != 'archived')")

    op.add_column(
        "strategies",
        sa.Column("config", postgresql.JSONB(), nullable=False, server_default="{}"),
    )

    op.drop_column("strategies", "status")

    # ===================
    # Drop enums
    # ===================

    deployment_environment_enum = postgresql.ENUM(name="deployment_environment_enum")
    deployment_environment_enum.drop(op.get_bind(), checkfirst=True)

    deployment_status_enum = postgresql.ENUM(name="deployment_status_enum")
    deployment_status_enum.drop(op.get_bind(), checkfirst=True)

    strategy_status_enum = postgresql.ENUM(name="strategy_status_enum")
    strategy_status_enum.drop(op.get_bind(), checkfirst=True)

    strategy_type_enum = postgresql.ENUM(name="strategy_type_enum")
    strategy_type_enum.drop(op.get_bind(), checkfirst=True)
