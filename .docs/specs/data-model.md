# Data Model Reference

Complete database schema documentation for LlamaTrade.

---

## Overview

LlamaTrade uses PostgreSQL with:
- **SQLAlchemy 2.0** async ORM
- **Row-Level Security (RLS)** for tenant isolation
- **TimescaleDB** extension for market data time series
- **JSONB** for flexible configuration storage

Models are defined in `libs/db/llamatrade_db/models/`.

---

## Multi-Tenancy Pattern

All tenant-scoped tables include:

```python
class TenantMixin:
    tenant_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("tenants.id"),
        nullable=False,
        index=True
    )
```

**Every query must filter by tenant_id.** The middleware injects this automatically.

---

## Auth Models

Source: `libs/db/llamatrade_db/models/auth.py`

### Tenant

Multi-tenant organization/workspace.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | UUID | PK | Unique identifier |
| `name` | VARCHAR(255) | NOT NULL | Display name |
| `slug` | VARCHAR(100) | UNIQUE, NOT NULL | URL-safe identifier |
| `is_active` | BOOLEAN | DEFAULT TRUE | Account status |
| `settings` | JSONB | NULLABLE | Tenant preferences |
| `created_at` | TIMESTAMPTZ | NOT NULL | Creation timestamp |
| `updated_at` | TIMESTAMPTZ | NOT NULL | Last update |

**Indexes:**
- `ix_tenants_slug` (unique)

### User

User account within a tenant.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | UUID | PK | Unique identifier |
| `tenant_id` | UUID | FK → tenants.id, NOT NULL | Parent tenant |
| `email` | VARCHAR(320) | NOT NULL | Email address |
| `password_hash` | VARCHAR(255) | NOT NULL | Bcrypt hash |
| `first_name` | VARCHAR(100) | NULLABLE | First name |
| `last_name` | VARCHAR(100) | NULLABLE | Last name |
| `role` | VARCHAR(50) | DEFAULT 'user' | Role (admin, user) |
| `is_active` | BOOLEAN | DEFAULT TRUE | Account status |
| `is_verified` | BOOLEAN | DEFAULT FALSE | Email verified |
| `last_login` | TIMESTAMPTZ | NULLABLE | Last login time |
| `settings` | JSONB | NULLABLE | User preferences |
| `created_at` | TIMESTAMPTZ | NOT NULL | Creation timestamp |
| `updated_at` | TIMESTAMPTZ | NOT NULL | Last update |

**Indexes:**
- `ix_users_tenant_email` (unique composite)
- `ix_users_tenant_id`

### AlpacaCredentials

Encrypted Alpaca API credentials.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | UUID | PK | Unique identifier |
| `tenant_id` | UUID | FK → tenants.id, NOT NULL | Parent tenant |
| `name` | VARCHAR(100) | NOT NULL | Display name |
| `api_key_encrypted` | TEXT | NOT NULL | AES-encrypted API key |
| `api_secret_encrypted` | TEXT | NOT NULL | AES-encrypted secret |
| `is_paper` | BOOLEAN | DEFAULT TRUE | Paper vs live |
| `is_active` | BOOLEAN | DEFAULT TRUE | Active status |
| `created_at` | TIMESTAMPTZ | NOT NULL | Creation timestamp |
| `updated_at` | TIMESTAMPTZ | NOT NULL | Last update |

**Indexes:**
- `ix_alpaca_credentials_tenant_id`

### APIKey

Programmatic API keys for external access.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | UUID | PK | Unique identifier |
| `tenant_id` | UUID | FK → tenants.id, NOT NULL | Parent tenant |
| `user_id` | UUID | FK → users.id, NOT NULL | Owner user |
| `name` | VARCHAR(100) | NOT NULL | Display name |
| `key_prefix` | VARCHAR(10) | NOT NULL | First 8 chars for ID |
| `key_hash` | VARCHAR(64) | NOT NULL | SHA-256 hash of key |
| `scopes` | JSONB | NULLABLE | Allowed scopes |
| `expires_at` | TIMESTAMPTZ | NULLABLE | Expiration time |
| `last_used_at` | TIMESTAMPTZ | NULLABLE | Last usage time |
| `is_active` | BOOLEAN | DEFAULT TRUE | Active status |
| `created_at` | TIMESTAMPTZ | NOT NULL | Creation timestamp |

