"""Add agent memory tables for cross-session recall.

This migration creates tables for the agent memory system:
- agent_memory_facts: Extracted user preferences and facts
- agent_memory_embeddings: Vector embeddings for semantic search
- agent_session_summaries: Condensed session summaries

It also adds:
- pgvector extension for similarity search (if available)
- Full-text search index on agent_messages.content

Note: If pgvector is not available, embeddings will be stored as JSONB arrays
and semantic search will fall back to text-based search.

Revision ID: 014_add_agent_memory_tables
Revises: 013_add_agent_tables
Create Date: 2025-03-11
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "014_add_agent_memory_tables"
down_revision: str | None = "013_add_agent_tables"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _pgvector_available() -> bool:
    """Check if pgvector extension is available."""
    conn = op.get_bind()
    result = conn.execute(
        sa.text("SELECT EXISTS(SELECT 1 FROM pg_available_extensions WHERE name = 'vector')")
    )
    return result.scalar() or False


def upgrade() -> None:
    """Create agent memory tables and enable pgvector."""

    # =========================================================================
    # STEP 1: CHECK AND CREATE PGVECTOR EXTENSION (if available)
    # =========================================================================

    pgvector_enabled = False
    if _pgvector_available():
        op.execute("CREATE EXTENSION IF NOT EXISTS vector")
        pgvector_enabled = True
        print("pgvector extension enabled")
    else:
        print("WARNING: pgvector extension not available, semantic search will be limited")

    # =========================================================================
    # STEP 2: CREATE POSTGRES ENUM TYPE FOR MEMORY CATEGORIES
    # =========================================================================

    op.execute(
        """
        CREATE TYPE memory_fact_category AS ENUM (
            'user_preference',
            'risk_tolerance',
            'investment_goal',
            'asset_preference',
            'strategy_decision',
            'trading_behavior',
            'feedback'
        )
        """
    )

    # =========================================================================
    # STEP 3: CREATE agent_memory_facts TABLE
    # =========================================================================

    op.create_table(
        "agent_memory_facts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "category",
            postgresql.ENUM(
                "user_preference",
                "risk_tolerance",
                "investment_goal",
                "asset_preference",
                "strategy_decision",
                "trading_behavior",
                "feedback",
                name="memory_fact_category",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0.7"),
        # Source tracking
        sa.Column(
            "source_session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("agent_sessions.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "source_message_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("agent_messages.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("extraction_method", sa.String(20), nullable=False, server_default="heuristic"),
        # Lifecycle
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column(
            "supersedes_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("agent_memory_facts.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        # Access tracking
        sa.Column("last_accessed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("access_count", sa.Integer(), nullable=False, server_default="0"),
        # Timestamps
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

    # Indexes for agent_memory_facts
    op.create_index("ix_agent_memory_facts_tenant_id", "agent_memory_facts", ["tenant_id"])
    op.create_index("ix_agent_memory_facts_user_id", "agent_memory_facts", ["user_id"])
    op.create_index(
        "ix_agent_memory_facts_tenant_user", "agent_memory_facts", ["tenant_id", "user_id"]
    )
    op.create_index(
        "ix_agent_memory_facts_tenant_category",
        "agent_memory_facts",
        ["tenant_id", "category"],
    )
    op.create_index(
        "ix_agent_memory_facts_tenant_active",
        "agent_memory_facts",
        ["tenant_id", "is_active"],
    )
    op.create_index(
        "ix_agent_memory_facts_last_accessed",
        "agent_memory_facts",
        ["last_accessed_at"],
    )

    # =========================================================================
    # STEP 4: CREATE agent_memory_embeddings TABLE
    # Uses pgvector if available, otherwise JSONB for embeddings
    # =========================================================================

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
        # Timestamps
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

    # Add embedding column - vector type if pgvector available, otherwise JSONB
    if pgvector_enabled:
        op.execute("ALTER TABLE agent_memory_embeddings ADD COLUMN embedding vector(1536) NOT NULL")
    else:
        # Fallback to JSONB array storage
        op.execute(
            "ALTER TABLE agent_memory_embeddings ADD COLUMN embedding JSONB NOT NULL DEFAULT '[]'"
        )

    # Indexes for agent_memory_embeddings
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

    # Create IVFFlat index for approximate nearest neighbor search (only if pgvector)
    if pgvector_enabled:
        # Using 100 lists for a good balance of speed vs accuracy for <100k vectors
        op.execute(
            """
            CREATE INDEX ix_agent_memory_embeddings_vector
            ON agent_memory_embeddings
            USING ivfflat (embedding vector_cosine_ops)
            WITH (lists = 100)
            """
        )

    # =========================================================================
    # STEP 5: CREATE agent_session_summaries TABLE
    # =========================================================================

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
        # Timestamps
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

    # Indexes for agent_session_summaries
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

    # =========================================================================
    # STEP 6: ADD FULL-TEXT SEARCH TO agent_messages
    # =========================================================================

    # Add generated tsvector column for full-text search
    op.execute(
        """
        ALTER TABLE agent_messages
        ADD COLUMN content_tsv tsvector
        GENERATED ALWAYS AS (to_tsvector('english', content)) STORED
        """
    )

    # Create GIN index for full-text search
    op.create_index(
        "ix_agent_messages_content_fts",
        "agent_messages",
        ["content_tsv"],
        postgresql_using="gin",
    )


def downgrade() -> None:
    """Drop agent memory tables and extensions."""

    # Drop full-text search components from agent_messages
    op.drop_index("ix_agent_messages_content_fts", table_name="agent_messages")
    op.execute("ALTER TABLE agent_messages DROP COLUMN IF EXISTS content_tsv")

    # Drop vector index if it exists (only created if pgvector was available)
    op.execute("DROP INDEX IF EXISTS ix_agent_memory_embeddings_vector")

    # Drop tables in reverse order
    op.drop_table("agent_session_summaries")
    op.drop_table("agent_memory_embeddings")
    op.drop_table("agent_memory_facts")

    # Drop enum type
    op.execute("DROP TYPE IF EXISTS memory_fact_category")

    # Note: We don't drop the pgvector extension as it may be used by other tables
