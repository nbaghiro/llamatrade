"""Enforce ``orders.client_order_id`` uniqueness at the database.

``client_order_id`` is the exactly-once submission key (and the seed of the
ledger fill's deterministic ``event_id``); the app-level dedup lookup can race
under concurrent submits, so the constraint is the last line of defense against
two rows claiming one broker order.

Revision ID: 036_orders_client_order_id_uq
Revises: 035_add_alpaca_key_prefix
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "036_orders_client_order_id_uq"
down_revision: str | None = "035_add_alpaca_key_prefix"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_unique_constraint("uq_orders_client_order_id", "orders", ["client_order_id"])


def downgrade() -> None:
    op.drop_constraint("uq_orders_client_order_id", "orders", type_="unique")
