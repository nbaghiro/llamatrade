# Trading Service Architecture

The trading service is the execution engine that connects user-defined strategies to real markets via Alpaca Markets. It handles everything from receiving real-time market data to executing orders with comprehensive risk controls.

---

## Overview

The trading service is responsible for:

- **Live Strategy Execution**: Running compiled strategies against real-time market data
- **Order Management**: Submitting, tracking, and syncing orders with Alpaca
- **Risk Controls**: Enforcing position limits, daily loss limits, and order validation
- **Position Tracking**: Maintaining local position records with P&L calculations
- **Session Management**: Starting, stopping, pausing trading sessions
- **Audit Logging**: Recording all trading events for compliance

---

## Architecture Overview

### System Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           TRADING SERVICE                                   │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                      FastAPI Application                            │    │
│  │   /orders    /sessions    /positions    /health                     │    │
│  └─────────────────────────────┬───────────────────────────────────────┘    │
│                                │                                            │
│  ┌─────────────────────────────┴───────────────────────────────────────┐    │
│  │                      Core Services Layer                            │    │
│  │                                                                     │    │
│  │  OrderExecutor ─────► Submit/track orders, sync with Alpaca         │    │
│  │  LiveSessionService ─► Session + Runner lifecycle                   │    │
│  │  PositionService ───► Local position tracking, P&L                  │    │
│  │  RiskManager ───────► 5-layer validation pipeline                   │    │
│  │  AuditService ──────► Event logging for compliance                  │    │
│  └─────────────────────────────┬───────────────────────────────────────┘    │
│                                │                                            │
│  ┌─────────────────────────────┴───────────────────────────────────────┐    │
│  │                      Strategy Runner (per session)                  │    │
│  │                                                                     │    │
│  │  AlpacaBarStream ──► WebSocket real-time bars                       │    │
│  │  StrategyAdapter ──► Compiled strategy evaluation                   │    │
│  │  RunnerManager ────► Manages multiple concurrent sessions           │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                             │
└─────────────────────────────────┬───────────────────────────────────────────┘
                                  │
        ┌─────────────────────────┼─────────────────────────┐
        ▼                         ▼                         ▼
   ┌─────────────┐        ┌─────────────┐           ┌─────────────┐
   │  Alpaca     │        │ Market Data │           │  Strategy   │
   │  Trading    │        │  Service    │           │  Service    │
   │  API        │        │  :8840      │           │  :8820      │
   └─────────────┘        └─────────────┘           └─────────────┘
