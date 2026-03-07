"""Convert string-based enum columns to PostgreSQL native ENUM types.

This migration converts all string-based enum columns to PostgreSQL native ENUM types.
This provides:
- Human-readable values in database queries
- Database-level validation of enum values
- Better data integrity

Proto enum definitions remain the source of truth for API integer values.
Conversion between proto ints and DB enum strings happens at the service layer.

Proto enum value mappings (for reference):
- OrderSide: BUY=1, SELL=2
- OrderType: MARKET=1, LIMIT=2, STOP=3, STOP_LIMIT=4, TRAILING_STOP=5
- OrderStatus: PENDING=1, SUBMITTED=2, ACCEPTED=3, PARTIAL=4, FILLED=5,
               CANCELLED=6, REJECTED=7, EXPIRED=8
- TimeInForce: DAY=1, GTC=2, IOC=3, FOK=4, OPG=5, CLS=6
- PositionSide: LONG=1, SHORT=2
- ExecutionMode: PAPER=1, LIVE=2
- ExecutionStatus: PENDING=1, RUNNING=2, PAUSED=3, STOPPED=4, ERROR=5
- StrategyStatus: DRAFT=1, ACTIVE=2, PAUSED=3, ARCHIVED=4
- BacktestStatus: PENDING=1, RUNNING=2, COMPLETED=3, FAILED=4, CANCELLED=5
- SubscriptionStatus: ACTIVE=1, PAST_DUE=2, CANCELED=3, TRIALING=4, PAUSED=5
- PlanTier: FREE=1, STARTER=2, PRO=3
- BillingInterval: MONTHLY=1, YEARLY=2
- NotificationType: INFO=1, SUCCESS=2, WARNING=3, ERROR=4, ALERT=5, ORDER=6, TRADE=7, SYSTEM=8
- ChannelType: EMAIL=1, SMS=2, PUSH=3, WEBHOOK=4, SLACK=5, DISCORD=6, TELEGRAM=7
- AlertConditionType: PRICE_ABOVE=1, PRICE_BELOW=2, PRICE_CHANGE_PERCENT=3,
                      VOLUME_ABOVE=4, RSI_ABOVE=5, RSI_BELOW=6, ORDER_FILLED=7, STRATEGY_SIGNAL=8

Revision ID: 009_postgres_enums
Revises: 008_strategy_performance
Create Date: 2024-09-01

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "009_postgres_enums"
down_revision: str | None = "008_strategy_performance"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Convert string-based enum columns to PostgreSQL native ENUM types."""

    # =========================================================================
    # STEP 1: CREATE ALL POSTGRES ENUM TYPES
    # =========================================================================

    # Trading enums
    op.execute("CREATE TYPE order_side AS ENUM ('buy', 'sell')")
    op.execute(
        "CREATE TYPE order_type AS ENUM ('market', 'limit', 'stop', 'stop_limit', 'trailing_stop')"
    )
    op.execute(
        "CREATE TYPE order_status AS ENUM "
        "('pending', 'submitted', 'accepted', 'partial', 'filled', "
        "'cancelled', 'rejected', 'expired')"
    )
    op.execute("CREATE TYPE time_in_force AS ENUM ('day', 'gtc', 'ioc', 'fok', 'opg', 'cls')")
    op.execute("CREATE TYPE position_side AS ENUM ('long', 'short')")
    op.execute("CREATE TYPE session_status AS ENUM ('active', 'paused', 'stopped', 'error')")

    # Common enums
    op.execute("CREATE TYPE execution_mode AS ENUM ('paper', 'live')")
    op.execute(
        "CREATE TYPE execution_status AS ENUM ('pending', 'running', 'paused', 'stopped', 'error')"
    )

    # Strategy enums
    op.execute("CREATE TYPE strategy_status AS ENUM ('draft', 'active', 'paused', 'archived')")

    # Backtest enums
    op.execute(
        "CREATE TYPE backtest_status AS ENUM "
        "('pending', 'running', 'completed', 'failed', 'cancelled')"
    )

    # Billing enums
    op.execute(
        "CREATE TYPE subscription_status AS ENUM "
        "('active', 'past_due', 'canceled', 'trialing', 'paused')"
    )
    op.execute("CREATE TYPE plan_tier AS ENUM ('free', 'starter', 'pro')")
    op.execute("CREATE TYPE billing_interval AS ENUM ('monthly', 'yearly')")
    op.execute(
        "CREATE TYPE invoice_status AS ENUM ('draft', 'open', 'paid', 'void', 'uncollectible')"
    )

    # Notification enums
    op.execute(
        "CREATE TYPE notification_type AS ENUM "
        "('info', 'success', 'warning', 'error', 'alert', 'order', 'trade', 'system')"
    )
    op.execute(
        "CREATE TYPE channel_type AS ENUM "
        "('email', 'sms', 'push', 'webhook', 'slack', 'discord', 'telegram')"
    )
    op.execute(
        "CREATE TYPE alert_condition_type AS ENUM "
        "('price_above', 'price_below', 'price_change_percent', 'volume_above', "
        "'rsi_above', 'rsi_below', 'order_filled', 'strategy_signal')"
    )
    op.execute("CREATE TYPE alert_status AS ENUM ('active', 'triggered', 'disabled')")
    op.execute("CREATE TYPE notification_status AS ENUM ('pending', 'sent', 'failed', 'read')")

    # =========================================================================
    # STEP 2: CONVERT ORDERS TABLE
    # =========================================================================

    # Order.side: buy, sell
    op.add_column("orders", sa.Column("side_enum", sa.String(10), nullable=True))
    op.execute("""
        UPDATE orders SET side_enum = CASE LOWER(side)
            WHEN 'buy' THEN 'buy'
            WHEN 'sell' THEN 'sell'
            ELSE 'buy'
        END
    """)
    op.drop_column("orders", "side")
    op.execute("ALTER TABLE orders ADD COLUMN side order_side")
    op.execute("UPDATE orders SET side = side_enum::order_side")
    op.alter_column("orders", "side", nullable=False)
    op.drop_column("orders", "side_enum")

    # Order.order_type: market, limit, stop, stop_limit, trailing_stop
    op.add_column("orders", sa.Column("order_type_enum", sa.String(20), nullable=True))
    op.execute("""
        UPDATE orders SET order_type_enum = CASE LOWER(order_type)
            WHEN 'market' THEN 'market'
            WHEN 'limit' THEN 'limit'
            WHEN 'stop' THEN 'stop'
            WHEN 'stop_limit' THEN 'stop_limit'
            WHEN 'trailing_stop' THEN 'trailing_stop'
            ELSE 'market'
        END
    """)
    op.drop_column("orders", "order_type")
    op.execute("ALTER TABLE orders ADD COLUMN order_type order_type")
    op.execute("UPDATE orders SET order_type = order_type_enum::order_type")
    op.alter_column("orders", "order_type", nullable=False)
    op.drop_column("orders", "order_type_enum")

    # Order.status: pending, submitted, accepted, partial, filled, cancelled, rejected, expired
    op.add_column("orders", sa.Column("status_enum", sa.String(20), nullable=True))
    op.execute("""
        UPDATE orders SET status_enum = CASE LOWER(status)
            WHEN 'pending' THEN 'pending'
            WHEN 'submitted' THEN 'submitted'
            WHEN 'new' THEN 'submitted'
            WHEN 'accepted' THEN 'accepted'
            WHEN 'partial' THEN 'partial'
            WHEN 'partially_filled' THEN 'partial'
            WHEN 'filled' THEN 'filled'
            WHEN 'cancelled' THEN 'cancelled'
            WHEN 'canceled' THEN 'cancelled'
            WHEN 'rejected' THEN 'rejected'
            WHEN 'expired' THEN 'expired'
            ELSE 'pending'
        END
    """)
    op.drop_column("orders", "status")
    op.execute("ALTER TABLE orders ADD COLUMN status order_status")
    op.execute("UPDATE orders SET status = status_enum::order_status")
    op.alter_column("orders", "status", nullable=False)
    op.drop_column("orders", "status_enum")

    # Order.time_in_force: day, gtc, ioc, fok, opg, cls
    op.add_column("orders", sa.Column("time_in_force_enum", sa.String(10), nullable=True))
    op.execute("""
        UPDATE orders SET time_in_force_enum = CASE LOWER(time_in_force)
            WHEN 'day' THEN 'day'
            WHEN 'gtc' THEN 'gtc'
            WHEN 'ioc' THEN 'ioc'
            WHEN 'fok' THEN 'fok'
            WHEN 'opg' THEN 'opg'
            WHEN 'cls' THEN 'cls'
            ELSE 'day'
        END
    """)
    op.drop_column("orders", "time_in_force")
    op.execute("ALTER TABLE orders ADD COLUMN time_in_force time_in_force")
    op.execute("UPDATE orders SET time_in_force = time_in_force_enum::time_in_force")
    op.alter_column("orders", "time_in_force", nullable=False)
    op.drop_column("orders", "time_in_force_enum")

    # =========================================================================
    # STEP 3: CONVERT POSITIONS TABLE
    # =========================================================================

    # Position.side: long, short
    op.add_column("positions", sa.Column("side_enum", sa.String(10), nullable=True))
    op.execute("""
        UPDATE positions SET side_enum = CASE LOWER(side)
            WHEN 'long' THEN 'long'
            WHEN 'short' THEN 'short'
            ELSE 'long'
        END
    """)
    op.drop_column("positions", "side")
    op.execute("ALTER TABLE positions ADD COLUMN side position_side")
    op.execute("UPDATE positions SET side = side_enum::position_side")
    op.alter_column("positions", "side", nullable=False)
    op.drop_column("positions", "side_enum")

    # =========================================================================
    # STEP 4: CONVERT TRADING_SESSIONS TABLE
    # =========================================================================

    # TradingSession.mode: paper, live
    op.add_column("trading_sessions", sa.Column("mode_enum", sa.String(10), nullable=True))
    op.execute("""
        UPDATE trading_sessions SET mode_enum = CASE LOWER(mode)
            WHEN 'paper' THEN 'paper'
            WHEN 'live' THEN 'live'
            ELSE 'paper'
        END
    """)
    op.drop_column("trading_sessions", "mode")
    op.execute("ALTER TABLE trading_sessions ADD COLUMN mode execution_mode")
    op.execute("UPDATE trading_sessions SET mode = mode_enum::execution_mode")
    op.alter_column("trading_sessions", "mode", nullable=False)
    op.drop_column("trading_sessions", "mode_enum")

    # TradingSession.status: active, paused, stopped, error
    op.add_column("trading_sessions", sa.Column("status_enum", sa.String(20), nullable=True))
    op.execute("""
        UPDATE trading_sessions SET status_enum = CASE LOWER(status)
            WHEN 'active' THEN 'active'
            WHEN 'running' THEN 'active'
            WHEN 'paused' THEN 'paused'
            WHEN 'stopped' THEN 'stopped'
            WHEN 'error' THEN 'error'
            ELSE 'stopped'
        END
    """)
    op.drop_column("trading_sessions", "status")
    op.execute("ALTER TABLE trading_sessions ADD COLUMN status session_status")
    op.execute("UPDATE trading_sessions SET status = status_enum::session_status")
    op.alter_column("trading_sessions", "status", nullable=False)
    op.drop_column("trading_sessions", "status_enum")

    # =========================================================================
    # STEP 5: CONVERT STRATEGIES TABLE
    # =========================================================================

    # Strategy.status: draft, active, paused, archived
    # First drop old enum type if exists (from previous schema)
    op.execute("DROP TYPE IF EXISTS strategy_status_enum CASCADE")

    # Note: strategies.status may be integer (from previous partial migration) or string
    # Handle both cases by checking the column type
    op.add_column("strategies", sa.Column("status_enum", sa.String(20), nullable=True))
    op.execute("""
        UPDATE strategies SET status_enum = CASE
            -- Handle integer values (from previous migration)
            WHEN status::text ~ '^[0-9]+$' THEN
                CASE status::integer
                    WHEN 1 THEN 'draft'
                    WHEN 2 THEN 'active'
                    WHEN 3 THEN 'paused'
                    WHEN 4 THEN 'archived'
                    ELSE 'draft'
                END
            -- Handle string values
            ELSE
                CASE LOWER(status::text)
                    WHEN 'draft' THEN 'draft'
                    WHEN 'active' THEN 'active'
                    WHEN 'paused' THEN 'paused'
                    WHEN 'archived' THEN 'archived'
                    ELSE 'draft'
                END
        END
    """)
    op.drop_column("strategies", "status")
    op.execute("ALTER TABLE strategies ADD COLUMN status strategy_status")
    op.execute("UPDATE strategies SET status = status_enum::strategy_status")
    op.alter_column("strategies", "status", nullable=False)
    op.drop_column("strategies", "status_enum")

    # =========================================================================
    # STEP 6: CONVERT STRATEGY_EXECUTIONS TABLE
    # =========================================================================
    # Note: strategy_executions already has mode and status columns using
    # execution_mode_enum and execution_status_enum with UPPERCASE values.
    # We need to convert to lowercase enum types.

    # StrategyExecution.mode: paper, live (convert from UPPERCASE enum to lowercase enum)
    # First, save data to temp column
    op.add_column("strategy_executions", sa.Column("mode_temp", sa.String(10), nullable=True))
    op.execute("""
        UPDATE strategy_executions SET mode_temp = LOWER(mode::text)
    """)
    # Drop old column (removes dependency on old enum type)
    op.drop_column("strategy_executions", "mode")
    # Add new column with new enum type
    op.execute("ALTER TABLE strategy_executions ADD COLUMN mode execution_mode")
    op.execute("UPDATE strategy_executions SET mode = mode_temp::execution_mode")
    op.alter_column("strategy_executions", "mode", nullable=False)
    op.drop_column("strategy_executions", "mode_temp")

    # StrategyExecution.status: pending, running, paused, stopped, error
    op.add_column("strategy_executions", sa.Column("status_temp", sa.String(20), nullable=True))
    op.execute("""
        UPDATE strategy_executions SET status_temp = LOWER(status::text)
    """)
    op.drop_column("strategy_executions", "status")
    op.execute("ALTER TABLE strategy_executions ADD COLUMN status execution_status")
    op.execute("UPDATE strategy_executions SET status = status_temp::execution_status")
    op.alter_column("strategy_executions", "status", nullable=False)
    op.drop_column("strategy_executions", "status_temp")

    # Now drop old enum types (no longer referenced)
    op.execute("DROP TYPE IF EXISTS execution_mode_enum")
    op.execute("DROP TYPE IF EXISTS execution_status_enum")

    # =========================================================================
    # STEP 7: CONVERT BACKTESTS TABLE
    # =========================================================================

    # Backtest.status: pending, running, completed, failed, cancelled
    op.add_column("backtests", sa.Column("status_enum", sa.String(20), nullable=True))
    op.execute("""
        UPDATE backtests SET status_enum = CASE LOWER(status)
            WHEN 'pending' THEN 'pending'
            WHEN 'running' THEN 'running'
            WHEN 'completed' THEN 'completed'
            WHEN 'success' THEN 'completed'
            WHEN 'failed' THEN 'failed'
            WHEN 'error' THEN 'failed'
            WHEN 'cancelled' THEN 'cancelled'
            WHEN 'canceled' THEN 'cancelled'
            ELSE 'pending'
        END
    """)
    op.drop_column("backtests", "status")
    op.execute("ALTER TABLE backtests ADD COLUMN status backtest_status")
    op.execute("UPDATE backtests SET status = status_enum::backtest_status")
    op.alter_column("backtests", "status", nullable=False)
    op.drop_column("backtests", "status_enum")

    # =========================================================================
    # STEP 8: CONVERT SUBSCRIPTIONS TABLE
    # =========================================================================

    # Subscription.status: active, past_due, canceled, trialing, paused
    op.add_column("subscriptions", sa.Column("status_enum", sa.String(20), nullable=True))
    op.execute("""
        UPDATE subscriptions SET status_enum = CASE LOWER(status)
            WHEN 'active' THEN 'active'
            WHEN 'past_due' THEN 'past_due'
            WHEN 'canceled' THEN 'canceled'
            WHEN 'cancelled' THEN 'canceled'
            WHEN 'trialing' THEN 'trialing'
            WHEN 'paused' THEN 'paused'
            ELSE 'active'
        END
    """)
    op.drop_column("subscriptions", "status")
    op.execute("ALTER TABLE subscriptions ADD COLUMN status subscription_status")
    op.execute("UPDATE subscriptions SET status = status_enum::subscription_status")
    op.alter_column("subscriptions", "status", nullable=False)
    op.drop_column("subscriptions", "status_enum")

    # Subscription.billing_cycle: monthly, yearly
    op.add_column("subscriptions", sa.Column("billing_cycle_enum", sa.String(10), nullable=True))
    op.execute("""
        UPDATE subscriptions SET billing_cycle_enum = CASE LOWER(billing_cycle)
            WHEN 'monthly' THEN 'monthly'
            WHEN 'yearly' THEN 'yearly'
            WHEN 'annual' THEN 'yearly'
            ELSE 'monthly'
        END
    """)
    op.drop_column("subscriptions", "billing_cycle")
    op.execute("ALTER TABLE subscriptions ADD COLUMN billing_cycle billing_interval")
    op.execute("UPDATE subscriptions SET billing_cycle = billing_cycle_enum::billing_interval")
    op.alter_column("subscriptions", "billing_cycle", nullable=False)
    op.drop_column("subscriptions", "billing_cycle_enum")

    # =========================================================================
    # STEP 9: CONVERT PLANS TABLE
    # =========================================================================

    # Plan.tier: free, starter, pro
    op.add_column("plans", sa.Column("tier_enum", sa.String(20), nullable=True))
    op.execute("""
        UPDATE plans SET tier_enum = CASE LOWER(tier)
            WHEN 'free' THEN 'free'
            WHEN 'starter' THEN 'starter'
            WHEN 'pro' THEN 'pro'
            WHEN 'professional' THEN 'pro'
            WHEN 'enterprise' THEN 'pro'
            ELSE 'free'
        END
    """)
    op.drop_column("plans", "tier")
    op.execute("ALTER TABLE plans ADD COLUMN tier plan_tier")
    op.execute("UPDATE plans SET tier = tier_enum::plan_tier")
    op.alter_column("plans", "tier", nullable=False)
    op.drop_column("plans", "tier_enum")

    # =========================================================================
    # STEP 10: CONVERT INVOICES TABLE
    # =========================================================================

    # Invoice.status: draft, open, paid, void, uncollectible
    op.add_column("invoices", sa.Column("status_enum", sa.String(20), nullable=True))
    op.execute("""
        UPDATE invoices SET status_enum = CASE LOWER(status)
            WHEN 'draft' THEN 'draft'
            WHEN 'open' THEN 'open'
            WHEN 'paid' THEN 'paid'
            WHEN 'void' THEN 'void'
            WHEN 'uncollectible' THEN 'uncollectible'
            ELSE 'draft'
        END
    """)
    op.drop_column("invoices", "status")
    op.execute("ALTER TABLE invoices ADD COLUMN status invoice_status")
    op.execute("UPDATE invoices SET status = status_enum::invoice_status")
    op.alter_column("invoices", "status", nullable=False)
    op.drop_column("invoices", "status_enum")

    # =========================================================================
    # STEP 11: CONVERT ALERTS TABLE
    # =========================================================================

    # Alert.alert_type: price_above, price_below, etc.
    op.add_column("alerts", sa.Column("alert_type_enum", sa.String(30), nullable=True))
    op.execute("""
        UPDATE alerts SET alert_type_enum = CASE LOWER(alert_type)
            WHEN 'price_above' THEN 'price_above'
            WHEN 'price_below' THEN 'price_below'
            WHEN 'price_change_percent' THEN 'price_change_percent'
            WHEN 'percent_change' THEN 'price_change_percent'
            WHEN 'volume_above' THEN 'volume_above'
            WHEN 'rsi_above' THEN 'rsi_above'
            WHEN 'rsi_below' THEN 'rsi_below'
            WHEN 'order_filled' THEN 'order_filled'
            WHEN 'strategy_signal' THEN 'strategy_signal'
            ELSE 'price_above'
        END
    """)
    op.drop_column("alerts", "alert_type")
    op.execute("ALTER TABLE alerts ADD COLUMN alert_type alert_condition_type")
    op.execute("UPDATE alerts SET alert_type = alert_type_enum::alert_condition_type")
    op.alter_column("alerts", "alert_type", nullable=False)
    op.drop_column("alerts", "alert_type_enum")

    # Alert.status: active, triggered, disabled
    op.add_column("alerts", sa.Column("status_enum", sa.String(20), nullable=True))
    op.execute("""
        UPDATE alerts SET status_enum = CASE LOWER(status)
            WHEN 'active' THEN 'active'
            WHEN 'triggered' THEN 'triggered'
            WHEN 'disabled' THEN 'disabled'
            ELSE 'active'
        END
    """)
    op.drop_column("alerts", "status")
    op.execute("ALTER TABLE alerts ADD COLUMN status alert_status")
    op.execute("UPDATE alerts SET status = status_enum::alert_status")
    op.alter_column("alerts", "status", nullable=False)
    op.drop_column("alerts", "status_enum")

    # =========================================================================
    # STEP 12: CONVERT NOTIFICATIONS TABLE
    # =========================================================================

    # Notification.notification_type: info, success, warning, error, alert, order, trade, system
    op.add_column(
        "notifications", sa.Column("notification_type_enum", sa.String(20), nullable=True)
    )
    op.execute("""
        UPDATE notifications SET notification_type_enum = CASE LOWER(notification_type)
            WHEN 'info' THEN 'info'
            WHEN 'success' THEN 'success'
            WHEN 'warning' THEN 'warning'
            WHEN 'error' THEN 'error'
            WHEN 'alert' THEN 'alert'
            WHEN 'order' THEN 'order'
            WHEN 'order_fill' THEN 'order'
            WHEN 'trade' THEN 'trade'
            WHEN 'system' THEN 'system'
            ELSE 'info'
        END
    """)
    op.drop_column("notifications", "notification_type")
    op.execute("ALTER TABLE notifications ADD COLUMN notification_type notification_type")
    op.execute(
        "UPDATE notifications SET notification_type = notification_type_enum::notification_type"
    )
    op.alter_column("notifications", "notification_type", nullable=False)
    op.drop_column("notifications", "notification_type_enum")

    # Notification.channel: email, sms, push, webhook, slack, discord, telegram
    op.add_column("notifications", sa.Column("channel_enum", sa.String(20), nullable=True))
    op.execute("""
        UPDATE notifications SET channel_enum = CASE LOWER(channel)
            WHEN 'email' THEN 'email'
            WHEN 'sms' THEN 'sms'
            WHEN 'push' THEN 'push'
            WHEN 'in_app' THEN 'push'
            WHEN 'webhook' THEN 'webhook'
            WHEN 'slack' THEN 'slack'
            WHEN 'discord' THEN 'discord'
            WHEN 'telegram' THEN 'telegram'
            ELSE 'email'
        END
    """)
    op.drop_column("notifications", "channel")
    op.execute("ALTER TABLE notifications ADD COLUMN channel channel_type")
    op.execute("UPDATE notifications SET channel = channel_enum::channel_type")
    op.alter_column("notifications", "channel", nullable=False)
    op.drop_column("notifications", "channel_enum")

    # Notification.status: pending, sent, failed, read
    op.add_column("notifications", sa.Column("status_enum", sa.String(20), nullable=True))
    op.execute("""
        UPDATE notifications SET status_enum = CASE LOWER(status)
            WHEN 'pending' THEN 'pending'
            WHEN 'sent' THEN 'sent'
            WHEN 'failed' THEN 'failed'
            WHEN 'read' THEN 'read'
            ELSE 'pending'
        END
    """)
    op.drop_column("notifications", "status")
    op.execute("ALTER TABLE notifications ADD COLUMN status notification_status")
    op.execute("UPDATE notifications SET status = status_enum::notification_status")
    op.alter_column("notifications", "status", nullable=False)
    op.drop_column("notifications", "status_enum")

    # =========================================================================
    # STEP 13: CONVERT NOTIFICATION_CHANNELS TABLE
    # =========================================================================

    # NotificationChannel.channel_type: email, sms, push, webhook, slack, discord, telegram
    op.add_column(
        "notification_channels", sa.Column("channel_type_enum", sa.String(20), nullable=True)
    )
    op.execute("""
        UPDATE notification_channels SET channel_type_enum = CASE LOWER(channel_type)
            WHEN 'email' THEN 'email'
            WHEN 'sms' THEN 'sms'
            WHEN 'push' THEN 'push'
            WHEN 'webhook' THEN 'webhook'
            WHEN 'slack' THEN 'slack'
            WHEN 'discord' THEN 'discord'
            WHEN 'telegram' THEN 'telegram'
            ELSE 'email'
        END
    """)
    op.drop_column("notification_channels", "channel_type")
    op.execute("ALTER TABLE notification_channels ADD COLUMN channel_type channel_type")
    op.execute("UPDATE notification_channels SET channel_type = channel_type_enum::channel_type")
    op.alter_column("notification_channels", "channel_type", nullable=False)
    op.drop_column("notification_channels", "channel_type_enum")


