"""Add Alpaca OAuth support: token columns on alpaca_credentials + oauth_identities.

``alpaca_credentials`` gains an ``auth_type`` discriminator and OAuth token columns
(the key/secret pair becomes nullable so OAuth rows can omit it). A new
``oauth_identities`` table anchors external-provider logins (Alpaca account id →
user) and is RLS-protected like every other tenant-scoped table.

Revision ID: 029_add_alpaca_oauth
Revises: 028_decimalize_risk_and_pnl
Create Date: 2025-03-26 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from llamatrade_db.models.auth import OAuthIdentity, OAuthPendingSignup
from llamatrade_db.rls import disable_rls_statements, enable_rls_statements

# revision identifiers, used by Alembic.
revision: str = "029_add_alpaca_oauth"
down_revision: str | None = "028_decimalize_risk_and_pnl"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # OAuth token columns on alpaca_credentials.
    op.add_column(
        "alpaca_credentials",
        sa.Column("auth_type", sa.String(20), nullable=False, server_default="api_key"),
    )
    op.add_column(
        "alpaca_credentials", sa.Column("access_token_encrypted", sa.Text(), nullable=True)
    )
    op.add_column(
        "alpaca_credentials", sa.Column("refresh_token_encrypted", sa.Text(), nullable=True)
    )
    op.add_column(
        "alpaca_credentials",
        sa.Column("token_expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "alpaca_credentials", sa.Column("alpaca_account_id", sa.String(64), nullable=True)
    )
    # The app-side default supplies auth_type going forward; drop the backfill default.
    op.alter_column("alpaca_credentials", "auth_type", server_default=None)

    # OAuth rows carry a token, not a key/secret pair.
    op.alter_column(
        "alpaca_credentials", "api_key_encrypted", existing_type=sa.Text(), nullable=True
    )
    op.alter_column(
        "alpaca_credentials", "api_secret_encrypted", existing_type=sa.Text(), nullable=True
    )

    # oauth_identities table (matches the ORM model exactly) + fail-closed RLS.
    bind = op.get_bind()
    OAuthIdentity.__table__.create(bind=bind, checkfirst=True)
    for statement in enable_rls_statements("oauth_identities"):
        op.execute(statement)

    # oauth_pending_signups is a transient, pre-tenant staging table (no RLS).
    OAuthPendingSignup.__table__.create(bind=bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    OAuthPendingSignup.__table__.drop(bind=bind, checkfirst=True)
    for statement in disable_rls_statements("oauth_identities"):
        op.execute(statement)
    OAuthIdentity.__table__.drop(bind=bind, checkfirst=True)

    op.alter_column(
        "alpaca_credentials", "api_secret_encrypted", existing_type=sa.Text(), nullable=False
    )
    op.alter_column(
        "alpaca_credentials", "api_key_encrypted", existing_type=sa.Text(), nullable=False
    )
    op.drop_column("alpaca_credentials", "alpaca_account_id")
    op.drop_column("alpaca_credentials", "token_expires_at")
    op.drop_column("alpaca_credentials", "refresh_token_encrypted")
    op.drop_column("alpaca_credentials", "access_token_encrypted")
    op.drop_column("alpaca_credentials", "auth_type")