**Indexes:**
- `ix_api_keys_key_hash`
- `ix_api_keys_tenant_id`
- `ix_api_keys_user_id`

---

## Strategy Models

Source: `libs/db/llamatrade_db/models/strategy.py`

### Strategy

Trading strategy definition.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | UUID | PK | Unique identifier |
| `tenant_id` | UUID | FK → tenants.id, NOT NULL | Parent tenant |
| `name` | VARCHAR(255) | NOT NULL | Strategy name |
| `description` | TEXT | NULLABLE | Description |
| `strategy_type` | ENUM | NOT NULL | Type (see below) |
| `status` | ENUM | DEFAULT 'draft' | Status (see below) |
| `is_public` | BOOLEAN | DEFAULT FALSE | Publicly visible |
| `current_version` | INTEGER | DEFAULT 1 | Active version |
| `created_by` | UUID | NOT NULL | Creator user ID |
| `created_at` | TIMESTAMPTZ | NOT NULL | Creation timestamp |
| `updated_at` | TIMESTAMPTZ | NOT NULL | Last update |

**Enums:**
- `StrategyType`: `trend_following`, `mean_reversion`, `momentum`, `breakout`, `custom`
- `StrategyStatus`: `draft`, `active`, `paused`, `archived`

**Indexes:**
- `ix_strategies_tenant_name`
- `ix_strategies_tenant_status`
- `ix_strategies_tenant_type`

### StrategyVersion

Immutable version snapshot of strategy configuration.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | UUID | PK | Unique identifier |
| `strategy_id` | UUID | FK → strategies.id, NOT NULL | Parent strategy |
| `version` | INTEGER | NOT NULL | Version number |
| `config` | JSONB | NOT NULL | Visual builder config |
| `sexpr` | TEXT | NOT NULL | Compiled S-expression |
| `change_notes` | TEXT | NULLABLE | Version notes |
| `created_by` | UUID | NOT NULL | Creator user ID |
| `created_at` | TIMESTAMPTZ | NOT NULL | Creation timestamp |

**Indexes:**
- `ix_strategy_versions_strategy_version` (unique composite)

### StrategyDeployment

Live deployment of a strategy.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | UUID | PK | Unique identifier |
| `tenant_id` | UUID | FK → tenants.id, NOT NULL | Parent tenant |
| `strategy_id` | UUID | FK → strategies.id, NOT NULL | Strategy |
| `strategy_version` | INTEGER | NOT NULL | Deployed version |
| `credentials_id` | UUID | NOT NULL | Alpaca credentials |
| `environment` | ENUM | NOT NULL | paper/live |
| `status` | ENUM | DEFAULT 'pending' | Deployment status |
| `config` | JSONB | NOT NULL | Runtime config |
| `symbols` | JSONB | NOT NULL | Trading symbols |
| `started_at` | TIMESTAMPTZ | NULLABLE | Start time |
| `stopped_at` | TIMESTAMPTZ | NULLABLE | Stop time |
| `error_message` | TEXT | NULLABLE | Error details |
| `created_at` | TIMESTAMPTZ | NOT NULL | Creation timestamp |

**Enums:**
- `DeploymentEnvironment`: `paper`, `live`
- `DeploymentStatus`: `pending`, `running`, `paused`, `stopped`, `error`

---

## Trading Models

Source: `libs/db/llamatrade_db/models/trading.py`

### TradingSession

