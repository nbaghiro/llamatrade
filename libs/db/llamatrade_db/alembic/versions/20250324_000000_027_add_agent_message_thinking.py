"""Add agent_messages.thinking for collapsible reasoning blocks.

Stores the curated reasoning the model surfaced for a turn (the ``<thinking>``
preamble split out of the streamed response) so the collapsible block re-expands
when a thread is reloaded. Nullable — user turns and pre-existing rows have none.

Revision ID: 027_add_agent_message_thinking
Revises: 026_drop_deprecated_agent_tables
Create Date: 2025-03-24 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "027_add_agent_message_thinking"
down_revision: str | None = "026_drop_deprecated_agent_tables"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("agent_messages", sa.Column("thinking", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("agent_messages", "thinking")
