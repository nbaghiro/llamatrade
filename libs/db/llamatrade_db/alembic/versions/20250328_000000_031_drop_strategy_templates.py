"""Drop the dormant strategy_templates table.

Strategy templates are a curated, code-owned catalog served from
``services/strategy/src/services/template_service.py`` (``TEMPLATES``); the
``strategy_templates`` table was never read or written by any service. Removing
it makes the in-code catalog the single source of truth. The PostgreSQL enum
types it referenced (``template_category``/``asset_class``/``template_difficulty``)
are left in place — the DB TypeDecorators still declare them.

Revision ID: 031_drop_strategy_templates
Revises: 030_add_alert_condition_values
Create Date: 2025-03-28 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "031_drop_strategy_templates"
down_revision: str | None = "030_add_alert_condition_values"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # No explicit drop_index: revision 012 dropped and re-added the ``category``
    # column, taking ``ix_strategy_templates_category`` with it, and drop_table
    # removes any surviving dependent index anyway.
    op.drop_table("strategy_templates")


def downgrade() -> None:
    op.create_table(
        "strategy_templates",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "category",
            postgresql.ENUM(name="template_category", create_type=False),
            nullable=False,
        ),
        sa.Column(
            "asset_class",
            postgresql.ENUM(name="asset_class", create_type=False),
            nullable=False,
        ),
        sa.Column("config_sexpr", sa.Text(), nullable=False),
        sa.Column("config_json", postgresql.JSONB(), nullable=False),
        sa.Column("tags", postgresql.JSONB(), nullable=True),
        sa.Column(
            "difficulty",
            postgresql.ENUM(name="template_difficulty", create_type=False),
            nullable=False,
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("usage_count", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_index("ix_strategy_templates_category", "strategy_templates", ["category"])