Live or paper trading session.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | UUID | PK | Unique identifier |
| `tenant_id` | UUID | FK → tenants.id, NOT NULL | Parent tenant |
| `strategy_id` | UUID | NOT NULL | Strategy being run |
| `strategy_version` | INTEGER | NOT NULL | Version number |
| `credentials_id` | UUID | NOT NULL | Alpaca credentials |
| `name` | VARCHAR(255) | NOT NULL | Session name |
| `mode` | VARCHAR(20) | NOT NULL | 'paper' or 'live' |
| `status` | VARCHAR(50) | DEFAULT 'stopped' | Session status |
| `config` | JSONB | DEFAULT {} | Runtime configuration |
| `symbols` | JSONB | DEFAULT [] | Trading symbols |
| `started_at` | TIMESTAMPTZ | NULLABLE | Start time |
| `stopped_at` | TIMESTAMPTZ | NULLABLE | Stop time |
| `last_heartbeat` | TIMESTAMPTZ | NULLABLE | Last activity |
| `error_message` | TEXT | NULLABLE | Error details |
| `created_by` | UUID | NOT NULL | Creator user ID |
| `created_at` | TIMESTAMPTZ | NOT NULL | Creation timestamp |

**Indexes:**
- `ix_trading_sessions_tenant_status`
- `ix_trading_sessions_strategy`

### Order

Order placed through trading session.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | UUID | PK | Unique identifier |
| `tenant_id` | UUID | FK → tenants.id, NOT NULL | Parent tenant |
| `session_id` | UUID | FK → trading_sessions.id, NOT NULL | Parent session |
| `alpaca_order_id` | VARCHAR(100) | NULLABLE | Alpaca's order ID |
| `client_order_id` | VARCHAR(100) | NOT NULL | Our order ID |
| `symbol` | VARCHAR(20) | NOT NULL | Trading symbol |
| `side` | VARCHAR(10) | NOT NULL | 'buy' or 'sell' |
| `order_type` | VARCHAR(20) | NOT NULL | Order type |
| `time_in_force` | VARCHAR(10) | NOT NULL | TIF |
| `qty` | NUMERIC(18,8) | NOT NULL | Order quantity |
| `limit_price` | NUMERIC(18,8) | NULLABLE | Limit price |
| `stop_price` | NUMERIC(18,8) | NULLABLE | Stop price |
| `status` | VARCHAR(50) | NOT NULL | Order status |
| `filled_qty` | NUMERIC(18,8) | DEFAULT 0 | Filled quantity |
| `filled_avg_price` | NUMERIC(18,8) | NULLABLE | Fill price |
| `submitted_at` | TIMESTAMPTZ | NULLABLE | Submit time |
| `filled_at` | TIMESTAMPTZ | NULLABLE | Fill time |
| `canceled_at` | TIMESTAMPTZ | NULLABLE | Cancel time |
| `failed_at` | TIMESTAMPTZ | NULLABLE | Failure time |
| `signal_reason` | TEXT | NULLABLE | Why signal was generated |
| `metadata` | JSONB | NULLABLE | Additional data |
| `created_at` | TIMESTAMPTZ | NOT NULL | Creation timestamp |

**Indexes:**
- `ix_orders_tenant_status`
- `ix_orders_session`
- `ix_orders_symbol`
- `ix_orders_alpaca_order_id`

### Position

Current position in a trading session.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | UUID | PK | Unique identifier |
| `tenant_id` | UUID | FK → tenants.id, NOT NULL | Parent tenant |
| `session_id` | UUID | FK → trading_sessions.id, NOT NULL | Parent session |
| `symbol` | VARCHAR(20) | NOT NULL | Trading symbol |
| `side` | VARCHAR(10) | NOT NULL | 'long' or 'short' |
| `qty` | NUMERIC(18,8) | NOT NULL | Position size |
| `avg_entry_price` | NUMERIC(18,8) | NOT NULL | Entry price |
| `current_price` | NUMERIC(18,8) | NULLABLE | Latest price |
| `cost_basis` | NUMERIC(18,8) | NOT NULL | Total cost |
| `market_value` | NUMERIC(18,8) | NULLABLE | Current value |
| `unrealized_pl` | NUMERIC(18,8) | DEFAULT 0 | Unrealized P&L |
| `unrealized_plpc` | NUMERIC(10,6) | DEFAULT 0 | Unrealized P&L % |
| `realized_pl` | NUMERIC(18,8) | DEFAULT 0 | Realized P&L |
| `is_open` | BOOLEAN | DEFAULT TRUE | Position open |
| `opened_at` | TIMESTAMPTZ | NOT NULL | Open time |
| `closed_at` | TIMESTAMPTZ | NULLABLE | Close time |
| `created_at` | TIMESTAMPTZ | NOT NULL | Creation timestamp |

