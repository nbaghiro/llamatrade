# Trading Service Architecture

The trading service is the execution engine that connects user-defined strategies to real markets via Alpaca Markets. It handles order execution, position tracking, risk management, and real-time streaming of order and position updates. It is the **execution arm** of the portfolio ledger: it emits terminal fills and reservation events and defers all accounting to the [Portfolio Ledger](../portfolio-ledger.md).

All Alpaca access (REST + WebSocket) goes through the shared `llamatrade_alpaca` library — the trading service never talks to Alpaca directly.

---

## Overview

The trading service is responsible for:

- **Order Execution**: Submitting, tracking, and syncing orders with Alpaca
- **Position Management**: Tracking positions with real-time P&L calculations
- **Risk Controls**: Enforcing position limits, daily loss limits, and order validation
- **Real-Time Streaming**: Streaming order and position updates to clients
- **Session Management**: Linking orders and positions to trading sessions
- **Alpaca Integration**: Paper and live trading via the shared `llamatrade_alpaca` library

---

## Architecture Overview

### System Architecture

```
╔════════════════════════════════════════════════════════════════════════════════════════╗
║                                 TRADING SERVICE  ·  :8850                              ║
╚════════════════════════════════════════════════════════════════════════════════════════╝
                                             │
╭────────────────────────────────────────────────────────────────────────────────────────╮
│                                 FastAPI + Connect ASGI                                 │
├────────────────────────────────────────────────────────────────────────────────────────┤
│ /health · /metrics       TradingServiceASGIApplication                                 │
╰────────────────────────────────────────────────────────────────────────────────────────╯
                                             │
╭────────────────────────────────────────────────────────────────────────────────────────╮
│                                     gRPC Servicer                                      │
├────────────────────────────────────────────────────────────────────────────────────────┤
│ SubmitOrder ───────────► submit order after 6-layer risk checks                        │
│ CancelOrder ───────────► cancel a pending / submitted order                            │
│ GetOrder ──────────────► get order by id                                               │
│ ListOrders ────────────► list orders with status filter                                │
│ GetPosition ───────────► get position by symbol                                        │
│ ListPositions ─────────► list all positions in a session                               │
│ ClosePosition ─────────► close position (submit offsetting order)                      │
│ StreamOrderUpdates ────► real-time order status changes                                │
│ StreamPositionUpdates ─► real-time position changes                                    │
╰────────────────────────────────────────────────────────────────────────────────────────╯
                                             │
╭────────────────────────────────────────────────────────────────────────────────────────╮
│                                     Service Layer                                      │
├────────────────────────────────────────────────────────────────────────────────────────┤
│ LiveSessionService ────► runs the 4-loop strategy runner per session                   │
│ OrderExecutor ─────────► deterministic client_order_id · exactly-once                  │
│ PositionService ───────► local position cache (fills = source of truth)                │
│ RiskManager ───────────► 6-layer validation + circuit breaker                          │
│ StrategySession ───────► strategy DSL → weights → target weights                       │
╰────────────────────────────────────────────────────────────────────────────────────────╯
                                             │
╭────────────────────────────────────────────────────────────────────────────────────────╮
│                     Runner — 4 concurrent loops (per live session)                     │
├────────────────────────────────────────────────────────────────────────────────────────┤
│ bar → signal ──────────► tick clock + rebalance gate (≤ 1 / day)                       │
│ fills → positions ─────► trade_updates stream · broker = truth                         │
│ equity sync (~60s) ────► sleeve-aware account valuation                                │
│ reconcile (~300s) ─────► diff local vs broker · correct drift                          │
╰────────────────────────────────────────────────────────────────────────────────────────╯
                                             │
╭────────────────────────────────────────────────────────────────────────────────────────╮
│                                     Database Layer                                     │
├────────────────────────────────────────────────────────────────────────────────────────┤
│ TradingSession ────────► live / paper session records                                  │
│ Order ─────────────────► durable order intent (client_order_id key)                    │
│ Position ──────────────► position cache per session                                    │
│ RiskConfig · DailyPnL ─► risk limits + daily P&L for the breaker                       │
╰────────────────────────────────────────────────────────────────────────────────────────╯
                                             │
                      ┌──────────────────────┴──┬────────────────────────┐
                      ▼                         ▼                        ▼
              ╭───────────────╮          ╭─────────────╮          ╭────────────╮
              │ Alpaca        │          │ market-data │          │ consumers  │
              │ Trading       │          │ :8840       │          │ frontend · │
              │ ═ REST + WS ═ │          │ prices      │          │ portfolio  │
              ╰───────────────╯          ╰─────────────╯          ╰────────────╯

                      terminal fills ═════════════════════════►
                      ╔════════════════════════════════════════════════╗
                      ║   ledger:fills  (global; key lt:ledger:fills)  ║
                      ╠════════════════════════════════════════════════╣
                      ║ portfolio LEDGER  ·  :8860                     ║
                      ║ the book of record (append-only, double-entry) ║
                      ╚════════════════════════════════════════════════╝
```

