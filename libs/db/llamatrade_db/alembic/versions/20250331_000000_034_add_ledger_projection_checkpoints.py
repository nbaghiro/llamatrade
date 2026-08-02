"""Add ledger_projection_checkpoints — persisted incremental-projection checkpoints.

Projections are pure folds of the ledger event log; the projector's incremental
path checkpoints its fold state (projection + reservation state) per account.
This table persists those checkpoints so a restarted process folds only the
delta since ``as_of_sequence`` instead of replaying each account's full history.
Rows are derived state (safe to delete). Tenant-scoped, so the table gets the
same fail-closed RLS policy as every other ledger table.

Revision ID: 034_add_projection_checkpoints
Revises: 033_swap_timeframe_for_rebalance
Create Date: 2025-03-31 00:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

from llamatrade_db.models.ledger import ProjectionCheckpoint
from llamatrade_db.rls import disable_rls_statements, enable_rls_statements

# revision identifiers, used by Alembic.
revision: str = "034_add_projection_checkpoints"
down_revision: str | None = "033_swap_timeframe_for_rebalance"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "ledger_projection_checkpoints"


def upgrade() -> None:
    bind = op.get_bind()
    ProjectionCheckpoint.__table__.create(bind=bind, checkfirst=True)
    for statement in enable_rls_statements(_TABLE):
        op.execute(statement)


def downgrade() -> None:
    bind = op.get_bind()
    for statement in disable_rls_statements(_TABLE):
        op.execute(statement)
    ProjectionCheckpoint.__table__.drop(bind=bind, checkfirst=True)
