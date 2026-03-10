"""Add tenant_id column to strategy_versions table for defense-in-depth tenant isolation.

Revision ID: 010
Revises: 009_postgres_enums
Create Date: 2024-10-01 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "010"
down_revision: str | None = "009_postgres_enums"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add tenant_id column to strategy_versions with data backfill.

    Steps:
    1. Add nullable tenant_id column
    2. Backfill from parent strategies table
    3. Make column NOT NULL
    4. Add index for tenant isolation queries
    """
    # Step 1: Add nullable column
    op.add_column(
        "strategy_versions",
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=True),
    )

    # Step 2: Backfill tenant_id from parent strategies
    op.execute(
        """
        UPDATE strategy_versions sv
        SET tenant_id = s.tenant_id
        FROM strategies s
        WHERE sv.strategy_id = s.id
        """
    )

    # Step 3: Make NOT NULL after backfill
    op.alter_column("strategy_versions", "tenant_id", nullable=False)

    # Step 4: Add index for tenant isolation queries
    op.create_index(
        "ix_strategy_versions_tenant",
        "strategy_versions",
        ["tenant_id"],
    )


def downgrade() -> None:
    """Remove tenant_id column from strategy_versions."""
    op.drop_index("ix_strategy_versions_tenant", table_name="strategy_versions")
    op.drop_column("strategy_versions", "tenant_id")
