"""Drop the deprecated agent semantic-memory tables.

``agent_memory_embeddings`` and ``agent_session_summaries`` backed the
never-launched embedding/session-summary subsystem. Their ORM models and every
runtime writer were removed; the physical tables (always empty) are dropped here.
They carry no RLS policies — migration 025 skipped them — so the drop is clean.

The downgrade recreates both tables exactly as ``014`` did (including the
pgvector-vs-JSONB embedding branch) so the migration chain stays reversible.

Revision ID: 026_drop_deprecated_agent_tables
Revises: 025_enable_rls_all_tenant_tables
Create Date: 2025-03-23 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "026_drop_deprecated_agent_tables"
down_revision: str | None = "025_enable_rls_all_tenant_tables"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _pgvector_available() -> bool:
    """Check if the pgvector extension is available in this Postgres."""
    conn = op.get_bind()
    result = conn.execute(
        sa.text("SELECT EXISTS(SELECT 1 FROM pg_available_extensions WHERE name = 'vector')")
    )
    return result.scalar() or False


def upgrade() -> None:
    """Drop the deprecated tables (indexes cascade with the table)."""
    op.execute("DROP TABLE IF EXISTS agent_session_summaries")
    op.execute("DROP TABLE IF EXISTS agent_memory_embeddings")


def downgrade() -> None:
    """Recreate both tables (mirrors migration 014) so 025 is fully restorable."""
    pgvector_enabled = False
    if _pgvector_available():
        op.execute("CREATE EXTENSION IF NOT EXISTS vector")
        pgvector_enabled = True

    op.create_table(
        "agent_memory_embeddings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("embedding_type", sa.String(20), nullable=False),
        sa.Column("content_text", sa.Text(), nullable=False),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "embedding_model",
            sa.String(50),
            nullable=False,
            server_default="text-embedding-3-small",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    if pgvector_enabled:
        op.execute("ALTER TABLE agent_memory_embeddings ADD COLUMN embedding vector(1536) NOT NULL")
    else:
        op.execute(
            "ALTER TABLE agent_memory_embeddings ADD COLUMN embedding JSONB NOT NULL DEFAULT '[]'"
        )
    op.create_index(
        "ix_agent_memory_embeddings_tenant_id", "agent_memory_embeddings", ["tenant_id"]
    )
    op.create_index("ix_agent_memory_embeddings_user_id", "agent_memory_embeddings", ["user_id"])
    op.create_index(
        "ix_agent_memory_embeddings_tenant_user",
        "agent_memory_embeddings",
        ["tenant_id", "user_id"],
    )
    op.create_index("ix_agent_memory_embeddings_source", "agent_memory_embeddings", ["source_id"])
    if pgvector_enabled:
        op.execute(
            """
            CREATE INDEX ix_agent_memory_embeddings_vector
            ON agent_memory_embeddings
            USING ivfflat (embedding vector_cosine_ops)
            WITH (lists = 100)
            """
        )

    op.create_table(
        "agent_session_summaries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("agent_sessions.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("summary_short", sa.Text(), nullable=False),
        sa.Column("summary_detailed", sa.Text(), nullable=False),
        sa.Column("topics", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("strategies_discussed", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("decisions", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("message_count_at_summary", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_agent_session_summaries_tenant_id", "agent_session_summaries", ["tenant_id"]
    )
    op.create_index("ix_agent_session_summaries_user_id", "agent_session_summaries", ["user_id"])
    op.create_index(
        "ix_agent_session_summaries_tenant_user",
        "agent_session_summaries",
        ["tenant_id", "user_id"],
    )
    op.create_index(
        "ix_agent_session_summaries_session",
        "agent_session_summaries",
        ["session_id"],
    )
