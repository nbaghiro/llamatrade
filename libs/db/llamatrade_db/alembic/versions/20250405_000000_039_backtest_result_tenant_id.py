"""Give backtest_results a tenant_id (mirrored from its backtest) + fail-closed RLS.

``backtest_results`` holds tenant data (equity curve, trades, metrics) but was
keyed only by ``backtest_id``, so it had no ``tenant_id`` column, no RLS policy,
and the RLS parity test could not see it. The column is added, backfilled from
the parent ``backtests`` row, made NOT NULL, indexed, and RLS-enabled like every
other tenant table.

Writers (the backtest worker) do not set ``tenant_id``; a BEFORE INSERT trigger
copies it from the parent ``backtests`` row, so the child's scope is always its
parent's and cannot drift. The trigger runs before the NOT NULL and RLS WITH
CHECK are evaluated, so an insert that omits the column still satisfies both.

Revision ID: 039_backtest_result_tenant_id
Revises: 038_sleeve_snapshot_unique

Migrations are forward-only in operation and follow expand-and-contract.
``downgrade`` is for local development only, not an operational rollback tool.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

from llamatrade_db.rls import disable_rls_statements, enable_rls_statements

# revision identifiers, used by Alembic.
revision: str = "039_backtest_result_tenant_id"
down_revision: str | None = "038_sleeve_snapshot_unique"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "backtest_results"
_INDEX = "ix_backtest_results_tenant_id"
_TRIGGER = "trg_backtest_results_fill_tenant_id"
_FUNCTION = "backtest_results_fill_tenant_id"

_CREATE_FUNCTION = f"""
CREATE OR REPLACE FUNCTION {_FUNCTION}() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.tenant_id IS NULL THEN
        SELECT tenant_id INTO NEW.tenant_id
        FROM backtests WHERE id = NEW.backtest_id;
    END IF;
    RETURN NEW;
END;
$$
"""

_CREATE_TRIGGER = f"""
CREATE TRIGGER {_TRIGGER}
    BEFORE INSERT ON {_TABLE}
    FOR EACH ROW EXECUTE FUNCTION {_FUNCTION}()
"""


def upgrade() -> None:
    op.add_column(_TABLE, sa.Column("tenant_id", PG_UUID(as_uuid=True), nullable=True))

    # Backfill from the parent (FK-guaranteed to exist) before enforcing NOT NULL.
    op.execute(
        f"""
        UPDATE {_TABLE} AS r
        SET tenant_id = b.tenant_id
        FROM backtests AS b
        WHERE r.backtest_id = b.id AND r.tenant_id IS NULL
        """
    )
    op.alter_column(_TABLE, "tenant_id", existing_type=PG_UUID(as_uuid=True), nullable=False)
    op.create_index(_INDEX, _TABLE, ["tenant_id"])

    op.execute(_CREATE_FUNCTION)
    op.execute(_CREATE_TRIGGER)

    for statement in enable_rls_statements(_TABLE):
        op.execute(statement)


def downgrade() -> None:
    for statement in disable_rls_statements(_TABLE):
        op.execute(statement)
    op.execute(f"DROP TRIGGER IF EXISTS {_TRIGGER} ON {_TABLE}")
    op.execute(f"DROP FUNCTION IF EXISTS {_FUNCTION}()")
    op.drop_index(_INDEX, table_name=_TABLE)
    op.drop_column(_TABLE, "tenant_id")
