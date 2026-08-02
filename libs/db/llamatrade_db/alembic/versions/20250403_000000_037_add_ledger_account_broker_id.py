"""Key ledger accounts to the broker account, not the credential row.

``ledger_accounts`` was unique per ``credentials_id`` alone, so deleting and
re-adding a broker credential set forked a second account whose genesis backfill
adopted the positions the first one still held, and tenant-level reads
double-counted them. ``alpaca_account_id`` records the broker-side identity so a
re-added credential set resolves back to the existing book.

The column is nullable: rows predating it carry NULL, and Postgres treats NULLs
as distinct in a unique constraint, so they neither collide with each other nor
block this migration. They are filled lazily the next time onboarding or
reconciliation holds a broker snapshot for the account.

Revision ID: 037_ledger_account_broker
Revises: 036_orders_client_order_id_uq

Migrations are forward-only in operation and follow expand-and-contract: add the
new shape, migrate readers, drop the old shape in a later release. ``downgrade``
is for local development only, not an operational rollback tool.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "037_ledger_account_broker"
down_revision: str | None = "036_orders_client_order_id_uq"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("ledger_accounts", sa.Column("alpaca_account_id", sa.String(64), nullable=True))
    op.create_unique_constraint(
        "uq_ledger_accounts_broker", "ledger_accounts", ["tenant_id", "alpaca_account_id"]
    )


def downgrade() -> None:
    op.drop_constraint("uq_ledger_accounts_broker", "ledger_accounts", type_="unique")
    op.drop_column("ledger_accounts", "alpaca_account_id")
