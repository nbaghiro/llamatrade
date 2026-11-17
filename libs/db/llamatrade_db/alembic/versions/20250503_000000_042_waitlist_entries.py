"""Marketing waitlist entries (pre-account, no tenant, so no RLS).

Revision ID: 042_waitlist_entries
Revises: 041_auth_tokens

Migrations are forward-only in operation and follow expand-and-contract.
``downgrade`` is for local development only, not an operational rollback tool.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

# revision identifiers, used by Alembic.
revision: str = "042_waitlist_entries"
down_revision: str | None = "041_auth_tokens"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "waitlist_entries"


def upgrade() -> None:
    op.create_table(
        _TABLE,
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("source", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="waiting"),
        sa.Column("invited_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ip_hash", sa.String(64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("status IN ('waiting', 'invited')", name="ck_waitlist_entries_status"),
    )
    op.create_index(f"ix_{_TABLE}_email", _TABLE, ["email"], unique=True)


def downgrade() -> None:
    op.drop_index(f"ix_{_TABLE}_email", table_name=_TABLE)
    op.drop_table(_TABLE)
