"""Add reconciliation_drift and sleeve_frozen to alert_condition_type enum.

Proto ``AlertConditionType`` gained ``RECONCILIATION_DRIFT`` (9) and
``SLEEVE_FROZEN`` (10); the PostgreSQL ``alert_condition_type`` enum lagged, so
alerts of those types were silently coerced to ``price_above`` on write. This
adds the two values to the native enum so the DB can store them.

Revision ID: 030_add_alert_condition_values
Revises: 029_add_alpaca_oauth
Create Date: 2025-03-27 00:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "030_add_alert_condition_values"
down_revision: str | None = "029_add_alpaca_oauth"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TYPE alert_condition_type ADD VALUE IF NOT EXISTS 'reconciliation_drift'")
    op.execute("ALTER TYPE alert_condition_type ADD VALUE IF NOT EXISTS 'sleeve_frozen'")


def downgrade() -> None:
    # PostgreSQL cannot drop enum values without recreating the type; the added
    # values are inert unless referenced, so downgrade is intentionally a no-op.
    pass