```

### Session Lifecycle

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         SESSION STATE MACHINE                               │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│                              ┌─────────┐                                    │
│                              │ CREATED │                                    │
│                              └────┬────┘                                    │
│                                   │ start_session()                         │
│                                   ▼                                         │
│                 ┌────────────►┌────────┐◄────────────┐                      │
│  resume()       │             │ ACTIVE │             │  error               │
│                 │             └────┬───┘             │                      │
│            ┌────┴───┐             │            ┌─────▼────┐                 │
│            │ PAUSED │◄────────────┤            │  ERROR   │                 │
│            └────────┘ pause()     │            └──────────┘                 │
│                                   │ stop_session()                          │
│                                   ▼                                         │
│                              ┌─────────┐                                    │
│                              │ STOPPED │                                    │
│                              └─────────┘                                    │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Directory Structure

```
services/trading/
├── src/
│   ├── main.py                    # FastAPI app, routers, health check
│   ├── models.py                  # Pydantic schemas
│   ├── alpaca_client.py           # Alpaca REST API client
│   ├── routers/
│   │   ├── orders.py              # Order CRUD endpoints
│   │   ├── sessions.py            # Session lifecycle endpoints
│   │   └── positions.py           # Position tracking endpoints
│   ├── services/
│   │   ├── session_service.py     # Session CRUD, P&L calculation
│   │   ├── live_session_service.py # Session + Runner lifecycle
│   │   ├── position_service.py    # Local position tracking
│   │   ├── audit_service.py       # Event logging
│   │   └── alert_service.py       # Webhook notifications
│   ├── runner/
│   │   ├── runner.py              # StrategyRunner, RunnerManager
│   │   └── bar_stream.py          # AlpacaBarStream (WebSocket)
│   ├── executor/
│   │   └── order_executor.py      # Order submission, Alpaca sync
│   ├── risk/
│   │   └── risk_manager.py        # Risk checks, limits
│   ├── clients/
│   │   └── market_data.py         # HTTP client for market-data service
│   └── compiler_adapter.py        # Bridges CompiledStrategy ↔ Runner
└── tests/
```

---

## Core Components

| Component               | File                               | Responsibility                                          |
| ----------------------- | ---------------------------------- | ------------------------------------------------------- |
| **OrderExecutor**       | `executor/order_executor.py`       | Submit orders, sync with Alpaca, manage order lifecycle |
| **RiskManager**         | `risk/risk_manager.py`             | Validate orders, enforce limits, track daily P&L        |
| **SessionService**      | `services/session_service.py`      | CRUD for trading sessions, P&L aggregation              |
| **LiveSessionService**  | `services/live_session_service.py` | Session + Runner lifecycle integration                  |
| **PositionService**     | `services/position_service.py`     | Local position tracking, P&L calculation                |
| **StrategyRunner**      | `runner/runner.py`                 | Real-time strategy execution loop                       |
| **RunnerManager**       | `runner/runner.py`                 | Manage multiple concurrent runners                      |
| **AlpacaBarStream**     | `runner/bar_stream.py`             | WebSocket connection for real-time bars                 |
| **StrategyAdapter**     | `compiler_adapter.py`              | Adapt CompiledStrategy to runner interface              |
| **AlpacaTradingClient** | `alpaca_client.py`                 | REST client for Alpaca Trading API                      |
| **MarketDataClient**    | `clients/market_data.py`           | HTTP client for market-data service                     |
| **AuditService**        | `services/audit_service.py`        | Log all trading events                                  |

---

## Session Lifecycle

### Session Start Flow

1. **Validate request**: Strategy exists, credentials valid
2. **Create TradingSession record** in database (status=ACTIVE)
3. **Load strategy S-expression** from StrategyVersion
4. **Create StrategyAdapter**: Parse + compile strategy
5. **Create AlpacaBarStream** with API credentials
6. **Configure RunnerConfig**: Symbols, timeframe, warmup_bars
7. **Start StrategyRunner** via RunnerManager
8. **Return SessionResponse**

The StrategyRunner then:
- Syncs equity from Alpaca account
- Connects to bar stream WebSocket
- Subscribes to configured symbols
- Enters main loop processing bars

### Session Stop Flow

1. **Stop StrategyRunner** via RunnerManager (set `_running = False`, disconnect stream, cancel tasks)
2. **Update TradingSession** (status=STOPPED, stopped_at=now)
3. **Return SessionResponse** with final P&L

---

## Strategy Runner

### Runner Configuration

- `tenant_id`, `deployment_id` (session_id), `strategy_id`
- `symbols`: List of symbols to trade (e.g., ["AAPL", "GOOGL"])
- `timeframe`: Bar interval (e.g., "1Min")
- `warmup_bars`: Bars needed before signals (e.g., 50)

### Runner State

- `_running`, `_paused`: Control flags
- `_equity`: Current account equity
- `_positions`: dict[symbol, Position]
- `_bar_history`: dict[symbol, list[BarData]]

### Main Execution Loop

1. **Sync equity** from Alpaca account
2. **Connect** to bar stream WebSocket
3. **Subscribe** to symbols
4. **Start equity sync loop** (every 60 seconds)
5. **Process bars** in main loop:
   - If paused, skip
   - Call `_process_bar(bar)` → returns Signal or None
   - If signal, call `_process_signal(signal)`

### Bar Processing

1. Add bar to `_bar_history[symbol]`
2. Trim history to max size (warmup_bars + 100)
3. Check if warmup complete (len >= warmup_bars)
4. If warming up, return None
5. Call `strategy_fn(symbol, bars, position, equity)` → Signal or None

### Signal Processing

1. Create OrderCreate from signal (symbol, side, qty)
2. Call `risk_manager.check_order()`
3. If failed: Log rejection, update metrics
4. If passed: Call `order_executor.submit_order()`
5. Update internal position tracking
6. Update metrics (signals_generated, orders_submitted)

### Runner Manager

The RunnerManager maintains a registry of active runners:
- `active_runners`: dict[UUID, StrategyRunner]
- `_tasks`: dict[UUID, asyncio.Task]

Methods:
- `start_runner(config, strategy_fn, bar_stream, ...)` → UUID
- `stop_runner(deployment_id)`
- `stop_all()`
- `get_runner(deployment_id)` → StrategyRunner or None

---

## Order Execution Flow

### Order Lifecycle

States: `PENDING` → `SUBMITTED` → `ACCEPTED` → `FILLED`

Alternative paths:
- `PENDING` → `REJECTED`
- `SUBMITTED` → `CANCELLED`
- `ACCEPTED` → `PARTIAL` → `FILLED`

### Order Submission Steps

1. **Risk Validation**: `risk_manager.check_order()` - checks max order value, allowed symbols, max position size, daily loss limit, order rate limit
2. **Create Database Record**: Order with status=PENDING
3. **Submit to Alpaca**: POST to Alpaca Trading API
4. **Update Database**: Store alpaca_order_id, update status
5. **Return Response**: OrderResponse with status

---

## Risk Management

### Risk Check Pipeline

`RiskManager.check_order()` validates against 5 checks:

| Check | Rule | Default |
|-------|------|---------|
| **Max Order Value** | qty × price ≤ limit | $10,000 |
| **Allowed Symbols** | symbol in whitelist | All allowed |
| **Max Position Size** | (current + new) × price ≤ limit | $50,000 |
| **Daily Loss Limit** | daily_pnl > -limit | $5,000 |
| **Order Rate Limit** | orders in last 60s < limit | 10/minute |

Returns: `RiskCheckResult(passed: bool, violations: list[str])`

### Risk Limits Configuration

Can be configured at session or tenant level:

```python
class RiskLimits:
    max_position_size: float | None   # Max $ per position (default: $50,000)
    max_daily_loss: float | None      # Max daily loss before halt (default: $5,000)
    max_order_value: float | None     # Max $ per order (default: $10,000)
    allowed_symbols: list[str] | None # Symbol whitelist (default: all)