**Indexes:**
- `ix_positions_session_symbol` (unique composite)

---

## Backtest Models

Source: `libs/db/llamatrade_db/models/backtest.py`

### Backtest

Backtest execution record.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | UUID | PK | Unique identifier |
| `tenant_id` | UUID | FK → tenants.id, NOT NULL | Parent tenant |
| `strategy_id` | UUID | NOT NULL | Strategy tested |
| `strategy_version` | INTEGER | DEFAULT 1 | Version tested |
| `name` | VARCHAR(255) | NULLABLE | Backtest name |
| `config` | JSONB | NOT NULL | Backtest config |
| `symbols` | JSONB | NULLABLE | Override symbols |
| `start_date` | DATE | NOT NULL | Start date |
| `end_date` | DATE | NOT NULL | End date |
| `initial_capital` | NUMERIC(18,2) | NOT NULL | Starting capital |
| `status` | VARCHAR(20) | DEFAULT 'pending' | Execution status |
| `error_message` | TEXT | NULLABLE | Error details |
| `started_at` | TIMESTAMPTZ | NULLABLE | Start time |
| `completed_at` | TIMESTAMPTZ | NULLABLE | Completion time |
| `created_by` | UUID | NOT NULL | Creator user ID |
| `created_at` | TIMESTAMPTZ | NOT NULL | Creation timestamp |

**Status values:** `pending`, `running`, `completed`, `failed`, `cancelled`

**Indexes:**
- `ix_backtests_tenant_status`
- `ix_backtests_strategy`

### BacktestResult

Backtest results and metrics.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | UUID | PK | Unique identifier |
| `backtest_id` | UUID | FK → backtests.id, UNIQUE | Parent backtest |
| `total_return` | NUMERIC(10,6) | NULLABLE | Total return |
| `annual_return` | NUMERIC(10,6) | NULLABLE | Annualized return |
| `sharpe_ratio` | NUMERIC(10,6) | NULLABLE | Sharpe ratio |
| `sortino_ratio` | NUMERIC(10,6) | NULLABLE | Sortino ratio |
| `max_drawdown` | NUMERIC(10,6) | NULLABLE | Max drawdown |
| `calmar_ratio` | NUMERIC(10,6) | NULLABLE | Calmar ratio |
| `volatility` | NUMERIC(10,6) | NULLABLE | Volatility |
| `total_trades` | INTEGER | NULLABLE | Trade count |
| `winning_trades` | INTEGER | NULLABLE | Winning trades |
| `losing_trades` | INTEGER | NULLABLE | Losing trades |
| `win_rate` | NUMERIC(10,6) | NULLABLE | Win rate |
| `profit_factor` | NUMERIC(10,6) | NULLABLE | Profit factor |
| `avg_trade_return` | NUMERIC(10,6) | NULLABLE | Avg trade return |
| `final_equity` | NUMERIC(18,2) | NULLABLE | Final equity |
| `equity_curve` | JSONB | NULLABLE | Equity time series |
| `trades` | JSONB | NULLABLE | Trade list |
| `daily_returns` | JSONB | NULLABLE | Daily returns |
| `monthly_returns` | JSONB | NULLABLE | Monthly returns |
| `created_at` | TIMESTAMPTZ | NOT NULL | Creation timestamp |

---

## Market Data Models

Source: `libs/db/llamatrade_db/models/market_data.py`

**Note:** Market data is NOT tenant-scoped. It's shared across all tenants.

