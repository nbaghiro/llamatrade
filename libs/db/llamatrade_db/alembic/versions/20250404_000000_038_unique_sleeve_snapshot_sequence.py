"""Give sleeve snapshots an idempotency key: (sleeve, sequence, UTC day).

``ledger_sleeve_snapshots`` rows are the equity curve the read layer serves, and
nothing stopped two writers (or one writer sweeping twice) from landing a second
row for the same sleeve at the same ledger sequence in the same pass. Duplicate
points skew period returns, volatility and Sharpe, so the triple becomes UNIQUE
and the writer inserts with ``ON CONFLICT DO NOTHING``.

The calendar day is part of the key, not an afterthought. A sleeve's ledger
sequence only advances when it trades, so a held position is re-marked every
pass at an unchanged sequence and those daily marks ARE the curve; keying on
(sleeve, sequence) alone would collapse an idle sleeve's whole history to a
single point. The day expression is written against UTC so it is immutable and
indexable.

Existing duplicates are removed first, keeping the newest row per key (greatest
``created_at``, ties broken by ``id``) — the freshest mark of that day. The
delete runs as the migration role, which owns the table and therefore bypasses
RLS (policies are not FORCEd), so it spans every tenant in one pass.

Revision ID: 038_sleeve_snapshot_unique
Revises: 037_ledger_account_broker

Migrations are forward-only in operation and follow expand-and-contract: add the
new shape, migrate readers, drop the old shape in a later release. ``downgrade``
is for local development only, not an operational rollback tool.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from llamatrade_db.models.ledger import SNAPSHOT_DAY_EXPRESSION

# revision identifiers, used by Alembic.
revision: str = "038_sleeve_snapshot_unique"
down_revision: str | None = "037_ledger_account_broker"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_INDEX = "ix_ledger_sleeve_snapshots_sleeve_seq"
_TABLE = "ledger_sleeve_snapshots"


def upgrade() -> None:
    op.execute(
        f"""
        DELETE FROM {_TABLE} AS stale
        USING {_TABLE} AS keep
        WHERE stale.sleeve_id = keep.sleeve_id
          AND stale.as_of_sequence = keep.as_of_sequence
          AND (stale.created_at AT TIME ZONE 'UTC')::date
              = (keep.created_at AT TIME ZONE 'UTC')::date
          AND (stale.created_at, stale.id) < (keep.created_at, keep.id)
        """
    )
    op.drop_index(_INDEX, table_name=_TABLE)
    op.create_index(
        _INDEX,
        _TABLE,
        ["sleeve_id", "as_of_sequence", sa.text(SNAPSHOT_DAY_EXPRESSION)],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(_INDEX, table_name=_TABLE)
    op.create_index(_INDEX, _TABLE, ["sleeve_id", "as_of_sequence"], unique=False)