```

### Daily P&L Tracking

The RiskManager tracks:
- `realized_pnl`: Sum of closed position P&L
- `unrealized_pnl`: Sum of open position P&L
- `equity_high` / `equity_low`: Tracked for drawdown calculation
- `trades_count`, `win_count`, `loss_count`

Drawdown = (equity_high - current_equity) / equity_high

### Price Fetching Fallback

Multi-layer fallback for price estimation:
1. **Market Data Service**: HTTP call to market-data service
2. **Local Cache**: Price from recent successful fetch
3. **Database Position**: Last known price from position tracking
4. **Default**: Return 100.0 (last resort)

---

## Real-Time Data Streaming

### AlpacaBarStream

WebSocket connection to Alpaca's real-time data feed.

**URLs:**
- Paper: `wss://stream.data.sandbox.alpaca.markets/v2/iex`
- Live: `wss://stream.data.alpaca.markets/v2/iex`

**Connection Flow:**
1. Connect WebSocket
2. Receive welcome message
3. Send auth credentials
4. Receive auth confirmation
5. Subscribe to symbols
6. Stream bars

**Bar Data Format:**
```json
{
  "T": "b",           // Type: bar
  "S": "AAPL",        // Symbol
  "t": "2024-...",    // Timestamp
  "o": 185.00,        // Open
  "h": 186.50,        // High
  "l": 184.75,        // Low
  "c": 185.50,        // Close
  "v": 1234567,       // Volume
  "vw": 185.25,       // VWAP
  "n": 5432           // Trade count
}
```

