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
│ SubmitOrder ───────────► submit order after 7-layer risk checks                        │
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
│ RiskManager ───────────► 7-layer validation + circuit breaker                          │
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
                      ║  ledger:fills (Kafka lt.ledger.fills, by acct) ║
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
                 │      RiskManager.check_order()  ·  7-layer pipeline      │
                 ├──────────────────────────────────────────────────────────┤
                 │ market hours (closed → reject) · max order value ($5,000)│
                 │ sleeve gate (status + cash) · allowed-symbols whitelist  │
                 │ max position size ($10,000) · daily-loss limit ($1,000)  │
                 │ order rate limit (10 / min) + circuit breaker (halt)     │
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
            ║ LedgerFill to the ledger:fills Kafka topic (lt.ledger.fills) →    ║
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
│   ├── main.py                    # FastAPI app, lifespan, health checks, rehydration loop
│   ├── models.py                  # Pydantic schemas + enum conversion helpers
│   ├── attribution.py             # Order ledger attribution (RPC submission + recovery emission)
│   ├── credentials.py             # Per-tenant/session Alpaca credential resolution
│   ├── recovery.py                # Boot + periodic runner rehydration (advisory locks)
│   ├── ledger_events.py           # LedgerFill / LedgerReservation message builders
│   ├── metrics.py                 # Service-local facade over llamatrade_telemetry
│   ├── proto_mappers.py           # Canonical DB-row → proto mappers for trading reads
│   ├── providers.py               # DI factory for executor/services/publisher singletons
│   ├── circuit_breaker.py         # Broker-failure circuit breaker
│   ├── symbol_status.py           # Broker symbol lifecycle (tradability checks)
│   ├── grpc/
│   │   └── servicer.py            # gRPC/Connect service implementation (resolve_identity)
│   ├── executor/
│   │   ├── base.py                # Shared Alpaca submit/sync mixin (via llamatrade_alpaca)
│   │   └── order_executor.py      # Order submission, deterministic ids, ledger emission
│   ├── risk/
│   │   └── risk_manager.py        # 7-layer risk checks + sleeve-aware ledger gate
│   ├── runner/
│   │   ├── runner.py              # Per-session live strategy runner (concurrent loops)
│   │   ├── runtime_adapters.py    # Shared llamatrade_runtime adapter (opt-in loop)
│   │   ├── service_bar_stream.py  # Live bar stream backed by the market-data fan-out
│   │   ├── warmup.py              # Indicator-history preload from the market-data store
│   │   └── intent_capture.py      # Per-evaluation order-intent capture (JSON lines)
│   ├── services/
│   │   ├── live_session_service.py # Start/stop/rehydrate runners
│   │   ├── position_service.py    # Local position cache, P&L
│   │   ├── session_service.py     # TradingSession CRUD
│   │   ├── audit_service.py       # Money-path audit log
│   │   └── alert_service.py       # Notification-stream publisher facade (alerts)
│   ├── streaming/
│   │   ├── publisher.py           # Kafka event publisher (orders, positions, ledger)
│   │   └── subscriber.py          # UI stream tail-reader
│   ├── clients/
│   │   ├── market_data.py         # HTTP client for market-data service
│   │   └── portfolio_client.py    # LedgerClient wrapper (sleeve state / free cash)
│   ├── tools/
│   │   └── parity_diff.py         # Operator tool: diff two live-loop intent captures
│   └── utils/
│       ├── cache.py               # Async TTL cache
│       └── trading_hours.py       # Market hours checker
└── tests/
    ├── integration/               # Real-Postgres tests (testcontainers)
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
| **RiskManager**         | `risk/risk_manager.py`         | 7-layer validation + sleeve-aware ledger gate + daily P&L |
| **AlertService**        | `services/alert_service.py`    | Maps trading alerts to notification categories, publishes to the notification stream |
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

`RiskManager.check_order()` validates against 7 layers (`risk/risk_manager.py`):

| #   | Check                 | Rule                            | Default   |
| --- | --------------------- | ------------------------------- | --------- |
| 1   | **Market Hours**      | market must be open (`TradingHoursChecker`); skipped when `allow_outside_market_hours` is set. A closed market rejects immediately without evaluating the remaining layers | Enforced  |
| 2   | **Max Order Value**   | qty × price ≤ limit             | $5,000    |
| 3   | **Sleeve gate** *(when `sleeve_id` present)* | sleeve status must be `ACTIVE` (a `FROZEN` or `CLOSED` sleeve rejects **all** orders); buys must fit the sleeve's **free cash** and sells must not exceed the sleeve's open holdings of the symbol (read from the portfolio ledger via `LedgerClient`) | — |
| 4   | **Allowed Symbols**   | symbol in whitelist             | All       |
| 5   | **Max Position Size** | (current + new) × price ≤ limit | $10,000   |
| 6   | **Daily Loss Limit**  | daily_pnl > -limit              | $1,000    |
| 7   | **Order Rate Limit**  | orders in last 60s < limit      | 10/minute |