### Bar (TimescaleDB Hypertable)

OHLCV candlestick data.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `symbol` | VARCHAR(20) | NOT NULL | Trading symbol |
| `timestamp` | TIMESTAMPTZ | NOT NULL | Bar timestamp |
| `timeframe` | VARCHAR(10) | NOT NULL | 1Min, 5Min, 1Hour, 1Day |
| `open` | NUMERIC(18,8) | NOT NULL | Open price |
| `high` | NUMERIC(18,8) | NOT NULL | High price |
| `low` | NUMERIC(18,8) | NOT NULL | Low price |
| `close` | NUMERIC(18,8) | NOT NULL | Close price |
| `volume` | BIGINT | NOT NULL | Volume |
| `vwap` | NUMERIC(18,8) | NULLABLE | VWAP |
| `trade_count` | INTEGER | NULLABLE | Number of trades |

**Primary Key:** `(symbol, timestamp, timeframe)`

**Hypertable:** Partitioned by `timestamp` (1 week chunks)

**Compression:** Enabled for data > 7 days old

---

## Billing Models

Source: `libs/db/llamatrade_db/models/billing.py`

### Subscription

Stripe subscription record.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | UUID | PK | Unique identifier |
| `tenant_id` | UUID | FK → tenants.id, UNIQUE | Parent tenant |
| `stripe_customer_id` | VARCHAR(100) | NOT NULL | Stripe customer |
| `stripe_subscription_id` | VARCHAR(100) | NULLABLE | Stripe subscription |
| `plan_id` | VARCHAR(50) | NOT NULL | Plan identifier |
| `status` | VARCHAR(50) | NOT NULL | Subscription status |
| `current_period_start` | TIMESTAMPTZ | NULLABLE | Period start |
| `current_period_end` | TIMESTAMPTZ | NULLABLE | Period end |
| `canceled_at` | TIMESTAMPTZ | NULLABLE | Cancellation time |
| `created_at` | TIMESTAMPTZ | NOT NULL | Creation timestamp |
| `updated_at` | TIMESTAMPTZ | NOT NULL | Last update |

---

## Audit Models

Source: `libs/db/llamatrade_db/models/audit.py`

### AuditLog

Audit trail for all significant events.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | UUID | PK | Unique identifier |
| `tenant_id` | UUID | NOT NULL | Tenant context |
| `user_id` | UUID | NULLABLE | Acting user |
| `action` | VARCHAR(100) | NOT NULL | Action type |
| `resource_type` | VARCHAR(100) | NOT NULL | Resource type |
| `resource_id` | VARCHAR(100) | NULLABLE | Resource ID |
| `details` | JSONB | NULLABLE | Additional details |
| `ip_address` | VARCHAR(45) | NULLABLE | Client IP |
| `user_agent` | TEXT | NULLABLE | Client user agent |
| `created_at` | TIMESTAMPTZ | NOT NULL | Event timestamp |

**Indexes:**
- `ix_audit_log_tenant_created` (tenant_id, created_at DESC)
- `ix_audit_log_resource` (resource_type, resource_id)

---

## Relationships Diagram

```
tenants
  ├── users (1:N)
  ├── api_keys (1:N)
  ├── alpaca_credentials (1:N)
  ├── strategies (1:N)
  │     └── strategy_versions (1:N)
  │     └── strategy_deployments (1:N)
  ├── trading_sessions (1:N)
  │     └── orders (1:N)
  │     └── positions (1:N)
  ├── backtests (1:N)
  │     └── backtest_results (1:1)
  ├── subscriptions (1:1)
  └── audit_logs (1:N)

bars (shared, not tenant-scoped)
```

---

## Migrations

Migrations are managed with Alembic per-service.

```bash
# Create migration
cd services/auth
alembic revision --autogenerate -m "Description"

# Apply
alembic upgrade head

# Rollback
alembic downgrade -1
```

**Note:** Shared models in `libs/db/` are migrated from the auth service (primary database owner).