**Auto-Reconnection:**
- Max attempts: 10
- Backoff: exponential (5s, 10s, 20s, 40s, ...)
- On reconnect: Re-authenticate and re-subscribe

---

## Position & P&L Tracking

### Position Service Operations

**open_position(tenant_id, session_id, symbol, side, qty, entry_price)**
Creates position with cost_basis, market_value, unrealized_pl.

**close_position(tenant_id, session_id, symbol, exit_price)**
Calculates realized P&L:
- Long: `(exit_price - entry_price) × qty`
- Short: `(entry_price - exit_price) × qty`

**update_prices(tenant_id, session_id, prices)**
For each open position: Update current_price, market_value, unrealized_pl.

### P&L Aggregation

```
get_session_pnl(tenant_id, session_id) → (realized, unrealized)

Realized P&L = SUM(realized_pl) from all positions
Unrealized P&L = SUM(unrealized_pl) from open positions only
Total P&L = Realized + Unrealized
```

---

## External Service Integrations

### Alpaca Trading Client

**Base URLs:**
- Paper: `https://paper-api.alpaca.markets/v2`
- Live: `https://api.alpaca.markets/v2`

**Authentication Headers:**
- `APCA-API-KEY-ID: <api_key>`
- `APCA-API-SECRET-KEY: <api_secret>`

**Methods:**
- `get_account()` → cash, equity, buying_power
- `submit_order(symbol, qty, side, type, time_in_force)`
- `get_order(order_id)`, `list_orders(status, limit)`, `cancel_order(order_id)`
- `get_positions()`, `get_position(symbol)`, `close_position(symbol)`, `close_all_positions()`

### Market Data Client

**Base URL:** `http://market-data:8840` (configurable)

**Methods:**
- `get_latest_price(symbol)` → float | None (GET /bars/{symbol}/latest)
- `get_prices(symbols)` → dict[str, float] (batch fetch)
- `get_bars(symbol, timeframe, start, end)` → list[dict]

### Strategy Adapter

Bridges CompiledStrategy with StrategyRunner interface.

**Initialization:** `StrategyAdapter(strategy_sexpr: str)`
1. Parse S-expression → AST
2. Compile AST → Executable

**Evaluation:** `__call__(symbol, bars, position, equity)` → Signal | None
1. Convert BarData → Compiler's Bar format
2. Sync position state with compiled strategy
3. On first call, warm up with historical bars
4. Evaluate strategy with latest bar
5. Convert compiler Signal → Runner Signal

---

## Data Models

### Order Models

**OrderCreate:**
- `symbol`, `side` (BUY/SELL), `qty`
- `order_type` (MARKET, LIMIT, STOP, STOP_LIMIT, TRAILING_STOP)
- `limit_price`, `stop_price`, `trail_percent` (optional)
- `time_in_force` (DAY, GTC, IOC, FOK)
- `extended_hours`

**OrderResponse:**
- `id`, `alpaca_order_id`, `symbol`, `side`, `qty`, `order_type`
- `status` (PENDING, SUBMITTED, ACCEPTED, PARTIAL, FILLED, CANCELLED, REJECTED)
- `filled_qty`, `filled_avg_price`, `submitted_at`, `filled_at`

### Session Models

**SessionCreate:**
- `strategy_id`, `credentials_id`, `name`
- `mode` (PAPER/LIVE)
- `strategy_version`, `symbols`, `config` (optional)

**SessionResponse:**
- `id`, `tenant_id`, `strategy_id`, `mode`
- `status` (ACTIVE, PAUSED, STOPPED, ERROR)
- `started_at`, `stopped_at`, `pnl`, `trades_count`