Layers 5-7 need database access and a `session_id`; without them they are skipped.
Returns: `RiskCheckResult(passed: bool, violations: list[str])`. A broker-failure
**circuit breaker** can additionally halt submission independently of these checks.

**Sleeve gate (layer 3)** is the ledger integration point and is **fail-safe**: if
the sleeve's state can't be fetched, the order is rejected rather than allowed
through. Unattributed/manual orders (no `sleeve_id`) skip this layer and degrade to
account-level behavior.

### Risk Limits Configuration

Can be configured at session or tenant level:

```python
class RiskLimits(BaseModel):
    max_position_size: Decimal | None   # Max $ per position
    max_daily_loss: Decimal | None      # Max daily loss before halt
    max_order_value: Decimal | None     # Max $ per order
    allowed_symbols: list[str] | None   # Symbol whitelist
    allow_outside_market_hours: bool    # Bypass layer 1 (paper trading/testing only)
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

Enums are proto-defined (`trading_pb2.OrderSide` / `OrderType` / `TimeInForce` / `OrderStatus`, `common_pb2.ExecutionMode` / `ExecutionStatus`), used as integer values with `*_to_str()` helpers only at the Alpaca boundary. Money and quantities are `Decimal`, never float. Responses are proto messages; the Pydantic layer covers requests and internal DTOs only:

```python
class OrderCreate(BaseModel):
    symbol: str
    side: OrderSide.ValueType
    qty: Decimal = Field(..., gt=0)
    order_type: OrderType.ValueType = ORDER_TYPE_MARKET
    limit_price: Decimal | None = None
    stop_price: Decimal | None = None
    trail_percent: Decimal | None = None
    time_in_force: TimeInForce.ValueType = TIME_IN_FORCE_DAY
    extended_hours: bool = False
    # Bracket order fields (stop-loss/take-profit)
    stop_loss_price: Decimal | None = None
    take_profit_price: Decimal | None = None
    bracket_time_in_force: TimeInForce.ValueType = TIME_IN_FORCE_GTC
    # Ledger attribution, fixed at origination (portfolio-ledger.md)
    sleeve_id: UUID | None = None
    account_id: UUID | None = None
    # Reference price used to size the cash reservation (never sent to the broker)
    est_price: Decimal | None = None
    # model_validator rejects orders missing the price their type requires

class SessionResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    strategy_id: UUID
    mode: ExecutionMode.ValueType
    status: ExecutionStatus.ValueType
    started_at: datetime
    stopped_at: datetime | None = None
    ...

class RiskLimits(BaseModel): ...      # per-session risk configuration
class RiskCheckResult(BaseModel): ... # pass/fail + reason
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

| Service      | Use Case                    | Method   |
| ------------ | --------------------------- | -------- |
| **Frontend** | Order placement, monitoring | All RPCs |

No other service calls trading. Strategy never calls it: sessions are started via trading's own `StartSession` RPC, trading reads the funded `StrategyExecution` (sleeve/account identity) from the shared DB, and the ledger decouples the rest (the risk check blocks orders on non-ACTIVE sleeves). Backtest simulates execution internally via `llamatrade_runtime` and never touches this service.

### Services That Trading Calls

| Service         | Use Case                                   | Method                             |
| --------------- | ------------------------------------------ | ---------------------------------- |
| **Market-Data** | Current prices for risk                    | HTTP `GET /quotes/{symbol}/latest` |
| **Portfolio**   | Sleeve state / free cash, Manual-sleeve resolution | `LedgerClient` (gRPC)      |
| **Alpaca**      | Order execution                            | `llamatrade_alpaca` REST + WS      |

Trading produces to three Kafka topic families: order/position UI events (`lt.trading.orders` / `lt.trading.positions`, keyed by session), ledger fill/reservation events (`lt.ledger.fills`, keyed by account), and notification events (`lt.notifications`, keyed by tenant, published by the `AlertService` facade below).

---

## Alerts (Notification Stream)

