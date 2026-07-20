"""Decimalize risk_configs + daily_pnl money columns (Float → Numeric).

Everything on the money path is Decimal; these were the last two SQL-Float money
tables in the trading domain (orders/positions/ledger were already Numeric).

Revision ID: 028_decimalize_risk_and_pnl
Revises: 027_add_agent_message_thinking
Create Date: 2025-03-25 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "028_decimalize_risk_and_pnl"
down_revision: str | None = "027_add_agent_message_thinking"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# (table, column) money columns migrated float → Numeric(18, 8).
_MONEY_COLUMNS: list[tuple[str, str]] = [
    ("risk_configs", "max_position_size_pct"),
    ("risk_configs", "max_position_value"),
    ("risk_configs", "max_daily_loss_pct"),
    ("risk_configs", "max_daily_loss_value"),
    ("risk_configs", "max_drawdown_pct"),
    ("risk_configs", "max_order_value"),
    ("daily_pnl", "realized_pnl"),
    ("daily_pnl", "unrealized_pnl"),
    ("daily_pnl", "total_pnl"),
    ("daily_pnl", "equity_start"),
    ("daily_pnl", "equity_high"),
    ("daily_pnl", "equity_low"),
    ("daily_pnl", "equity_end"),
    ("daily_pnl", "max_drawdown_pct"),
]


def upgrade() -> None:
    """Widen the trading risk/P&L money columns from float to Numeric(18, 8)."""
    for table, column in _MONEY_COLUMNS:
        op.alter_column(
            table,
            column,
            type_=sa.Numeric(precision=18, scale=8),
            postgresql_using=f"{column}::numeric(18,8)",
        )


def downgrade() -> None:
    """Revert the money columns to double precision."""
    for table, column in _MONEY_COLUMNS:
        op.alter_column(
            table,
            column,
            type_=sa.Float(),
            postgresql_using=f"{column}::double precision",
        )
