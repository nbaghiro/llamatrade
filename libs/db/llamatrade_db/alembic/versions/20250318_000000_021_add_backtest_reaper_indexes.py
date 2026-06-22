"""Add composite indexes supporting the backtest reaper's stale-row sweeps.

The reaper (1A) periodically scans for orphaned runs across all tenants:
RUNNING rows by ``started_at`` and PENDING rows by ``created_at``. The existing
``(tenant_id, status)`` index does not serve these tenant-agnostic range scans,
so add ``(status, started_at)`` and ``(status, created_at)``.

Revision ID: 021_add_backtest_reaper_indexes
Revises: 020_drop_legacy_fallback_columns
Create Date: 2025-03-18 00:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "021_add_backtest_reaper_indexes"
down_revision: str | None = "020_drop_legacy_fallback_columns"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_INDEXES = (
    ("ix_backtests_status_started_at", ["status", "started_at"]),
    ("ix_backtests_status_created_at", ["status", "created_at"]),
)


def upgrade() -> None:
    for name, columns in _INDEXES:
        op.create_index(name, "backtests", columns)


def downgrade() -> None:
    for name, _columns in _INDEXES:
        op.drop_index(name, table_name="backtests")
