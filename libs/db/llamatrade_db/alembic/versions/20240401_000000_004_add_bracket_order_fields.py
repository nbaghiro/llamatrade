"""Add bracket order fields for stop-loss/take-profit support.

Revision ID: 004
Revises: 003
Create Date: 2024-04-01 00:00:00.000000

Changes:
- Add parent_order_id column (FK to orders.id) for linking bracket orders to parent
- Add bracket_type column (stop_loss, take_profit) to identify bracket order type
- Add stop_loss_price column for storing stop-loss target
- Add take_profit_price column for storing take-profit target
- Add index on parent_order_id for efficient bracket order lookups
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "004"
down_revision: str | None = "003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ===================
    # Add bracket order columns to orders table
    # ===================

    # Parent order reference for linking bracket orders
    op.add_column(
        "orders",
        sa.Column(
            "parent_order_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("orders.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )

    # Bracket type identifier (stop_loss or take_profit)
    op.add_column(
        "orders",
        sa.Column("bracket_type", sa.String(20), nullable=True),
    )

    # Stop-loss price for the position exit
    op.add_column(
        "orders",
        sa.Column("stop_loss_price", sa.Numeric(precision=18, scale=8), nullable=True),
    )

    # Take-profit price for the position exit
    op.add_column(
        "orders",
        sa.Column("take_profit_price", sa.Numeric(precision=18, scale=8), nullable=True),
    )

    # Index for efficient bracket order lookups
    op.create_index("ix_orders_parent", "orders", ["parent_order_id"])


def downgrade() -> None:
    # Drop index first
    op.drop_index("ix_orders_parent", table_name="orders")

    # Drop columns
    op.drop_column("orders", "take_profit_price")
    op.drop_column("orders", "stop_loss_price")
    op.drop_column("orders", "bracket_type")
    op.drop_column("orders", "parent_order_id")