`services/alert_service.py` is a thin publisher facade over the platform notification stream, not a local alert engine. Each `on_*` hook (order filled/rejected, stop-loss/take-profit hit, position opened/closed/drift, reconciliation drift, sleeve frozen, risk breach, daily-loss and drawdown limits, strategy/session lifecycle, connection loss, circuit breaker) builds a proto `NotificationEvent` with machine-readable fields and publishes it to the `notifications` channel (Kafka topic `lt.notifications`, keyed by `tenant_id`). Delivery (in-app row, email, webhooks) is the notification service's job; publishes go through `publish_safe` (5s ceiling), are fire-and-forget, and never raise into the trading path.

`CATEGORY_BY_ALERT_TYPE` maps each `AlertType` to a proto `NotificationCategory` (the `events_pb2.NOTIFICATION_CATEGORY_*` constants). Most map 1:1 to a same-named category; the three risk-related types collapse onto the single `RISK_BREACH` category:

| `AlertType`                 | `NotificationCategory`      |
| --------------------------- | --------------------------- |
| `ORDER_FILLED`              | `ORDER_FILLED`              |
| `ORDER_REJECTED`            | `ORDER_REJECTED`            |
| `POSITION_OPENED`           | `POSITION_OPENED`           |
| `POSITION_CLOSED`           | `POSITION_CLOSED`           |
| `POSITION_DRIFT`            | `POSITION_DRIFT`            |
| `RECONCILIATION_DRIFT`      | `RECONCILIATION_DRIFT`      |
| `SLEEVE_FROZEN`             | `SLEEVE_FROZEN`             |
| `STOP_LOSS_HIT`             | `STOP_LOSS_HIT`             |
| `TAKE_PROFIT_HIT`           | `TAKE_PROFIT_HIT`           |
| `RISK_BREACH`               | `RISK_BREACH`               |
| `DAILY_LOSS_LIMIT`          | `RISK_BREACH`               |
| `DRAWDOWN_LIMIT`            | `RISK_BREACH`               |
| `STRATEGY_ERROR`            | `STRATEGY_ERROR`            |
| `EVALUATION_STALLED`        | `EVALUATION_STALLED`        |
| `SYMBOL_NOT_TRADABLE`       | `SYMBOL_NOT_TRADABLE`       |
| `SESSION_STARTED`           | `SESSION_STARTED`           |
| `SESSION_STOPPED`           | `SESSION_STOPPED`           |
| `SESSION_ERROR`             | `SESSION_ERROR`             |
| `CONNECTION_LOST`           | `CONNECTION_LOST`           |
| `CIRCUIT_BREAKER_TRIGGERED` | `CIRCUIT_BREAKER_TRIGGERED` |
| `CIRCUIT_BREAKER_RESET`     | `CIRCUIT_BREAKER_RESET`     |

An alert with `CRITICAL` priority publishes `NOTIFICATION_SEVERITY_CRITICAL`; every other priority publishes `NOTIFICATION_SEVERITY_UNSPECIFIED`. Three types that can re-report one logical episode (`EVALUATION_STALLED`, `SYMBOL_NOT_TRADABLE`, `SLEEVE_FROZEN`) publish under a deterministic event id derived from alert type, session, symbol, and sleeve, so repeats dedup platform-wide; all other types get a fresh occurrence id per publish.

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

# Kafka (order/position UI events + ledger fills + notifications)
KAFKA_BOOTSTRAP_SERVERS=localhost:9092

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

**Endpoint:** `GET /health` (shared `HealthChecker` from `llamatrade_common`, wired in `main.py`)

Two component checks run concurrently:

| Component  | Critical | Criteria                                                                                                        |
| ---------- | -------- | --------------------------------------------------------------------------------------------------------------- |
| `database` | yes      | `SELECT 1` on the shared engine (`cached_engine_check`, result cached 10s so kubelet probes stay cheap)          |
| `kafka`    | no       | `is_connected` on the trading event publisher's shared transport, so the probe opens no second broker connection |

Overall status: `healthy` when every check passes, `degraded` (HTTP 200) when only a
non-critical check fails, `unhealthy` (HTTP 503) when a critical check fails. Kafka is
non-critical so session reads and order submission stay available while the event
backbone recovers.

```json
{
  "status": "healthy",
  "timestamp": "2026-07-31T00:00:00Z",
  "service": "trading",
  "version": "0.1.0",
  "checks": {
    "database": { "healthy": true, "latency_ms": 1.2, "critical": true },
    "kafka": { "healthy": true, "latency_ms": 0.1, "critical": false }
  }
}
```

