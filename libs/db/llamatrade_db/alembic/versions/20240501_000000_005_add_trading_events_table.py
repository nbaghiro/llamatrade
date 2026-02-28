"""Add trading_events table for event sourcing.

Revision ID: 005
Revises: 004
Create Date: 2024-05-01 00:00:00.000000

Changes:
- Create trading_events table for append-only event storage
- Add indexes for efficient event stream queries
- Support for event sourcing pattern in trading service
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "005"
down_revision: str | None = "004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ===================
    # Create trading_events table for event sourcing
    # ===================

    op.create_table(
        "trading_events",
        # Primary key - global sequence for ordering
        sa.Column(
            "sequence",
            sa.BigInteger,
            primary_key=True,
            autoincrement=True,
        ),
        # Event identity
        sa.Column(
            "event_id",
            postgresql.UUID(as_uuid=True),
            unique=True,
            nullable=False,
        ),
        sa.Column(
            "event_type",
            sa.String(100),
            nullable=False,
        ),
        # Ownership
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        # Timing
        sa.Column(
            "timestamp",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "stored_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        # Event payload (JSONB for efficient querying)
        sa.Column(
            "data",
            postgresql.JSONB,
            nullable=False,
        ),
    )

    # ===================
    # Create indexes for efficient queries
    # ===================

    # Primary query pattern: read events for a session in order
    op.create_index(
        "ix_trading_events_session_seq",
        "trading_events",
        ["session_id", "sequence"],
    )

    # Query all events for a tenant
    op.create_index(
        "ix_trading_events_tenant_seq",
        "trading_events",
        ["tenant_id", "sequence"],
    )

    # Query events by type (for projections)
    op.create_index(
        "ix_trading_events_type_seq",
        "trading_events",
        ["event_type", "sequence"],
    )

    # Lookup by event ID
    op.create_index(
        "ix_trading_events_event_id",
        "trading_events",
        ["event_id"],
        unique=True,
    )


def downgrade() -> None:
    # Drop indexes first
    op.drop_index("ix_trading_events_event_id", table_name="trading_events")
    op.drop_index("ix_trading_events_type_seq", table_name="trading_events")
    op.drop_index("ix_trading_events_tenant_seq", table_name="trading_events")
    op.drop_index("ix_trading_events_session_seq", table_name="trading_events")

    # Drop table
    op.drop_table("trading_events")
