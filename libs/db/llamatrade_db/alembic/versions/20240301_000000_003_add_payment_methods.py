"""Add payment_methods table and trial_days to plans.

Revision ID: 003
Revises: 002
Create Date: 2024-03-01 00:00:00.000000

Changes:
- Add trial_days column to plans table
- Create payment_methods table for storing Stripe payment methods
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "003"
down_revision: str | None = "002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ===================
    # Add trial_days to plans
    # ===================

    op.add_column(
        "plans",
        sa.Column("trial_days", sa.Integer(), nullable=False, server_default="0"),
    )

    # ===================
    # Create payment_methods table
    # ===================

    op.create_table(
        "payment_methods",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("stripe_payment_method_id", sa.String(100), nullable=False, unique=True),
        sa.Column("stripe_customer_id", sa.String(100), nullable=False),
        sa.Column("type", sa.String(50), nullable=False),
        sa.Column("card_brand", sa.String(50), nullable=True),
        sa.Column("card_last4", sa.String(4), nullable=True),
        sa.Column("card_exp_month", sa.Integer(), nullable=True),
        sa.Column("card_exp_year", sa.Integer(), nullable=True),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default="false"),
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

    op.create_index("ix_payment_methods_tenant_id", "payment_methods", ["tenant_id"])
    op.create_index("ix_payment_methods_stripe_pm", "payment_methods", ["stripe_payment_method_id"])
    op.create_index("ix_payment_methods_stripe_customer", "payment_methods", ["stripe_customer_id"])


def downgrade() -> None:
    # Drop payment_methods table
    op.drop_index("ix_payment_methods_stripe_customer", table_name="payment_methods")
    op.drop_index("ix_payment_methods_stripe_pm", table_name="payment_methods")
    op.drop_index("ix_payment_methods_tenant_id", table_name="payment_methods")
    op.drop_table("payment_methods")

    # Remove trial_days from plans
    op.drop_column("plans", "trial_days")
