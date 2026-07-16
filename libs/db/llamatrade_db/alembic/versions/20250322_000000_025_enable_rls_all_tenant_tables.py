"""Enable fail-closed tenant row-level security on every tenant-scoped table.

The platform-wide RLS cutover (defense-in-depth): even if an application query
omits its ``WHERE tenant_id`` filter, Postgres exposes only rows for the tenant
bound to the current transaction (GUC ``app.current_tenant``, set from the
*verified* identity via ``llamatrade_db.tenant_session``). Trusted cross-tenant
background sweeps and the identity authority (auth) use ``app.rls_bypass``
(``llamatrade_db.system_session`` / ``set_rls_bypass``). Policy DDL is defined
once in ``llamatrade_db.rls`` (``RLS_TABLES``).

DEPLOY PREREQUISITE (RLS is inert until then): the application must connect as a
**non-superuser, non-BYPASSRLS** role; a separate privileged role runs
migrations/admin. Superusers and (without ``FORCE``) table owners bypass RLS.

Skips the deprecated agent tables (``agent_memory_embeddings``,
``agent_session_summaries``) whose models are being dropped separately.

Revision ID: 025_enable_rls_all_tenant_tables
Revises: 024_add_user_avatar_url
Create Date: 2025-03-22 00:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

from llamatrade_db.rls import RLS_TABLES, disable_rls_statements, enable_rls_statements

# revision identifiers, used by Alembic.
revision: str = "025_enable_rls_all_tenant_tables"
down_revision: str | None = "024_add_user_avatar_url"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    for table in RLS_TABLES:
        for statement in enable_rls_statements(table):
            op.execute(statement)


def downgrade() -> None:
    for table in RLS_TABLES:
        for statement in disable_rls_statements(table):
            op.execute(statement)
