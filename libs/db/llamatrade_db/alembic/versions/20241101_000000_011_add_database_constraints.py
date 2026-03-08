"""Add database constraints for data integrity.

Adds:
- UniqueConstraint on (tenant_id, name) for strategies to prevent duplicate names per tenant
- UniqueConstraint on (strategy_id, version) for strategy_versions (explicit constraint)
- CheckConstraint on version > 0 for strategy_versions

Revision ID: 011
Revises: 010
Create Date: 2024-11-01 00:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "011"
down_revision: str | None = "010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add database constraints for data integrity.

    Before adding constraints, we need to ensure no duplicates exist.
    The migration will fail if there are duplicate (tenant_id, name) pairs
    or (strategy_id, version) pairs in the data.
    """
    # Add unique constraint on (tenant_id, name) for strategies
    # This prevents duplicate strategy names within a tenant
    op.create_unique_constraint(
        "uq_strategy_tenant_name",
        "strategies",
        ["tenant_id", "name"],
    )

    # Add explicit unique constraint on (strategy_id, version)
    # Note: There's already a unique index, but an explicit constraint is clearer
    op.create_unique_constraint(
        "uq_version_strategy_version",
        "strategy_versions",
        ["strategy_id", "version"],
    )

    # Add check constraint to ensure version is positive
    op.create_check_constraint(
        "ck_version_positive",
        "strategy_versions",
        "version > 0",
    )


def downgrade() -> None:
    """Remove database constraints."""
    op.drop_constraint("ck_version_positive", "strategy_versions", type_="check")
    op.drop_constraint("uq_version_strategy_version", "strategy_versions", type_="unique")
    op.drop_constraint("uq_strategy_tenant_name", "strategies", type_="unique")
