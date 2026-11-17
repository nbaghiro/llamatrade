"""Single-use sign-up invite codes (pre-account, no tenant, so no RLS).

Revision ID: 043_invite_codes
Revises: 042_waitlist_entries

Migrations are forward-only in operation and follow expand-and-contract.
``downgrade`` is for local development only, not an operational rollback tool.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

# revision identifiers, used by Alembic.
revision: str = "043_invite_codes"
down_revision: str | None = "042_waitlist_entries"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "invite_codes"


def upgrade() -> None:
    op.create_table(
        _TABLE,
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column("code", sa.String(16), nullable=False),
        sa.Column("email", sa.String(320), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "used_by",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
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
    )
    op.create_index(f"ix_{_TABLE}_code", _TABLE, ["code"], unique=True)


def downgrade() -> None:
    op.drop_index(f"ix_{_TABLE}_code", table_name=_TABLE)
    op.drop_table(_TABLE)
