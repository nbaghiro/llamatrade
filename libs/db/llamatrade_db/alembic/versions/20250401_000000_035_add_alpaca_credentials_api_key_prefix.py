"""Add ``alpaca_credentials.api_key_prefix`` so list/get display skips decryption.

The first characters of the API key are stored at credential creation; display
paths return them directly and only legacy NULL rows (and OAuth rows, which have
no key) fall back to decrypting.

Revision ID: 035_add_alpaca_key_prefix
Revises: 034_add_projection_checkpoints
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "035_add_alpaca_key_prefix"
down_revision: str | None = "034_add_projection_checkpoints"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "alpaca_credentials",
        sa.Column("api_key_prefix", sa.String(length=12), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("alpaca_credentials", "api_key_prefix")
