"""Drop derived columns from strategy_versions; the DSL string is the source of truth.

``config_json`` (reproducible via ``to_json(parse(config_sexpr))``) and ``parameters``/``ui_state``
(the visual tree is derived client-side via ``fromDSLString``) are no longer stored — only the DSL
string ``config_sexpr``, plus the ``symbols``/``timeframe`` projections kept for querying.

Revision ID: 032_drop_version_derived_cols
Revises: 031_drop_strategy_templates
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "032_drop_version_derived_cols"
down_revision: str | None = "031_drop_strategy_templates"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_column("strategy_versions", "config_json")
    op.drop_column("strategy_versions", "parameters")


def downgrade() -> None:
    op.add_column(
        "strategy_versions",
        sa.Column(
            "parameters",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
    )
    op.add_column(
        "strategy_versions",
        sa.Column(
            "config_json",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
    )
