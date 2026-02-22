"""Initial schema with all 27 tables.

Revision ID: 001
Revises:
Create Date: 2024-01-01 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ===================
    # Auth Models
    # ===================

    # Tenants table
    op.create_table(
        "tenants",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(100), unique=True, nullable=False),
        sa.Column("is_active", sa.Boolean(), default=True, nullable=False),
        sa.Column("settings", postgresql.JSONB(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_tenants_slug", "tenants", ["slug"])

    # Users table
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id"),
            nullable=False,
        ),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("first_name", sa.String(100), nullable=True),
        sa.Column("last_name", sa.String(100), nullable=True),
        sa.Column("role", sa.String(50), default="user", nullable=False),
        sa.Column("is_active", sa.Boolean(), default=True, nullable=False),
        sa.Column("is_verified", sa.Boolean(), default=False, nullable=False),
        sa.Column("last_login", sa.DateTime(timezone=True), nullable=True),
        sa.Column("settings", postgresql.JSONB(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_users_tenant_id", "users", ["tenant_id"])
    op.create_index("ix_users_tenant_email", "users", ["tenant_id", "email"], unique=True)

    # Alpaca Credentials table
    op.create_table(
        "alpaca_credentials",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id"),
            nullable=False,
        ),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("api_key_encrypted", sa.Text(), nullable=False),
        sa.Column("api_secret_encrypted", sa.Text(), nullable=False),
        sa.Column("is_paper", sa.Boolean(), default=True, nullable=False),
        sa.Column("is_active", sa.Boolean(), default=True, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_alpaca_credentials_tenant_id", "alpaca_credentials", ["tenant_id"])

    # API Keys table
    op.create_table(
        "api_keys",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("key_prefix", sa.String(10), nullable=False),
        sa.Column("key_hash", sa.String(64), nullable=False),
        sa.Column("scopes", postgresql.JSONB(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), default=True, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_api_keys_tenant_id", "api_keys", ["tenant_id"])
    op.create_index("ix_api_keys_user_id", "api_keys", ["user_id"])
    op.create_index("ix_api_keys_key_hash", "api_keys", ["key_hash"])

    # ===================
    # Strategy Models
    # ===================

    # Strategies table
    op.create_table(
        "strategies",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("strategy_type", sa.String(50), nullable=False),
        sa.Column("config", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("is_active", sa.Boolean(), default=True, nullable=False),
        sa.Column("is_public", sa.Boolean(), default=False, nullable=False),
        sa.Column("current_version", sa.Integer(), default=1, nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_strategies_tenant_id", "strategies", ["tenant_id"])
    op.create_index("ix_strategies_tenant_name", "strategies", ["tenant_id", "name"])

    # Strategy Versions table
    op.create_table(
        "strategy_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "strategy_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("strategies.id"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("config", postgresql.JSONB(), nullable=False),
        sa.Column("changelog", sa.Text(), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_strategy_versions_strategy_id", "strategy_versions", ["strategy_id"])
    op.create_index(
        "ix_strategy_versions_strategy_version",
        "strategy_versions",
        ["strategy_id", "version"],
        unique=True,
    )

    # Strategy Templates table (not tenant-scoped)
    op.create_table(
        "strategy_templates",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False, unique=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("category", sa.String(100), nullable=False),
        sa.Column("strategy_type", sa.String(50), nullable=False),
        sa.Column("config", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("indicators", postgresql.JSONB(), nullable=True),
        sa.Column("is_active", sa.Boolean(), default=True, nullable=False),
        sa.Column("usage_count", sa.Integer(), default=0, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_strategy_templates_category", "strategy_templates", ["category"])

    # ===================
    # Backtest Models
    # ===================

    # Backtests table
    op.create_table(
        "backtests",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("strategy_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("strategy_version", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("status", sa.String(50), default="pending", nullable=False),
        sa.Column("config", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("symbols", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("initial_capital", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_backtests_tenant_id", "backtests", ["tenant_id"])
    op.create_index("ix_backtests_tenant_status", "backtests", ["tenant_id", "status"])
    op.create_index("ix_backtests_strategy", "backtests", ["strategy_id"])

    # Backtest Results table
    op.create_table(
        "backtest_results",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "backtest_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("backtests.id"),
            nullable=False,
            unique=True,
        ),
        sa.Column("total_return", sa.Numeric(precision=18, scale=6), nullable=False),
        sa.Column("annual_return", sa.Numeric(precision=18, scale=6), nullable=False),
        sa.Column("sharpe_ratio", sa.Numeric(precision=10, scale=4), nullable=False),
        sa.Column("sortino_ratio", sa.Numeric(precision=10, scale=4), nullable=True),
        sa.Column("max_drawdown", sa.Numeric(precision=10, scale=6), nullable=False),
        sa.Column("win_rate", sa.Numeric(precision=5, scale=4), nullable=False),
        sa.Column("profit_factor", sa.Numeric(precision=10, scale=4), nullable=True),
        sa.Column("total_trades", sa.Integer(), nullable=False),
        sa.Column("winning_trades", sa.Integer(), nullable=False),
        sa.Column("losing_trades", sa.Integer(), nullable=False),
        sa.Column("avg_trade_return", sa.Numeric(precision=18, scale=6), nullable=False),
        sa.Column("final_equity", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("equity_curve", postgresql.JSONB(), nullable=True),
        sa.Column("trades", postgresql.JSONB(), nullable=True),
        sa.Column("daily_returns", postgresql.JSONB(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    # ===================
    # Trading Models
    # ===================

    # Trading Sessions table
    op.create_table(
        "trading_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("strategy_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("strategy_version", sa.Integer(), nullable=False),
        sa.Column("credentials_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("mode", sa.String(20), nullable=False),
        sa.Column("status", sa.String(50), default="stopped", nullable=False),
        sa.Column("config", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("symbols", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("stopped_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_heartbeat", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_trading_sessions_tenant_id", "trading_sessions", ["tenant_id"])
    op.create_index(
        "ix_trading_sessions_tenant_status", "trading_sessions", ["tenant_id", "status"]
    )
    op.create_index("ix_trading_sessions_strategy", "trading_sessions", ["strategy_id"])

    # Orders table
    op.create_table(
        "orders",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("trading_sessions.id"),
            nullable=False,
        ),
        sa.Column("alpaca_order_id", sa.String(100), nullable=True),
        sa.Column("client_order_id", sa.String(100), nullable=False),
        sa.Column("symbol", sa.String(20), nullable=False),
        sa.Column("side", sa.String(10), nullable=False),
        sa.Column("order_type", sa.String(20), nullable=False),
        sa.Column("time_in_force", sa.String(10), nullable=False),
        sa.Column("qty", sa.Numeric(precision=18, scale=8), nullable=False),
        sa.Column("limit_price", sa.Numeric(precision=18, scale=8), nullable=True),
        sa.Column("stop_price", sa.Numeric(precision=18, scale=8), nullable=True),
        sa.Column("status", sa.String(50), nullable=False),
        sa.Column("filled_qty", sa.Numeric(precision=18, scale=8), default=0, nullable=False),
        sa.Column("filled_avg_price", sa.Numeric(precision=18, scale=8), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("filled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("canceled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("signal_reason", sa.Text(), nullable=True),
        sa.Column("metadata", postgresql.JSONB(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_orders_tenant_id", "orders", ["tenant_id"])
    op.create_index("ix_orders_tenant_status", "orders", ["tenant_id", "status"])
    op.create_index("ix_orders_session", "orders", ["session_id"])
    op.create_index("ix_orders_symbol", "orders", ["symbol"])
    op.create_index("ix_orders_alpaca_order_id", "orders", ["alpaca_order_id"])

    # Positions table
    op.create_table(
        "positions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("trading_sessions.id"),
            nullable=False,
        ),
        sa.Column("symbol", sa.String(20), nullable=False),
        sa.Column("side", sa.String(10), nullable=False),
        sa.Column("qty", sa.Numeric(precision=18, scale=8), nullable=False),
        sa.Column("avg_entry_price", sa.Numeric(precision=18, scale=8), nullable=False),
        sa.Column("current_price", sa.Numeric(precision=18, scale=8), nullable=True),
        sa.Column("market_value", sa.Numeric(precision=18, scale=2), nullable=True),
        sa.Column("cost_basis", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("unrealized_pl", sa.Numeric(precision=18, scale=2), nullable=True),
        sa.Column("unrealized_plpc", sa.Numeric(precision=10, scale=6), nullable=True),
        sa.Column("realized_pl", sa.Numeric(precision=18, scale=2), default=0, nullable=False),
        sa.Column("is_open", sa.Boolean(), default=True, nullable=False),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_positions_tenant_id", "positions", ["tenant_id"])
    op.create_index(
        "ix_positions_session_symbol", "positions", ["session_id", "symbol"], unique=True
    )

    # ===================
    # Portfolio Models
    # ===================

    # Portfolio Summary table
    op.create_table(
        "portfolio_summary",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("equity", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("cash", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("buying_power", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("portfolio_value", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("daily_pl", sa.Numeric(precision=18, scale=2), default=0, nullable=False),
        sa.Column("daily_pl_percent", sa.Numeric(precision=10, scale=6), default=0, nullable=False),
        sa.Column("total_pl", sa.Numeric(precision=18, scale=2), default=0, nullable=False),
        sa.Column("total_pl_percent", sa.Numeric(precision=10, scale=6), default=0, nullable=False),
        sa.Column("positions", postgresql.JSONB(), nullable=True),
        sa.Column("position_count", sa.Integer(), default=0, nullable=False),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_portfolio_summary_tenant_id", "portfolio_summary", ["tenant_id"])

    # Transactions table
    op.create_table(
        "transactions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("order_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("transaction_type", sa.String(50), nullable=False),
        sa.Column("symbol", sa.String(20), nullable=True),
        sa.Column("side", sa.String(10), nullable=True),
        sa.Column("qty", sa.Numeric(precision=18, scale=8), nullable=True),
        sa.Column("price", sa.Numeric(precision=18, scale=8), nullable=True),
        sa.Column("amount", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("fees", sa.Numeric(precision=18, scale=4), default=0, nullable=False),
        sa.Column("net_amount", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("transaction_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("settlement_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("external_id", sa.String(100), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_transactions_tenant_id", "transactions", ["tenant_id"])
    op.create_index(
        "ix_transactions_tenant_date", "transactions", ["tenant_id", "transaction_date"]
    )
    op.create_index("ix_transactions_symbol", "transactions", ["symbol"])
    op.create_index("ix_transactions_type", "transactions", ["transaction_type"])
    op.create_index("ix_transactions_external_id", "transactions", ["external_id"])

    # Portfolio History table
    op.create_table(
        "portfolio_history",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("snapshot_date", sa.Date(), nullable=False),
        sa.Column("equity", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("cash", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("portfolio_value", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("daily_return", sa.Numeric(precision=10, scale=6), nullable=True),
        sa.Column("cumulative_return", sa.Numeric(precision=10, scale=6), nullable=True),
        sa.Column("positions_snapshot", postgresql.JSONB(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_portfolio_history_tenant_id", "portfolio_history", ["tenant_id"])
    op.create_index(
        "ix_portfolio_history_tenant_date",
        "portfolio_history",
        ["tenant_id", "snapshot_date"],
        unique=True,
    )

    # Performance Metrics table
    op.create_table(
        "performance_metrics",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("period_type", sa.String(20), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("total_return", sa.Numeric(precision=18, scale=6), nullable=False),
        sa.Column("annualized_return", sa.Numeric(precision=18, scale=6), nullable=True),
        sa.Column("volatility", sa.Numeric(precision=10, scale=6), nullable=True),
        sa.Column("sharpe_ratio", sa.Numeric(precision=10, scale=4), nullable=True),
        sa.Column("sortino_ratio", sa.Numeric(precision=10, scale=4), nullable=True),
        sa.Column("max_drawdown", sa.Numeric(precision=10, scale=6), nullable=True),
        sa.Column("calmar_ratio", sa.Numeric(precision=10, scale=4), nullable=True),
        sa.Column("total_trades", sa.Integer(), default=0, nullable=False),
        sa.Column("winning_trades", sa.Integer(), default=0, nullable=False),
        sa.Column("losing_trades", sa.Integer(), default=0, nullable=False),
        sa.Column("win_rate", sa.Numeric(precision=5, scale=4), nullable=True),
        sa.Column("profit_factor", sa.Numeric(precision=10, scale=4), nullable=True),
        sa.Column("realized_pl", sa.Numeric(precision=18, scale=2), default=0, nullable=False),
        sa.Column("unrealized_pl", sa.Numeric(precision=18, scale=2), default=0, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_performance_metrics_tenant_id", "performance_metrics", ["tenant_id"])
    op.create_index(
        "ix_performance_metrics_tenant_period",
        "performance_metrics",
        ["tenant_id", "period_type", "period_start"],
    )

    # ===================
    # Market Data Models (not tenant-scoped)
    # ===================

    # Bars table
    op.create_table(
        "bars",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("symbol", sa.String(20), nullable=False),
        sa.Column("timeframe", sa.String(10), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("open", sa.Numeric(precision=18, scale=8), nullable=False),
        sa.Column("high", sa.Numeric(precision=18, scale=8), nullable=False),
        sa.Column("low", sa.Numeric(precision=18, scale=8), nullable=False),
        sa.Column("close", sa.Numeric(precision=18, scale=8), nullable=False),
        sa.Column("volume", sa.BigInteger(), nullable=False),
        sa.Column("vwap", sa.Numeric(precision=18, scale=8), nullable=True),
        sa.Column("trade_count", sa.Integer(), nullable=True),
    )
    op.create_index(
        "ix_bars_symbol_timeframe_timestamp", "bars", ["symbol", "timeframe", "timestamp"]
    )
    op.create_index("ix_bars_timestamp", "bars", ["timestamp"])

    # Quotes table
    op.create_table(
        "quotes",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("symbol", sa.String(20), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("bid_price", sa.Numeric(precision=18, scale=8), nullable=False),
        sa.Column("bid_size", sa.Integer(), nullable=False),
        sa.Column("ask_price", sa.Numeric(precision=18, scale=8), nullable=False),
        sa.Column("ask_size", sa.Integer(), nullable=False),
        sa.Column("bid_exchange", sa.String(10), nullable=True),
        sa.Column("ask_exchange", sa.String(10), nullable=True),
        sa.Column("conditions", sa.String(50), nullable=True),
    )
    op.create_index("ix_quotes_symbol_timestamp", "quotes", ["symbol", "timestamp"])

    # Trades table
    op.create_table(
        "trades",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("symbol", sa.String(20), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("price", sa.Numeric(precision=18, scale=8), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column("exchange", sa.String(10), nullable=True),
        sa.Column("trade_id", sa.String(50), nullable=True),
        sa.Column("conditions", sa.String(100), nullable=True),
        sa.Column("tape", sa.String(5), nullable=True),
    )
    op.create_index("ix_trades_symbol_timestamp", "trades", ["symbol", "timestamp"])

    # ===================
    # Notification Models
    # ===================

    # Alerts table
    op.create_table(
        "alerts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("alert_type", sa.String(50), nullable=False),
        sa.Column("symbol", sa.String(20), nullable=True),
        sa.Column("condition", postgresql.JSONB(), nullable=False),
        sa.Column("status", sa.String(20), default="active", nullable=False),
        sa.Column("channels", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("cooldown_minutes", sa.Integer(), default=60, nullable=False),
        sa.Column("last_triggered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("trigger_count", sa.Integer(), default=0, nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_alerts_tenant_id", "alerts", ["tenant_id"])
    op.create_index("ix_alerts_tenant_status", "alerts", ["tenant_id", "status"])
    op.create_index("ix_alerts_symbol", "alerts", ["symbol"])

    # Notifications table
    op.create_table(
        "notifications",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("alert_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("notification_type", sa.String(50), nullable=False),
        sa.Column("channel", sa.String(20), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("data", postgresql.JSONB(), nullable=True),
        sa.Column("status", sa.String(20), default="pending", nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_notifications_tenant_id", "notifications", ["tenant_id"])
    op.create_index("ix_notifications_tenant_created", "notifications", ["tenant_id", "created_at"])
    op.create_index("ix_notifications_user", "notifications", ["user_id"])

    # Notification Channels table
    op.create_table(
        "notification_channels",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("channel_type", sa.String(20), nullable=False),
        sa.Column("destination", sa.String(320), nullable=False),
        sa.Column("is_verified", sa.Boolean(), default=False, nullable=False),
        sa.Column("is_enabled", sa.Boolean(), default=True, nullable=False),
        sa.Column("preferences", postgresql.JSONB(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_notification_channels_tenant_id", "notification_channels", ["tenant_id"])
    op.create_index(
        "ix_notification_channels_tenant_user",
        "notification_channels",
        ["tenant_id", "user_id"],
    )

    # Webhooks table
    op.create_table(
        "webhooks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("secret", sa.String(255), nullable=True),
        sa.Column("events", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("headers", postgresql.JSONB(), nullable=True),
        sa.Column("is_active", sa.Boolean(), default=True, nullable=False),
        sa.Column("last_triggered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_status_code", sa.Integer(), nullable=True),
        sa.Column("failure_count", sa.Integer(), default=0, nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_webhooks_tenant_id", "webhooks", ["tenant_id"])
    op.create_index("ix_webhooks_tenant_active", "webhooks", ["tenant_id", "is_active"])

    # ===================
    # Billing Models
    # ===================

    # Plans table (not tenant-scoped)
    op.create_table(
        "plans",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False, unique=True),
        sa.Column("display_name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("tier", sa.String(50), nullable=False),
        sa.Column("price_monthly", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("price_yearly", sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column("stripe_price_id_monthly", sa.String(100), nullable=True),
        sa.Column("stripe_price_id_yearly", sa.String(100), nullable=True),
        sa.Column("features", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("limits", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("is_active", sa.Boolean(), default=True, nullable=False),
        sa.Column("sort_order", sa.Integer(), default=0, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    # Subscriptions table
    op.create_table(
        "subscriptions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "plan_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("plans.id"),
            nullable=False,
        ),
        sa.Column("status", sa.String(50), nullable=False),
        sa.Column("billing_cycle", sa.String(20), nullable=False),
        sa.Column("stripe_subscription_id", sa.String(100), nullable=True),
        sa.Column("stripe_customer_id", sa.String(100), nullable=True),
        sa.Column("current_period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("current_period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("canceled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancel_at_period_end", sa.Boolean(), default=False, nullable=False),
        sa.Column("trial_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("trial_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata", postgresql.JSONB(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_subscriptions_tenant_id", "subscriptions", ["tenant_id"])
    op.create_index("ix_subscriptions_tenant_status", "subscriptions", ["tenant_id", "status"])
    op.create_index("ix_subscriptions_stripe", "subscriptions", ["stripe_subscription_id"])

    # Usage Records table
    op.create_table(
        "usage_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "subscription_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("subscriptions.id"),
            nullable=False,
        ),
        sa.Column("metric_name", sa.String(100), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("reported_to_stripe", sa.Boolean(), default=False, nullable=False),
        sa.Column("stripe_usage_record_id", sa.String(100), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_usage_records_tenant_id", "usage_records", ["tenant_id"])
    op.create_index(
        "ix_usage_records_tenant_period",
        "usage_records",
        ["tenant_id", "period_start", "period_end"],
    )
    op.create_index("ix_usage_records_metric", "usage_records", ["metric_name"])

    # Invoices table
    op.create_table(
        "invoices",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "subscription_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("subscriptions.id"),
            nullable=True,
        ),
        sa.Column("stripe_invoice_id", sa.String(100), nullable=False, unique=True),
        sa.Column("invoice_number", sa.String(50), nullable=True),
        sa.Column("status", sa.String(50), nullable=False),
        sa.Column("amount_due", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("amount_paid", sa.Numeric(precision=10, scale=2), default=0, nullable=False),
        sa.Column("currency", sa.String(3), default="usd", nullable=False),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("due_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("hosted_invoice_url", sa.Text(), nullable=True),
        sa.Column("invoice_pdf", sa.Text(), nullable=True),
        sa.Column("line_items", postgresql.JSONB(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_invoices_tenant_id", "invoices", ["tenant_id"])
    op.create_index("ix_invoices_tenant_status", "invoices", ["tenant_id", "status"])
    op.create_index("ix_invoices_stripe", "invoices", ["stripe_invoice_id"])


def downgrade() -> None:
    # Drop tables in reverse order of creation (respecting foreign key constraints)

    # Billing
    op.drop_table("invoices")
    op.drop_table("usage_records")
    op.drop_table("subscriptions")
    op.drop_table("plans")

    # Notification
    op.drop_table("webhooks")
    op.drop_table("notification_channels")
    op.drop_table("notifications")
    op.drop_table("alerts")

    # Market Data
    op.drop_table("trades")
    op.drop_table("quotes")
    op.drop_table("bars")

    # Portfolio
    op.drop_table("performance_metrics")
    op.drop_table("portfolio_history")
    op.drop_table("transactions")
    op.drop_table("portfolio_summary")

    # Trading
    op.drop_table("positions")
    op.drop_table("orders")
    op.drop_table("trading_sessions")

    # Backtest
    op.drop_table("backtest_results")
    op.drop_table("backtests")

    # Strategy
    op.drop_table("strategy_templates")
    op.drop_table("strategy_versions")
    op.drop_table("strategies")

    # Auth
    op.drop_table("api_keys")
    op.drop_table("alpaca_credentials")
    op.drop_table("users")
    op.drop_table("tenants")
