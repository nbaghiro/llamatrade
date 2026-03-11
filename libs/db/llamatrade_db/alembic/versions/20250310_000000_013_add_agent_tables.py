"""Add agent conversation tables.

This migration creates tables for the AI Strategy Agent (Copilot) feature:
- agent_sessions: Conversation threads
- agent_messages: Chat messages within sessions
- pending_artifacts: Generated resources awaiting user confirmation
- tool_call_logs: Audit trail of tool executions

Proto enum value mappings:
- AgentSessionStatus: ACTIVE=1, COMPLETED=2, ERROR=3
- MessageRole: USER=1, ASSISTANT=2, SYSTEM=3
- ArtifactType: STRATEGY=1

Revision ID: 013_add_agent_tables
Revises: 012_consolidate_strategy_enums
Create Date: 2025-03-10
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "013_add_agent_tables"
down_revision: str | None = "012_consolidate_strategy_enums"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create agent tables and enum types."""

    # =========================================================================
    # STEP 1: CREATE POSTGRES ENUM TYPES
    # =========================================================================

    op.execute("CREATE TYPE agent_session_status AS ENUM ('active', 'completed', 'error')")
    op.execute("CREATE TYPE message_role AS ENUM ('user', 'assistant', 'system')")
    op.execute("CREATE TYPE artifact_type AS ENUM ('strategy')")

    # =========================================================================
    # STEP 2: CREATE agent_sessions TABLE
    # =========================================================================

    op.create_table(
        "agent_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(255), nullable=True),
        sa.Column(
            "status",
            postgresql.ENUM(
                "active",
                "completed",
                "error",
                name="agent_session_status",
                create_type=False,
            ),
            nullable=False,
            server_default="active",
        ),
        sa.Column("message_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "last_activity_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
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

    # Indexes for agent_sessions
    op.create_index("ix_agent_sessions_tenant_id", "agent_sessions", ["tenant_id"])
    op.create_index("ix_agent_sessions_tenant_user", "agent_sessions", ["tenant_id", "user_id"])
    op.create_index("ix_agent_sessions_tenant_status", "agent_sessions", ["tenant_id", "status"])
    op.create_index("ix_agent_sessions_last_activity", "agent_sessions", ["last_activity_at"])
    op.create_index("ix_agent_sessions_user_id", "agent_sessions", ["user_id"])

    # =========================================================================
    # STEP 3: CREATE agent_messages TABLE
    # =========================================================================

    op.create_table(
        "agent_messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("agent_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "role",
            postgresql.ENUM(
                "user",
                "assistant",
                "system",
                name="message_role",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("tool_calls_json", postgresql.JSONB(), nullable=True),
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

    # Indexes for agent_messages
    op.create_index("ix_agent_messages_tenant_id", "agent_messages", ["tenant_id"])
    op.create_index("ix_agent_messages_session", "agent_messages", ["session_id"])
    op.create_index(
        "ix_agent_messages_tenant_session",
        "agent_messages",
        ["tenant_id", "session_id"],
    )

    # =========================================================================
    # STEP 4: CREATE pending_artifacts TABLE
    # =========================================================================

    op.create_table(
        "pending_artifacts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("agent_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "artifact_type",
            postgresql.ENUM("strategy", name="artifact_type", create_type=False),
            nullable=False,
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("artifact_json", postgresql.JSONB(), nullable=False),
        sa.Column("is_committed", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("committed_resource_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("committed_at", sa.DateTime(timezone=True), nullable=True),
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

    # Indexes for pending_artifacts
    op.create_index("ix_pending_artifacts_tenant_id", "pending_artifacts", ["tenant_id"])
    op.create_index("ix_pending_artifacts_session", "pending_artifacts", ["session_id"])
    op.create_index("ix_pending_artifacts_committed", "pending_artifacts", ["is_committed"])

    # =========================================================================
    # STEP 5: CREATE tool_call_logs TABLE
    # =========================================================================

    op.create_table(
        "tool_call_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("agent_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "message_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("agent_messages.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("tool_name", sa.String(100), nullable=False),
        sa.Column("arguments_json", postgresql.JSONB(), nullable=True),
        sa.Column("result_json", postgresql.JSONB(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("success", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("error_message", sa.Text(), nullable=True),
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

    # Indexes for tool_call_logs
    op.create_index("ix_tool_call_logs_tenant_id", "tool_call_logs", ["tenant_id"])
    op.create_index("ix_tool_call_logs_session", "tool_call_logs", ["session_id"])
    op.create_index("ix_tool_call_logs_tenant_tool", "tool_call_logs", ["tenant_id", "tool_name"])
    op.create_index(
        "ix_tool_call_logs_tenant_created",
        "tool_call_logs",
        ["tenant_id", "created_at"],
    )


def downgrade() -> None:
    """Drop agent tables and enum types."""

    # Drop tables in reverse order (respecting foreign key constraints)
    op.drop_table("tool_call_logs")
    op.drop_table("pending_artifacts")
    op.drop_table("agent_messages")
    op.drop_table("agent_sessions")

    # Drop enum types
    op.execute("DROP TYPE IF EXISTS artifact_type")
    op.execute("DROP TYPE IF EXISTS message_role")
    op.execute("DROP TYPE IF EXISTS agent_session_status")