### Position Models

**PositionResponse:**
- `symbol`, `qty`, `side` (long/short)
- `cost_basis`, `market_value`
- `unrealized_pnl`, `unrealized_pnl_percent`
- `current_price`

### Risk Models

**RiskLimits:**
- `max_position_size`, `max_daily_loss`, `max_order_value`, `allowed_symbols`

**RiskCheckResult:**
- `passed`: bool
- `violations`: list[str] (e.g., "Order value $15,000 exceeds limit $10,000")

---

## API Endpoints

### Orders Router (`/orders`)

| Method   | Endpoint                  | Description                             |
| -------- | ------------------------- | --------------------------------------- |
| `POST`   | `/orders`                 | Submit a new order                      |
| `GET`    | `/orders`                 | List orders (filter by session, status) |
| `GET`    | `/orders/{order_id}`      | Get order details                       |
| `DELETE` | `/orders/{order_id}`      | Cancel an order                         |
| `POST`   | `/orders/{order_id}/sync` | Sync order status from Alpaca           |
| `POST`   | `/orders/sync`            | Sync all pending orders                 |

### Sessions Router (`/sessions`)

| Method | Endpoint                        | Description                 |
| ------ | ------------------------------- | --------------------------- |
| `POST` | `/sessions`                     | Start a new trading session |
| `GET`  | `/sessions`                     | List sessions               |
| `GET`  | `/sessions/{session_id}`        | Get session details         |
| `POST` | `/sessions/{session_id}/stop`   | Stop a session              |
| `POST` | `/sessions/{session_id}/pause`  | Pause a session             |
| `POST` | `/sessions/{session_id}/resume` | Resume a paused session     |

### Positions Router (`/positions`)

| Method   | Endpoint              | Description                        |
| -------- | --------------------- | ---------------------------------- |
| `GET`    | `/positions`          | List positions (session or Alpaca) |
| `GET`    | `/positions/{symbol}` | Get position for symbol            |
| `DELETE` | `/positions/{symbol}` | Close position                     |
| `POST`   | `/positions/sync`     | Sync prices from market data       |

---

## Complete Data Flow Example

**Scenario: Strategy Generates Buy Signal**

1. **Bar Arrives**: AlpacaBarStream receives `{"T": "b", "S": "AAPL", "c": 185.50, ...}`

2. **Runner Processes Bar**: Adds bar to history, checks warmup, calls strategy_fn

3. **Strategy Evaluates**: StrategyAdapter converts bars, evaluates compiled strategy (e.g., SMA(20) crossed above SMA(50)), returns Signal(type="buy", symbol="AAPL", quantity=10)

4. **Risk Validation**: RiskManager checks all 5 rules → RiskCheckResult(passed=True)

5. **Order Submission**: OrderExecutor creates DB record, POSTs to Alpaca, updates with alpaca_order_id

6. **Position Tracking**: StrategyRunner updates internal positions, PositionService creates DB record

7. **Audit & Alerts**: AuditService logs signal/order events, AlertService sends webhook on fill

8. **Metrics Update**: Runner and RiskManager metrics updated (signals_generated, orders_submitted, etc.)

---

## Summary

The trading service provides a complete, production-grade execution engine with:

1. **Real-time Execution**: WebSocket streaming, async processing loop
2. **Risk Controls**: 5-layer validation pipeline
3. **Session Management**: Full lifecycle with runner integration
4. **Position Tracking**: Local database tracking with P&L calculations
5. **Audit Trail**: Comprehensive logging for compliance
6. **Alert System**: Webhook notifications for critical events
7. **Broker Integration**: Direct connection to Alpaca
8. **Multi-tenancy**: Complete tenant isolation

Architecture separates concerns: Routers (HTTP) → Services (business logic) → Runner (real-time) → Executor (orders) → Risk Manager (limits).
