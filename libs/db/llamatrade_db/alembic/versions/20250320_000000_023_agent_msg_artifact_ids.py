"""Add inline_artifact_ids to agent_messages.

Persists which draft artifacts an assistant turn produced so reloaded copilot
sessions render the strategy cards inline with their message. The link previously
existed only client-side during streaming and was lost on reload.

Revision ID: 023_agent_msg_artifact_ids
Revises: 022_add_backtest_result_columns
Create Date: 2025-03-20 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision: str = "023_agent_msg_artifact_ids"
down_revision: str | None = "022_add_backtest_result_columns"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the inline_artifact_ids column to agent_messages."""
    op.add_column(
        "agent_messages",
        sa.Column("inline_artifact_ids", JSONB, nullable=True),
    )


def downgrade() -> None:
    """Remove the inline_artifact_ids column from agent_messages."""
    op.drop_column("agent_messages", "inline_artifact_ids")