A failing check adds a `message` field (exception text or `"Check timed out after 5.0s"`).
`GET /health/live` always returns 200 while the process runs; `GET /health/ready`
returns 503 unless all critical dependencies are healthy.

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
   - Risk checks: market hours, order value, sleeve gate, allowed symbols, position size, daily loss, rate limit

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
2. **Risk Controls**: 7-layer validation pipeline before every order
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
├── integration/                   # Real-Postgres tests (testcontainers)
│   ├── conftest.py                # Throwaway Postgres per module, trading tables only
│   ├── test_order_constraints.py  # client_order_id uniqueness at the DB level
│   └── test_session_lock_failover.py # Advisory-lock session leases across DB failover
├── test_account_preflight.py      # Cash accounts refused, margin accounts pass
├── test_alert_service.py          # Notification-stream publisher tests
├── test_attribution.py            # Order-attribution resolution + emission backfill tests
├── test_audit_service.py          # Audit logging tests
├── test_auth_isolation.py         # Per-RPC tenant-isolation tests
├── test_base_executor.py          # Base Alpaca submit/sync mixin tests
├── test_bracket_orders.py         # Bracket order tests
├── test_cache.py                  # Cache layer tests
├── test_circuit_breaker.py        # Circuit breaker tests
├── test_concurrency.py            # Concurrent execution tests
├── test_deterministic_ids.py      # Deterministic order-id property tests
├── test_dual_path_emission.py     # Stream + REST-sync ledger emission dedup tests
├── test_factory_tenant_scope.py   # Tenant scoping of gRPC-path service factories
├── test_fill_handling.py          # Order fill tests
├── test_forming_bars.py           # One-minute stream → strategy-period bar folding tests
├── test_grpc_servicer.py          # gRPC endpoint tests
├── test_grpc_servicer_sessions.py # Session-lifecycle RPC tests
├── test_health.py                 # Health check tests
├── test_ledger_emission.py        # LedgerFill / reservation emission tests
├── test_live_session_service.py   # Live session tests
├── test_market_data_client.py     # Market data client tests
├── test_metrics.py                # Prometheus metrics tests
├── test_order_executor.py         # Order executor tests
├── test_order_validation.py       # OrderCreate type↔price validation tests
├── test_parity_capture.py         # Intent capture + parity diff tool tests
├── test_position_service.py       # Position service tests
├── test_proto_mappers.py          # DB-row → proto mapper round-trip tests
├── test_providers.py              # DI factory / singleton tests
├── test_recovery.py               # Crash-recovery / rehydration tests
├── test_rehydration.py            # Runner rehydration tests
├── test_reservation_release.py    # Reservation release on reject/expiry tests
├── test_risk_manager.py           # Risk manager tests
├── test_risk_public_gate.py       # Sleeve risk-gate wiring tests
├── test_runner.py                 # Strategy runner tests
├── test_runner_session.py         # Runner-session integration tests
├── test_runtime_adapters.py       # Shared runtime adapter tests
├── test_service_bar_stream.py     # Market-data-backed live bar stream tests
├── test_session_lease.py          # Per-session ownership lease tests
├── test_session_service.py        # Session service tests
├── test_sleeve_execution.py       # Sleeve-attributed execution tests
├── test_streaming.py              # Streaming tests
├── test_streaming_endpoints.py    # Streaming endpoint tests
├── test_symbol_lifecycle.py       # Symbol tradability lifecycle tests
├── test_trading_hours.py          # Market hours tests
└── test_warmup.py                 # Indicator-history warmup tests
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
- **Risk checks**: Each of the 7 risk-check layers individually
- **Position tracking**: Open, close, P&L calculation
- **Streaming**: Order updates, position updates
- **Circuit breaker**: Broker failure handling
- **Concurrent execution**: Race condition handling
- **Event sourcing**: Order lifecycle events

---

## Capabilities

- **gRPC/Connect Endpoints**: SubmitOrder, CancelOrder, GetOrder, ListOrders, GetPosition, ListPositions, ClosePosition
- **Order Executor**: Order submission pipeline with Alpaca integration
- **Risk Manager**: 7-layer validation pipeline
- **Position Service**: Local position tracking with P&L
- **Alpaca Client**: REST client for paper/live trading
- **Market Data Client**: HTTP client for price fetching
- **Health Check**: `/health` with database and Kafka component checks, plus `/health/live` and `/health/ready` probes
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