> **Execution runtime.** The runner drives the shared `StrategySession` (evaluation + sizing) through its production `_evaluate_session` loop, priming indicators from historical bars at session start so it can trade from the first live bar; the shared `StrategyRuntime.stream()` loop is opt-in. Full model and the backtest↔live parity differences: [execution-runtime.md](../execution-runtime.md).

### Order Execution Flow

```
╔════════════════════════════════════════════════════════════════════════════════════════════╗
║           ORDER EXECUTION FLOW  ·  rebalance → risk → executor → Alpaca → ledger           ║
╚════════════════════════════════════════════════════════════════════════════════════════════╝

                 ╭─────────────────────────────────────────────────────────╮
                 │     rebalance signal  (runner: bar → target weights)    │
                 ├─────────────────────────────────────────────────────────┤
                 │ a single rebalance can emit MANY orders at once —       │
                 │ one per symbol whose holding must change (sells + buys) │
                 ╰─────────────────────────────────────────────────────────╯
                                              │ per order
                                              ▼
                 ╭──────────────────────────────────────────────────────────╮
                 │      RiskManager.check_order()  —  6-layer pipeline      │
                 ├──────────────────────────────────────────────────────────┤
                 │ max order value ($5,000)   ·   allowed-symbols whitelist │
                 │ max position size ($10,000) ·  daily-loss limit ($1,000) │
                 │ order rate limit (10 / min) +  circuit breaker (halt)    │
                 ╰──────────────────────────────────────────────────────────╯
                                               │
                             ┌─────────────────┴────────────────────────────┐
                        risk PASSED                                    risk FAILED
                             ▼                                              ▼
   ╭──────────────────────────────────────────────────╮        ┌─────────────────────────┐
   │              record durable intent               │        │          reject         │
   ├──────────────────────────────────────────────────┤        ├─────────────────────────┤
   │ create Order in DB (status = pending)            │        │ return INVALID_ARGUMENT │
   │ deterministic client_order_id = lt-<sha256[:16]> │        │ with violation details  │
   │ already-recorded id short-circuits (idempotent)  │        └─────────────────────────┘
   ╰──────────────────────────────────────────────────╯
                             │ submit
                             ▼
                   ╭──────────────────────────────────────────────────────╮
                   │   OrderExecutor → Alpaca  (within the open window)   │
                   ├──────────────────────────────────────────────────────┤
                   │ POST /v2/orders  ═►  Alpaca Trading API              │
                   │ (market · limit · stop · stop-limit · bracket / OCO) │
                   ╰──────────────────────────────────────────────────────╯
                                               │
                             ┌─────────────────┴────────────────┐
                         Alpaca OK                        Alpaca error
                             ▼                                  ▼
               ┌──────────────────────────┐        ┌─────────────────────────┐
               │         accepted         │        │          failed         │
               ├──────────────────────────┤        ├─────────────────────────┤
               │ update Order → submitted │        │ update Order → rejected │
               │ store alpaca_order_id    │        │ map + return error      │
               └──────────────────────────┘        └─────────────────────────┘
                             │
                             ╰─► async fills via trade_updates  ·  broker = source of truth

                fills ═══════════════════════════════════════════►
            ╔═══════════════════════════════════════════════════════════════════╗
            ║                    fills in  →  book of record                    ║
            ╠═══════════════════════════════════════════════════════════════════╣
            ║ fills update local positions; TERMINAL fills publish one proto    ║
            ║ LedgerFill to the global ledger:fills stream (lt:ledger:fills) →  ║
            ║ the portfolio LEDGER (per-sleeve P&L). See portfolio-ledger.md.   ║
            ╚═══════════════════════════════════════════════════════════════════╝
```

### Ledger Emission

Terminal fills publish one proto `LedgerFill` to the global `ledger:fills` stream
(`ledger_events.py`); each buy also publishes a `LedgerReservation` on submit so
sleeve free cash reflects in-flight orders (released on cancel/reject/expiry,
consumed by the fill). The reserved notional
(`executor/order_executor.py::_reservation_amount`) is exact for a **limit** buy
(`qty × limit_price`) but adds a buffer for **market** and **stop** buys
(`qty × reference_price × (1 + _MARKET_BUY_RESERVE_BUFFER)`, default 2%, env
`TRADING_MARKET_BUY_RESERVE_BUFFER`) because the fill can gap above the reference
price.

