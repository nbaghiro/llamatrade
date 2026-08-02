"""Single-use auth email tokens (password reset, email verification) + RLS.

Revision ID: 041_auth_tokens
Revises: 040_notification_delivery

Migrations are forward-only in operation and follow expand-and-contract.
``downgrade`` is for local development only, not an operational rollback tool.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

from llamatrade_db.rls import disable_rls_statements, enable_rls_statements

# revision identifiers, used by Alembic.
revision: str = "041_auth_tokens"
down_revision: str | None = "040_notification_delivery"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "auth_tokens"


def upgrade() -> None:
    op.create_table(
        _TABLE,
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("tenants.id"),
            nullable=False,
        ),
        sa.Column("user_id", PG_UUID(as_uuid=True), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("purpose", sa.String(20), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
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
    op.create_index(f"ix_{_TABLE}_tenant_id", _TABLE, ["tenant_id"])
    op.create_index(f"ix_{_TABLE}_hash", _TABLE, ["token_hash"], unique=True)

    for statement in enable_rls_statements(_TABLE):
        op.execute(statement)


def downgrade() -> None:
    for statement in disable_rls_statements(_TABLE):
        op.execute(statement)
    op.drop_index(f"ix_{_TABLE}_hash", table_name=_TABLE)
    op.drop_index(f"ix_{_TABLE}_tenant_id", table_name=_TABLE)
    op.drop_table(_TABLE)