def downgrade() -> None:
    """Convert PostgreSQL ENUM columns back to strings."""

    # =========================================================================
    # NOTIFICATION_CHANNELS TABLE
    # =========================================================================
    op.add_column(
        "notification_channels", sa.Column("channel_type_str", sa.String(20), nullable=True)
    )
    op.execute("""
        UPDATE notification_channels SET channel_type_str = channel_type::text
    """)
    op.alter_column("notification_channels", "channel_type_str", nullable=False)
    op.drop_column("notification_channels", "channel_type")
    op.alter_column("notification_channels", "channel_type_str", new_column_name="channel_type")

    # =========================================================================
    # NOTIFICATIONS TABLE
    # =========================================================================
    op.add_column("notifications", sa.Column("status_str", sa.String(20), nullable=True))
    op.execute("UPDATE notifications SET status_str = status::text")
    op.alter_column("notifications", "status_str", nullable=False)
    op.drop_column("notifications", "status")
    op.alter_column("notifications", "status_str", new_column_name="status")

    op.add_column("notifications", sa.Column("channel_str", sa.String(20), nullable=True))
    op.execute("UPDATE notifications SET channel_str = channel::text")
    op.alter_column("notifications", "channel_str", nullable=False)
    op.drop_column("notifications", "channel")
    op.alter_column("notifications", "channel_str", new_column_name="channel")

    op.add_column("notifications", sa.Column("notification_type_str", sa.String(50), nullable=True))
    op.execute("UPDATE notifications SET notification_type_str = notification_type::text")
    op.alter_column("notifications", "notification_type_str", nullable=False)
    op.drop_column("notifications", "notification_type")
    op.alter_column("notifications", "notification_type_str", new_column_name="notification_type")

    # =========================================================================
    # ALERTS TABLE
    # =========================================================================
    op.add_column("alerts", sa.Column("status_str", sa.String(20), nullable=True))
    op.execute("UPDATE alerts SET status_str = status::text")
    op.alter_column("alerts", "status_str", nullable=False)
    op.drop_column("alerts", "status")
    op.alter_column("alerts", "status_str", new_column_name="status")

    op.add_column("alerts", sa.Column("alert_type_str", sa.String(50), nullable=True))
    op.execute("UPDATE alerts SET alert_type_str = alert_type::text")
    op.alter_column("alerts", "alert_type_str", nullable=False)
    op.drop_column("alerts", "alert_type")
    op.alter_column("alerts", "alert_type_str", new_column_name="alert_type")

    # =========================================================================
    # INVOICES TABLE
    # =========================================================================
    op.add_column("invoices", sa.Column("status_str", sa.String(50), nullable=True))
    op.execute("UPDATE invoices SET status_str = status::text")
    op.alter_column("invoices", "status_str", nullable=False)
    op.drop_column("invoices", "status")
    op.alter_column("invoices", "status_str", new_column_name="status")

    # =========================================================================
    # PLANS TABLE
    # =========================================================================
    op.add_column("plans", sa.Column("tier_str", sa.String(50), nullable=True))
    op.execute("UPDATE plans SET tier_str = tier::text")
    op.alter_column("plans", "tier_str", nullable=False)
    op.drop_column("plans", "tier")
    op.alter_column("plans", "tier_str", new_column_name="tier")

    # =========================================================================
    # SUBSCRIPTIONS TABLE
    # =========================================================================
    op.add_column("subscriptions", sa.Column("billing_cycle_str", sa.String(20), nullable=True))
    op.execute("UPDATE subscriptions SET billing_cycle_str = billing_cycle::text")
    op.alter_column("subscriptions", "billing_cycle_str", nullable=False)
    op.drop_column("subscriptions", "billing_cycle")
    op.alter_column("subscriptions", "billing_cycle_str", new_column_name="billing_cycle")

    op.add_column("subscriptions", sa.Column("status_str", sa.String(50), nullable=True))
    op.execute("UPDATE subscriptions SET status_str = status::text")
    op.alter_column("subscriptions", "status_str", nullable=False)
    op.drop_column("subscriptions", "status")
    op.alter_column("subscriptions", "status_str", new_column_name="status")

    # =========================================================================
    # BACKTESTS TABLE
    # =========================================================================
    op.add_column("backtests", sa.Column("status_str", sa.String(50), nullable=True))
    op.execute("UPDATE backtests SET status_str = status::text")
    op.alter_column("backtests", "status_str", nullable=False)
    op.drop_column("backtests", "status")
    op.alter_column("backtests", "status_str", new_column_name="status")

    # =========================================================================
    # STRATEGY_EXECUTIONS TABLE
    # =========================================================================
    # Recreate old enum types for strategy executions
    op.execute("CREATE TYPE execution_mode_enum AS ENUM ('paper', 'live')")
    op.execute(
        "CREATE TYPE execution_status_enum AS ENUM ('pending', 'running', 'paused', 'stopped', 'error')"
    )

    op.add_column(
        "strategy_executions",
        sa.Column(
            "status_enum_col",
            sa.Enum(
                "pending", "running", "paused", "stopped", "error", name="execution_status_enum"
            ),
            nullable=True,
        ),
    )
    op.execute(
        "UPDATE strategy_executions SET status_enum_col = status::text::execution_status_enum"
    )
    op.alter_column("strategy_executions", "status_enum_col", nullable=False)
    op.drop_column("strategy_executions", "status")
    op.alter_column("strategy_executions", "status_enum_col", new_column_name="status")

    op.add_column(
        "strategy_executions",
        sa.Column(
            "mode_enum_col", sa.Enum("paper", "live", name="execution_mode_enum"), nullable=True
        ),
    )
    op.execute("UPDATE strategy_executions SET mode_enum_col = mode::text::execution_mode_enum")
    op.alter_column("strategy_executions", "mode_enum_col", nullable=False)
    op.drop_column("strategy_executions", "mode")
    op.alter_column("strategy_executions", "mode_enum_col", new_column_name="mode")

    # =========================================================================
    # STRATEGIES TABLE
    # =========================================================================
    # Recreate old enum type for strategies
    op.execute("CREATE TYPE strategy_status_enum AS ENUM ('draft', 'active', 'paused', 'archived')")

    op.add_column(
        "strategies",
        sa.Column(
            "status_enum_col",
            sa.Enum("draft", "active", "paused", "archived", name="strategy_status_enum"),
            nullable=True,
        ),
    )
    op.execute("UPDATE strategies SET status_enum_col = status::text::strategy_status_enum")
    op.alter_column("strategies", "status_enum_col", nullable=False)
    op.drop_column("strategies", "status")
    op.alter_column("strategies", "status_enum_col", new_column_name="status")

    # =========================================================================
    # TRADING_SESSIONS TABLE
    # =========================================================================
    op.add_column("trading_sessions", sa.Column("status_str", sa.String(50), nullable=True))
    op.execute("UPDATE trading_sessions SET status_str = status::text")
    op.alter_column("trading_sessions", "status_str", nullable=False)
    op.drop_column("trading_sessions", "status")
    op.alter_column("trading_sessions", "status_str", new_column_name="status")

    op.add_column("trading_sessions", sa.Column("mode_str", sa.String(20), nullable=True))
    op.execute("UPDATE trading_sessions SET mode_str = mode::text")
    op.alter_column("trading_sessions", "mode_str", nullable=False)
    op.drop_column("trading_sessions", "mode")
    op.alter_column("trading_sessions", "mode_str", new_column_name="mode")

    # =========================================================================
    # POSITIONS TABLE
    # =========================================================================
    op.add_column("positions", sa.Column("side_str", sa.String(10), nullable=True))
    op.execute("UPDATE positions SET side_str = side::text")
    op.alter_column("positions", "side_str", nullable=False)
    op.drop_column("positions", "side")
    op.alter_column("positions", "side_str", new_column_name="side")

    # =========================================================================
    # ORDERS TABLE
    # =========================================================================
    op.add_column("orders", sa.Column("time_in_force_str", sa.String(10), nullable=True))
    op.execute("UPDATE orders SET time_in_force_str = time_in_force::text")
    op.alter_column("orders", "time_in_force_str", nullable=False)
    op.drop_column("orders", "time_in_force")
    op.alter_column("orders", "time_in_force_str", new_column_name="time_in_force")

    op.add_column("orders", sa.Column("status_str", sa.String(50), nullable=True))
    op.execute("UPDATE orders SET status_str = status::text")
    op.alter_column("orders", "status_str", nullable=False)
    op.drop_column("orders", "status")
    op.alter_column("orders", "status_str", new_column_name="status")

    op.add_column("orders", sa.Column("order_type_str", sa.String(20), nullable=True))
    op.execute("UPDATE orders SET order_type_str = order_type::text")
    op.alter_column("orders", "order_type_str", nullable=False)
    op.drop_column("orders", "order_type")
    op.alter_column("orders", "order_type_str", new_column_name="order_type")

    op.add_column("orders", sa.Column("side_str", sa.String(10), nullable=True))
    op.execute("UPDATE orders SET side_str = side::text")
    op.alter_column("orders", "side_str", nullable=False)
    op.drop_column("orders", "side")
    op.alter_column("orders", "side_str", new_column_name="side")

    # =========================================================================
    # DROP ALL NEW ENUM TYPES
    # =========================================================================
    op.execute("DROP TYPE IF EXISTS notification_status")
    op.execute("DROP TYPE IF EXISTS alert_status")
    op.execute("DROP TYPE IF EXISTS alert_condition_type")
    op.execute("DROP TYPE IF EXISTS channel_type")
    op.execute("DROP TYPE IF EXISTS notification_type")
    op.execute("DROP TYPE IF EXISTS invoice_status")
    op.execute("DROP TYPE IF EXISTS billing_interval")
    op.execute("DROP TYPE IF EXISTS plan_tier")
    op.execute("DROP TYPE IF EXISTS subscription_status")
    op.execute("DROP TYPE IF EXISTS backtest_status")
    op.execute("DROP TYPE IF EXISTS strategy_status")
    op.execute("DROP TYPE IF EXISTS execution_status")
    op.execute("DROP TYPE IF EXISTS execution_mode")
    op.execute("DROP TYPE IF EXISTS session_status")
    op.execute("DROP TYPE IF EXISTS position_side")
    op.execute("DROP TYPE IF EXISTS time_in_force")
    op.execute("DROP TYPE IF EXISTS order_status")
    op.execute("DROP TYPE IF EXISTS order_type")
    op.execute("DROP TYPE IF EXISTS order_side")
