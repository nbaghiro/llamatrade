"""Add parameters column to strategy_versions table.

Revision ID: 007
Revises: 006
Create Date: 2024-07-01 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "007"
down_revision: str | None = "006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add parameters column to strategy_versions table."""
    op.add_column(
        "strategy_versions",
        sa.Column(
            "parameters",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
    )


def downgrade() -> None:
    """Remove parameters column from strategy_versions table."""
    op.drop_column("strategy_versions", "parameters")
