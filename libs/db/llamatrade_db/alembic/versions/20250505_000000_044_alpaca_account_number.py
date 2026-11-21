"""Alpaca account number on broker credentials, for telling paper and live apart.

Revision ID: 044_alpaca_account_number
Revises: 043_invite_codes

Migrations are forward-only in operation and follow expand-and-contract.
``downgrade`` is for local development only, not an operational rollback tool.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "044_alpaca_account_number"
down_revision: str | None = "043_invite_codes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("alpaca_credentials", sa.Column("account_number", sa.String(32), nullable=True))


def downgrade() -> None:
    op.drop_column("alpaca_credentials", "account_number")
