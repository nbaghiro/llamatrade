"""Add users.avatar_url so a profile photo can live on the account.

Nullable URL string; empty/null renders an initials avatar client-side.

Revision ID: 024_add_user_avatar_url
Revises: 023_agent_msg_artifact_ids
Create Date: 2025-03-21 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "024_add_user_avatar_url"
down_revision: str | None = "023_agent_msg_artifact_ids"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the nullable avatar_url column to users."""
    op.add_column(
        "users",
        sa.Column("avatar_url", sa.String(512), nullable=True),
    )


def downgrade() -> None:
    """Drop the avatar_url column."""
    op.drop_column("users", "avatar_url")
