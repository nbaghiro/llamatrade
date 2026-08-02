"""Reshape notifications into the durable in-app row + per-channel deliveries.

``notifications`` becomes the logical notification (the durable floor every
flow persists before external delivery): it gains the deterministic
``event_id`` dedup key, the proto category/severity ints, and a nullable
``user_id`` (tenant-scoped rows leave it null). Per-channel delivery state
moves to the new ``notification_deliveries`` table, so the old ``channel`` /
``status`` / ``sent_at`` / ``error_message`` columns are dropped. Both tables
were unwritten before this revision, so no data migration is needed.

Revision ID: 040_notification_delivery
Revises: 039_backtest_result_tenant_id

Migrations are forward-only in operation and follow expand-and-contract.
``downgrade`` is for local development only, not an operational rollback tool.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ENUM as PG_ENUM
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

from llamatrade_db.rls import disable_rls_statements, enable_rls_statements

# revision identifiers, used by Alembic.
revision: str = "040_notification_delivery"
down_revision: str | None = "039_backtest_result_tenant_id"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_DELIVERIES = "notification_deliveries"


def upgrade() -> None:
    op.add_column(
        "notifications",
        sa.Column("event_id", sa.String(64), nullable=False, server_default=""),
    )
    op.alter_column("notifications", "event_id", server_default=None)
    op.add_column(
        "notifications", sa.Column("category", sa.Integer(), nullable=False, server_default="0")
    )
    op.alter_column("notifications", "category", server_default=None)
    op.add_column(
        "notifications", sa.Column("severity", sa.Integer(), nullable=False, server_default="0")
    )
    op.alter_column("notifications", "severity", server_default=None)
    op.alter_column("notifications", "user_id", existing_type=PG_UUID(as_uuid=True), nullable=True)
    op.create_index("ix_notifications_event_id", "notifications", ["event_id"], unique=True)
    op.drop_column("notifications", "channel")
    op.drop_column("notifications", "status")
    op.drop_column("notifications", "sent_at")
    op.drop_column("notifications", "error_message")

    op.create_table(
        _DELIVERIES,
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", PG_UUID(as_uuid=True), nullable=False),
        sa.Column("notification_id", PG_UUID(as_uuid=True), nullable=False),
        sa.Column(
            "channel",
            PG_ENUM(name="channel_type", create_type=False),
            nullable=False,
        ),
        sa.Column("destination", sa.Text(), nullable=False),
        sa.Column(
            "status",
            PG_ENUM(name="notification_status", create_type=False),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index(f"ix_{_DELIVERIES}_tenant_id", _DELIVERIES, ["tenant_id"])
    op.create_index(f"ix_{_DELIVERIES}_notification", _DELIVERIES, ["notification_id"])
    op.create_index(f"ix_{_DELIVERIES}_tenant_status", _DELIVERIES, ["tenant_id", "status"])

    for statement in enable_rls_statements(_DELIVERIES):
        op.execute(statement)


def downgrade() -> None:
    for statement in disable_rls_statements(_DELIVERIES):
        op.execute(statement)
    op.drop_index(f"ix_{_DELIVERIES}_tenant_status", table_name=_DELIVERIES)
    op.drop_index(f"ix_{_DELIVERIES}_notification", table_name=_DELIVERIES)
    op.drop_index(f"ix_{_DELIVERIES}_tenant_id", table_name=_DELIVERIES)
    op.drop_table(_DELIVERIES)

    op.add_column(
        "notifications",
        sa.Column("error_message", sa.Text(), nullable=True),
    )
    op.add_column(
        "notifications",
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "notifications",
        sa.Column(
            "status",
            PG_ENUM(name="notification_status", create_type=False),
            nullable=False,
            server_default="pending",
        ),
    )
    op.add_column(
        "notifications",
        sa.Column(
            "channel",
            PG_ENUM(name="channel_type", create_type=False),
            nullable=False,
            server_default="email",
        ),
    )
    op.execute("DELETE FROM notifications WHERE user_id IS NULL")
    op.alter_column("notifications", "user_id", existing_type=PG_UUID(as_uuid=True), nullable=False)
    op.drop_index("ix_notifications_event_id", table_name="notifications")
    op.drop_column("notifications", "severity")
    op.drop_column("notifications", "category")
    op.drop_column("notifications", "event_id")