Emission is idempotent on `client_order_id` from two paths — the live trade stream
and the REST-sync recovery path — so a fill booked twice is a no-op. Beyond the
runner's startup re-publish of terminal orders, a periodic drain
(`_ledger_republish_loop`, default 120s over a 15-minute window, sleeve-attributed
sessions only) proactively re-emits recently-terminal orders' ledger events,
closing the "crash before publish" window. See the
[ledger integration contract](../portfolio-ledger.md#integration-contract-trading--portfolio--strategy).

---

## Directory Structure

```
services/trading/
├── src/
│   ├── main.py                    # FastAPI app, lifespan, health check, rehydration loop
│   ├── models.py                  # Pydantic schemas + enum conversion helpers
│   ├── credentials.py             # Per-tenant/session Alpaca credential resolution
│   ├── recovery.py                # Boot + periodic runner rehydration (advisory locks)
│   ├── ledger_events.py           # LedgerFill / LedgerReservation message builders
│   ├── providers.py              # DI factory for executor/services/publisher singletons
│   ├── circuit_breaker.py         # Broker-failure circuit breaker
│   ├── grpc/
│   │   └── servicer.py            # gRPC/Connect service implementation (resolve_identity)
│   ├── executor/
│   │   ├── base.py               # Shared Alpaca submit/sync mixin (via llamatrade_alpaca)
│   │   └── order_executor.py      # Order submission, deterministic ids, ledger emission
│   ├── risk/
│   │   └── risk_manager.py        # 6-layer risk checks + sleeve-aware ledger gate
│   ├── runner/
│   │   ├── runner.py             # Per-session live strategy runner (concurrent loops)
│   │   └── runtime_adapters.py    # Shared llamatrade_runtime adapter (opt-in loop)
│   ├── services/
│   │   ├── live_session_service.py # Start/stop/rehydrate runners
│   │   ├── position_service.py    # Local position cache, P&L
│   │   ├── session_service.py     # TradingSession CRUD
│   │   ├── audit_service.py       # Money-path audit log
│   │   └── alert_service.py       # Reconciliation / halt alerts
│   ├── streaming/
│   │   ├── publisher.py          # Redis Streams publisher (orders, positions, ledger)
│   │   └── subscriber.py          # UI stream tail-reader
│   └── clients/
│       ├── market_data.py         # HTTP client for market-data service
│       └── portfolio_client.py    # LedgerClient wrapper (sleeve state / free cash)
└── tests/
    └── test_*.py                  # Test suite
```

---

## Core Components

| Component               | File                           | Responsibility                                          |
| ----------------------- | ------------------------------ | ------------------------------------------------------- |
| **TradingServicer**     | `grpc/servicer.py`             | gRPC endpoint implementations; `resolve_identity` guard |
| **LiveSessionService**  | `services/live_session_service.py` | Start/stop/rehydrate per-session strategy runners   |
| **OrderExecutor**       | `executor/order_executor.py`   | Submit orders, sync with Alpaca, deterministic ids, ledger emission |
| **PositionService**     | `services/position_service.py` | Local position tracking, P&L calculation                |
| **RiskManager**         | `risk/risk_manager.py`         | 6-layer validation + sleeve-aware ledger gate + daily P&L |
| **`llamatrade_alpaca`** | `libs/alpaca`                  | Shared Alpaca REST + WebSocket clients (the only Alpaca entry point) |
| **MarketDataClient**    | `clients/market_data.py`       | HTTP client for market-data service                     |

---

## RPC Endpoints

15 RPCs total, grouped below.

### Session Management

| RPC             | Request                | Response                | Description                        |
| --------------- | ---------------------- | ----------------------- | ---------------------------------- |
| `StartSession`  | `StartSessionRequest`  | `StartSessionResponse`  | Start a live/paper strategy runner |
| `StopSession`   | `StopSessionRequest`   | `StopSessionResponse`   | Stop a running session             |
| `PauseSession`  | `PauseSessionRequest`  | `PauseSessionResponse`  | Pause a running session            |
| `ResumeSession` | `ResumeSessionRequest` | `ResumeSessionResponse` | Resume a paused session            |
| `GetSession`    | `GetSessionRequest`    | `GetSessionResponse`    | Get a session by ID                |
| `ListSessions`  | `ListSessionsRequest`  | `ListSessionsResponse`  | List sessions for the tenant       |

### Order Management

| RPC           | Request              | Response              | Description                        |
| ------------- | -------------------- | --------------------- | ---------------------------------- |
| `SubmitOrder` | `SubmitOrderRequest` | `SubmitOrderResponse` | Submit order after risk validation |
| `CancelOrder` | `CancelOrderRequest` | `CancelOrderResponse` | Cancel pending/submitted order     |
| `GetOrder`    | `GetOrderRequest`    | `GetOrderResponse`    | Get order by ID                    |
| `ListOrders`  | `ListOrdersRequest`  | `ListOrdersResponse`  | List orders with status filter     |

### Position Management

| RPC             | Request                | Response                | Description                   |
| --------------- | ---------------------- | ----------------------- | ----------------------------- |
| `GetPosition`   | `GetPositionRequest`   | `GetPositionResponse`   | Get position by symbol        |
| `ListPositions` | `ListPositionsRequest` | `ListPositionsResponse` | List all positions in session |
| `ClosePosition` | `ClosePositionRequest` | `ClosePositionResponse` | Close position (submit order) |

### Real-Time Streaming

| RPC                     | Request                        | Response                | Description                |
| ----------------------- | ------------------------------ | ----------------------- | -------------------------- |
| `StreamOrderUpdates`    | `StreamOrderUpdatesRequest`    | `stream OrderUpdate`    | Real-time order status     |
| `StreamPositionUpdates` | `StreamPositionUpdatesRequest` | `stream PositionUpdate` | Real-time position changes |

---

## Risk Management

### Risk Check Pipeline

`RiskManager.check_order()` validates against 6 layers (`risk/risk_manager.py`):

| #   | Check                 | Rule                            | Default   |
| --- | --------------------- | ------------------------------- | --------- |
| 1   | **Max Order Value**   | qty × price ≤ limit             | $5,000    |
| 2   | **Sleeve gate** *(when `sleeve_id` present)* | sleeve status must be `ACTIVE` (a `FROZEN` or `CLOSED` sleeve rejects **all** orders); buys must fit the sleeve's **free cash** (read from the portfolio ledger via `LedgerClient`) | — |
| 3   | **Allowed Symbols**   | symbol in whitelist             | All       |
| 4   | **Max Position Size** | (current + new) × price ≤ limit | $10,000   |
| 5   | **Daily Loss Limit**  | daily_pnl > -limit              | $1,000    |
| 6   | **Order Rate Limit**  | orders in last 60s < limit      | 10/minute |

Returns: `RiskCheckResult(passed: bool, violations: list[str])`. A broker-failure
**circuit breaker** can additionally halt submission independently of these checks.

**Sleeve gate (layer 2)** is the ledger integration point and is **fail-safe**: if
the sleeve's state can't be fetched, the order is rejected rather than allowed
through. Unattributed/manual orders (no `sleeve_id`) skip this layer and degrade to
account-level behavior.

### Risk Limits Configuration

Can be configured at session or tenant level:

```python
class RiskLimits(BaseModel):
    max_position_size: float | None   # Max $ per position
    max_daily_loss: float | None      # Max daily loss before halt
    max_order_value: float | None     # Max $ per order
    allowed_symbols: list[str] | None # Symbol whitelist
```

### Daily P&L Tracking

The RiskManager tracks daily metrics via `DailyPnL` table:

- `realized_pnl`: Sum of closed position P&L
- `unrealized_pnl`: Sum of open position P&L
- `equity_high` / `equity_low`: For drawdown calculation
- `trades_count`, `winning_trades`, `losing_trades`
- `max_drawdown_pct`: (equity_high - current) / equity_high

### Price Fetching for Risk Checks

The max-order-value and position-size checks need a reference price. The
`RiskManager` tries, in order:

1. **Market Data Service**: HTTP call to `/quotes/{symbol}/latest`
2. **Local Cache**: Price from a recent successful fetch

If no price can be resolved, the order is **rejected** — a fail-safe risk-check
failure (`"Unable to verify order value for {symbol} - price unavailable"`), not a
guessed price. There is **no** hardcoded fallback price; the money path never sizes
against a fabricated value.

---

## Order Lifecycle

### Order Status States

```
   ╭─────────╮  submit   ╭───────────╮  accept  ╭──────────╮   fill   ╭────────╮
   │ PENDING │ ────────► │ SUBMITTED │ ───────► │ ACCEPTED │ ───────► │ FILLED │
   ╰────┬────╯           ╰─────┬─────╯          ╰────┬─────╯          ╰───▲────╯
       risk               cancel · or               partial              fill
    or reject              reject │                  fill │           remainder
        │                         │                       │                │
        ▼                         ▼                       ▼                │
   ╭──────────╮            ╭───────────╮            ╭─────────╮            │
   │ REJECTED │            │ CANCELLED │            │ PARTIAL │ ───────────╯
   ╰──────────╯            ╰───────────╯            ╰────┬────╯
                                            day order after EOD
                                                        │
                                                        ▼
                                                   ╭─────────╮
                                                   │ EXPIRED │
                                                   ╰─────────╯
```

| Status      | Description                            |
| ----------- | -------------------------------------- |
| `PENDING`   | Created in DB, not yet sent to Alpaca  |
| `SUBMITTED` | Sent to Alpaca, awaiting acceptance    |
| `ACCEPTED`  | Accepted by Alpaca, awaiting fill      |
| `PARTIAL`   | Partially filled                       |
| `FILLED`    | Fully filled                           |
| `CANCELLED` | Cancelled by user or system            |
| `REJECTED`  | Rejected by risk check or Alpaca       |
| `EXPIRED`   | Expired (e.g., day order after market) |

### Alpaca Status Mapping

```python
ALPACA_STATUS_MAP = {
    "new": "submitted",
    "accepted": "accepted",
    "pending_new": "pending",
    "partially_filled": "partial",
    "filled": "filled",
    "canceled": "cancelled",
    "rejected": "rejected",
    "expired": "expired",
}
```

---

## Position Tracking

### Position Service Operations

**open_position(tenant_id, session_id, symbol, side, qty, entry_price)**

Creates position with:

- `cost_basis = qty × entry_price`
- `market_value = qty × entry_price`
- `unrealized_pl = 0`
- `is_open = True`

**close_position(tenant_id, session_id, symbol, exit_price)**

Calculates realized P&L:

- Long: `(exit_price - entry_price) × qty`
- Short: `(entry_price - exit_price) × qty`

Sets `is_open = False`, `realized_pl = calculated_pnl`

**update_prices(tenant_id, session_id, prices)**

For each open position:

- Updates `current_price`, `market_value`
- Recalculates `unrealized_pl` and `unrealized_plpc`

**get_session_pnl(tenant_id, session_id) → (realized, unrealized)**

```
Realized P&L = SUM(realized_pl) from all positions
Unrealized P&L = SUM(unrealized_pl) from open positions only
```

---

## Data Models

### Pydantic Schemas (`models.py`)

```python
class OrderSide(StrEnum):
    BUY = "buy"
    SELL = "sell"

class OrderType(StrEnum):
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"
    TRAILING_STOP = "trailing_stop"

class OrderStatus(StrEnum):
    PENDING = "pending"
    SUBMITTED = "submitted"
    ACCEPTED = "accepted"
    PARTIAL = "partial"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"
    EXPIRED = "expired"

class TimeInForce(StrEnum):
    DAY = "day"      # Cancel at end of day
    GTC = "gtc"      # Good til cancelled
    IOC = "ioc"      # Immediate or cancel
    FOK = "fok"      # Fill or kill

class OrderCreate(BaseModel):
    symbol: str
    side: OrderSide
    qty: float = Field(..., gt=0)
    order_type: OrderType = OrderType.MARKET
    limit_price: float | None = None
    stop_price: float | None = None
    time_in_force: TimeInForce = TimeInForce.DAY
    extended_hours: bool = False

class OrderResponse(BaseModel):
    id: UUID
    alpaca_order_id: str | None = None
    symbol: str
    side: OrderSide
    qty: float
    order_type: OrderType
    limit_price: float | None = None
    stop_price: float | None = None
    status: OrderStatus
    filled_qty: float = 0
    filled_avg_price: float | None = None
    submitted_at: datetime
    filled_at: datetime | None = None

class PositionResponse(BaseModel):
    symbol: str
    qty: float
    side: str                    # "long" | "short"
    cost_basis: float
    market_value: float
    unrealized_pnl: float
    unrealized_pnl_percent: float
    current_price: float
```

### Database Models (`libs/db`)

```python
class Order(Base):
    """Order placed through trading session."""
    tenant_id: UUID
    session_id: UUID
    alpaca_order_id: str | None
    client_order_id: str
    symbol: str
    side: str                    # buy, sell
    order_type: str              # market, limit, stop, etc.
    time_in_force: str           # day, gtc, ioc, etc.
    qty: Decimal
    limit_price: Decimal | None
    stop_price: Decimal | None
    status: str
    filled_qty: Decimal
    filled_avg_price: Decimal | None
    submitted_at: datetime | None
    filled_at: datetime | None
    canceled_at: datetime | None
    failed_at: datetime | None

class Position(Base):
    """Current position in a trading session."""
    tenant_id: UUID
    session_id: UUID
    symbol: str
    side: str                    # long, short
    qty: Decimal
    avg_entry_price: Decimal
    current_price: Decimal | None
    market_value: Decimal | None
    cost_basis: Decimal
    unrealized_pl: Decimal | None
    unrealized_plpc: Decimal | None
    realized_pl: Decimal
    is_open: bool
    opened_at: datetime
    closed_at: datetime | None

class TradingSession(Base):
    """Live or paper trading session."""
    tenant_id: UUID
    strategy_id: UUID
    strategy_version: int
    credentials_id: UUID
    name: str
    mode: str                    # live, paper
    status: str                  # active, paused, stopped, error
    symbols: list[str]           # JSONB
    started_at: datetime | None
    stopped_at: datetime | None
```

---

## External Integrations

### Alpaca Trading API

Reached exclusively through the `llamatrade_alpaca` `TradingClient` (rate limiter,
circuit breaker, retry/backoff, and crash-recovery `get_order_by_client_id`); the
service supplies per-tenant credentials and never issues raw HTTP to Alpaca.

**Base URLs:**

- Paper: `https://paper-api.alpaca.markets/v2`
- Live: `https://api.alpaca.markets/v2`

**Authentication Headers:**

```
APCA-API-KEY-ID: <api_key>
APCA-API-SECRET-KEY: <api_secret>
```

**Endpoints Used:**

| Method   | Endpoint              | Purpose                |
| -------- | --------------------- | ---------------------- |
| `GET`    | `/account`            | Get account info       |
| `POST`   | `/orders`             | Submit order           |
| `GET`    | `/orders/{id}`        | Get order by ID        |
| `DELETE` | `/orders/{id}`        | Cancel order           |
| `GET`    | `/positions`          | List all positions     |
| `GET`    | `/positions/{symbol}` | Get position by symbol |
| `DELETE` | `/positions/{symbol}` | Close position         |
| `DELETE` | `/positions`          | Close all positions    |

### Market-Data Service

**Base URL:** `http://localhost:8840` (configurable via `MARKET_DATA_URL`)

**Used for:**

- Price fetching for risk checks
- Position value calculations

---

## Internal Service Connections

### Services That Call Trading

| Service      | Use Case                    | Method                         |
| ------------ | --------------------------- | ------------------------------ |
| **Frontend** | Order placement, monitoring | All RPCs                       |
| **Strategy** | Automated order execution   | `SubmitOrder`, `ClosePosition` |
| **Backtest** | Simulated order execution   | Similar interface              |

### Services That Trading Calls

| Service         | Use Case                | Method                             |
| --------------- | ----------------------- | ---------------------------------- |
| **Market-Data** | Current prices for risk | HTTP `GET /quotes/{symbol}/latest` |
| **Alpaca**      | Order execution         | REST API                           |

---

## Configuration

### Environment Variables

```bash
# Alpaca API credentials
ALPACA_API_KEY=your_api_key
ALPACA_API_SECRET=your_api_secret
ALPACA_PAPER=true              # Use paper trading endpoints

# Database
DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/llamatrade

# Market-Data service for price enrichment
MARKET_DATA_URL=http://localhost:8840

# CORS configuration
CORS_ORIGINS=http://localhost:8800,http://localhost:3000

# Logging
LOG_LEVEL=INFO
```

### Service Port

- **Port**: 8850
- **Health Check**: `GET http://localhost:8850/health`

---

## Health Check

**Endpoint:** `GET /health`

```json
{
  "status": "healthy",
  "service": "trading",
  "version": "0.1.0"
}
```

---

## Order Types

| Type            | Description                                   | Required Fields           |
| --------------- | --------------------------------------------- | ------------------------- |
| `MARKET`        | Execute immediately at current market price   | symbol, side, qty         |
| `LIMIT`         | Execute at limit price or better              | + limit_price             |
| `STOP`          | Trigger market order when stop price reached  | + stop_price              |
| `STOP_LIMIT`    | Trigger limit order when stop price reached   | + stop_price, limit_price |
| `TRAILING_STOP` | Stop price trails market by percent or amount | + trail_percent           |

## Time in Force Options

| TIF   | Name                | Description                                      |
| ----- | ------------------- | ------------------------------------------------ |
| `DAY` | Day Order           | Cancel at end of trading day                     |
| `GTC` | Good Til Cancelled  | Remains active until filled or cancelled         |
| `IOC` | Immediate or Cancel | Fill immediately or cancel remaining             |
| `FOK` | Fill or Kill        | Fill entire order immediately or cancel entirely |

---

## Complete Data Flow Example

**Scenario: Frontend submits a limit buy order**

1. **Frontend** calls `tradingClient.submitOrder({
  symbol: "AAPL",
  side: ORDER_SIDE_BUY,
  type: ORDER_TYPE_LIMIT,
  quantity: "10",
  limit_price: "185.00",
  time_in_force: TIME_IN_FORCE_DAY
})`

2. **gRPC Servicer** receives `SubmitOrderRequest`
   - Resolves identity via `resolve_identity` (the token identity; a mismatched
     wire `tenant_id` is rejected — cross-tenant guard)
   - Maps proto enums to internal enums

3. **OrderExecutor.submit_order()** is called
   - Calls `RiskManager.check_order()`
   - Risk checks: order value, position size, daily loss, rate limit

4. **Risk Check Passes**
   - Creates `Order` record in database (status=pending)
   - Generates a `client_order_id` — **deterministic** (`lt-<sha256(session:symbol:side:signal_ts)>`) for live-runner orders so a retry after a crash is idempotent; the id is sent to Alpaca, which enforces uniqueness. An already-recorded order short-circuits and is returned as-is.

5. **`llamatrade_alpaca` `TradingClient.submit_order()`** is called (with the deterministic `client_order_id`)
   - POSTs to `https://paper-api.alpaca.markets/v2/orders`
   - Receives Alpaca order ID and status

6. **Order Updated in Database**
   - `alpaca_order_id` stored
   - `status` updated to "submitted"
   - `submitted_at` timestamp set

7. **Response** returned to frontend

   ```json
   {
     "order": {
       "id": "uuid",
       "alpaca_order_id": "alpaca-uuid",
       "symbol": "AAPL",
       "side": "ORDER_SIDE_BUY",
       "type": "ORDER_TYPE_LIMIT",
       "status": "ORDER_STATUS_PENDING",
       "quantity": "10",
       "limit_price": "185.00"
     }
   }
   ```

8. **Order fills** (asynchronously)
   - Alpaca fills the order
   - Status sync updates database
   - Position created/updated in `PositionService`

---

## Summary

The trading service provides a production-ready order execution engine with:

1. **Order Execution**: Full order lifecycle from submission to fill
2. **Risk Controls**: 6-layer validation pipeline before every order
3. **Position Tracking**: Local database tracking with real-time P&L
4. **Alpaca Integration**: Paper and live trading via `llamatrade_alpaca`
5. **Real-Time Streaming**: gRPC streaming for order and position updates
6. **Multi-Tenancy**: Every RPC resolves identity via `resolve_identity` (cross-tenant guard); Alpaca credentials are per-tenant/session
7. **Crash Recovery**: Boot + periodic runner rehydration, arbitrated by per-session advisory locks
8. **Clean API**: gRPC/Connect protocol for type-safe communication

Architecture separates concerns: Servicer (gRPC) → OrderExecutor (business logic) → RiskManager (validation) → `llamatrade_alpaca` (broker) → Database (persistence) → ledger fill emission (portfolio).

---

## Error Handling

### gRPC Status Codes

| Status Code | When Raised | Example |
|-------------|-------------|---------|
| `INVALID_ARGUMENT` | Risk check violation | Order value exceeds limit |
| `FAILED_PRECONDITION` | Alpaca submission failed | Insufficient buying power |
| `NOT_FOUND` | Order or position not found | Get non-existent order |
| `INTERNAL` | Unexpected server error | Database connection failure |

### Risk Check Errors

When `RiskManager.check_order()` fails, the response includes violation details:

```python
# Example risk violation
await context.abort(
    grpc.StatusCode.INVALID_ARGUMENT,
    "Risk check failed: Order value $6,000 exceeds limit $5,000"
)
```

### Alpaca API Errors

Alpaca errors are mapped to appropriate responses:

| Alpaca Error | Trading Service Response |
|--------------|-------------------------|
| `insufficient_balance` | `FAILED_PRECONDITION` |
| `invalid_symbol` | `INVALID_ARGUMENT` |
| `market_closed` | `FAILED_PRECONDITION` |
| `rate_limit` | Retry with backoff |
| Connection error | `INTERNAL` with retry |

### Error Response Format

```json
{
  "code": "INVALID_ARGUMENT",
  "message": "Risk check failed: Order value $6,000 exceeds limit $5,000",
  "details": []
}
```

---

## Multi-Tenancy & Crash Recovery

**Tenant isolation.** The fail-closed `AuthMiddleware` populates a request-scoped
identity at the Connect boundary. Every RPC in the servicer resolves it via
`resolve_identity`: it returns the token identity and rejects a request whose wire
`tenant_id` differs (cross-tenant guard). All DB queries and ledger emissions are
`tenant_id`-scoped. Alpaca credentials are resolved per tenant/session
(`credentials.py`) — never from process-wide env defaults for user orders.

**Crash recovery (`recovery.py`).** A `StrategyRunner` lives in-process. When the
pod owning a session dies, the `trading_sessions` row stays RUNNING/PAUSED with no
runner. A boot-time and periodic (`TRADING_REHYDRATION_INTERVAL_SECONDS`, default
30s) rehydration pass re-attaches a runner to every such session. Ownership is
arbitrated by a **per-session Postgres advisory lock** held on a dedicated
connection for the runner's lifetime, so a horizontally scaled deployment never
double-runs a session; the lock frees automatically on pod death. Order-level
recovery is separate: a deterministic `client_order_id` plus `get_order_by_client_id`
lets a recorded-but-unsubmitted order resume and an already-submitted one
short-circuit (idempotent replay).

## Startup/Shutdown Sequence

### Startup

```
1. Load environment configuration (Alpaca keys, database URL)
2. Initialize logging and Prometheus metrics
3. Create FastAPI application with lifespan handler
4. In lifespan:
   a. Import Connect ASGI application from proto
   b. Create TradingServicer instance
   c. Mount Connect app at root path
   d. Start the runner rehydration loop (reclaim orphaned sessions)
5. Add CORS middleware (after AuthMiddleware, which fails closed at the edge)
6. Register health check endpoint (/health)
7. Register metrics endpoint (/metrics)
8. Start accepting requests
```

### Shutdown

```
1. Stop accepting new requests
2. Cancel the rehydration loop; release session advisory-lock leases
3. Wait for active order submissions to complete
4. Close market-data client connections
5. Close database connections
6. Flush Prometheus metrics
```

---

## Testing

### Test Structure

```
tests/
├── conftest.py                    # Shared fixtures
├── test_alert_service.py          # Reconciliation / halt alert tests
├── test_audit_service.py          # Audit logging tests
├── test_auth_isolation.py         # Per-RPC tenant-isolation tests
├── test_base_executor.py          # Base Alpaca submit/sync mixin tests
├── test_bracket_orders.py         # Bracket order tests
├── test_cache.py                  # Cache layer tests
├── test_circuit_breaker.py        # Circuit breaker tests
├── test_concurrency.py            # Concurrent execution tests
├── test_fill_handling.py          # Order fill tests
├── test_grpc_servicer.py          # gRPC endpoint tests
├── test_grpc_servicer_sessions.py # Session-lifecycle RPC tests
├── test_health.py                 # Health check tests
├── test_ledger_emission.py        # LedgerFill / reservation emission tests
├── test_live_session_service.py   # Live session tests
├── test_market_data_client.py     # Market data client tests
├── test_metrics.py                # Prometheus metrics tests
├── test_order_executor.py         # Order executor tests
├── test_order_validation.py       # OrderCreate type↔price validation tests
├── test_position_service.py       # Position service tests
├── test_providers.py              # DI factory / singleton tests
├── test_recovery.py               # Crash-recovery / rehydration tests
├── test_rehydration.py            # Runner rehydration tests
├── test_risk_manager.py           # Risk manager tests
├── test_runner.py                 # Strategy runner tests
├── test_runner_session.py         # Runner-session integration tests
├── test_runtime_adapters.py       # Shared runtime adapter tests
├── test_session_service.py        # Session service tests
├── test_sleeve_execution.py       # Sleeve-attributed execution tests
├── test_streaming.py              # Streaming tests
├── test_streaming_endpoints.py    # Streaming endpoint tests
└── test_trading_hours.py          # Market hours tests
```

### Running Tests

```bash
# Run all tests
cd services/trading && pytest

# Run with coverage
pytest --cov=src --cov-report=term-missing

# Run specific test file
pytest tests/test_order_executor.py

# Run specific test
pytest tests/test_order_executor.py::test_submit_order_success
```

### Key Test Scenarios

- **Order submission**: Happy path, risk violations, Alpaca errors
- **Risk checks**: Each of the 5 risk checks individually
- **Position tracking**: Open, close, P&L calculation
- **Streaming**: Order updates, position updates
- **Circuit breaker**: Broker failure handling
- **Concurrent execution**: Race condition handling
- **Event sourcing**: Order lifecycle events

---

## Capabilities

- **gRPC/Connect Endpoints**: SubmitOrder, CancelOrder, GetOrder, ListOrders, GetPosition, ListPositions, ClosePosition
- **Order Executor**: Order submission pipeline with Alpaca integration
- **Risk Manager**: 6-layer validation pipeline
- **Position Service**: Local position tracking with P&L
- **Alpaca Client**: REST client for paper/live trading
- **Market Data Client**: HTTP client for price fetching
- **Health Check**: Standard `/health` endpoint
- **Prometheus Metrics**: `/metrics` endpoint
- **Real-Time Streaming**: `StreamOrderUpdates` and `StreamPositionUpdates` deliver order and position changes over gRPC
- **Alpaca WebSocket**: Real-time order/trade updates from Alpaca
- **Session Management**: Trading session lifecycle (start/stop/pause)
- **Strategy Execution**: Automated strategy-driven trading
- **Order Sync**: Periodic sync with Alpaca order status
- **Extended Hours**: Pre/post-market trading support

---

## Related Documentation

- [Portfolio Ledger](../portfolio-ledger.md) - Multi-strategy execution, sleeves, ledger, and reconciliation
- [Strategy DSL](../strategy-dsl.md) - S-expression DSL reference
- [Market Data Service](market-data.md) - Real-time and historical market data
