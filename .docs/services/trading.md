# Trading Service Architecture

The trading service is the execution engine that connects user-defined strategies to real markets via Alpaca Markets. It handles order execution, position tracking, risk management, and real-time streaming of order and position updates.

---

## Overview

The trading service is responsible for:

- **Order Execution**: Submitting, tracking, and syncing orders with Alpaca
- **Position Management**: Tracking positions with real-time P&L calculations
- **Risk Controls**: Enforcing position limits, daily loss limits, and order validation
- **Real-Time Streaming**: Streaming order and position updates to clients
- **Session Management**: Linking orders and positions to trading sessions
- **Alpaca Integration**: Direct connection to Alpaca Trading API (paper and live)

---

## Architecture Overview

### System Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          TRADING SERVICE :8850                              │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                      FastAPI + Connect ASGI                         │    │
│  │   /health    TradingServiceASGIApplication                          │    │
│  └─────────────────────────────┬───────────────────────────────────────┘    │
│                                │                                            │
│  ┌─────────────────────────────┴───────────────────────────────────────┐    │
│  │                      gRPC Servicer                                  │    │
│  │                                                                     │    │
│  │  SubmitOrder ───────► Submit order after risk checks                │    │
│  │  CancelOrder ───────► Cancel pending/submitted order                │    │
│  │  GetOrder ──────────► Get order by ID                               │    │
│  │  ListOrders ────────► List orders with filters                      │    │
│  │  GetPosition ───────► Get position by symbol                        │    │
│  │  ListPositions ─────► List all positions                            │    │
│  │  ClosePosition ─────► Close position (submit sell order)            │    │
│  │  StreamOrderUpdates ► Real-time order status changes                │    │
│  │  StreamPositionUpdates ► Real-time position updates                 │    │
│  └─────────────────────────────┬───────────────────────────────────────┘    │
│                                │                                            │
│  ┌─────────────────────────────┴───────────────────────────────────────┐    │
│  │                      Service Layer                                  │    │
│  │                                                                     │    │
│  │  OrderExecutor ─────► Submit orders, risk checks, Alpaca sync       │    │
│  │  PositionService ───► Local position tracking, P&L                  │    │
│  │  RiskManager ───────► 5-layer validation pipeline                   │    │
│  │  AlpacaTradingClient ► REST client for Alpaca API                   │    │
│  │  MarketDataClient ──► HTTP client for price fetching                │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                      Database Layer                                 │    │
│  │                                                                     │    │
│  │  TradingSession ────► Trading session records                       │    │
│  │  Order ─────────────► Order records with Alpaca sync                │    │
│  │  Position ──────────► Position tracking per session                 │    │
│  │  RiskConfig ────────► Risk limits per tenant/session                │    │
│  │  DailyPnL ──────────► Daily P&L tracking for risk                   │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                             │
└─────────────────────────────────┬───────────────────────────────────────────┘
                                  │
        ┌─────────────────────────┼─────────────────────────┐
        ▼                         ▼                         ▼
   ┌─────────────┐        ┌─────────────┐           ┌─────────────┐
   │   Alpaca    │        │ Market-Data │           │  Consumers  │
   │  Trading    │        │  Service    │           │             │
   │  REST API   │        │   :8840     │           │  Frontend   │
   └─────────────┘        └─────────────┘           │  Strategy   │
                                                    │  Portfolio  │
                                                    └─────────────┘
```

### Order Execution Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         ORDER EXECUTION FLOW                                │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌───────────────────────────────────────────────────────────────────┐      │
│  │                    Client Request                                 │      │
│  │         SubmitOrder(symbol, side, qty, type, limit_price)         │      │
│  └───────────────────────────────┬───────────────────────────────────┘      │
│                                  │                                          │
│                                  ▼                                          │
│  ┌───────────────────────────────────────────────────────────────────┐      │
│  │                    RiskManager.check_order()                      │      │
│  │                                                                   │      │
│  │   ✓ Max order value check ($5,000 default)                        │      │
│  │   ✓ Allowed symbols check (whitelist)                             │      │
│  │   ✓ Max position size check ($10,000 default)                     │      │
│  │   ✓ Daily loss limit check ($1,000 default)                       │      │
│  │   ✓ Order rate limit check (10/minute)                            │      │
│  └───────────────────────────────┬───────────────────────────────────┘      │
│                                  │                                          │
│                    ┌─────────────┴─────────────┐                            │
│                    │                           │                            │
│              Risk PASSED               Risk FAILED                          │
│                    │                           │                            │
│                    ▼                           ▼                            │
│  ┌─────────────────────────────┐  ┌─────────────────────────────┐           │
│  │  Create Order in DB         │  │  Return INVALID_ARGUMENT    │           │
│  │  (status = pending)         │  │  with violation details     │           │
│  └──────────────┬──────────────┘  └─────────────────────────────┘           │
│                 │                                                           │
│                 ▼                                                           │
│  ┌───────────────────────────────────────────────────────────────────┐      │
│  │                    AlpacaTradingClient.submit_order()             │      │
│  │              POST /v2/orders → Alpaca Trading API                 │      │
│  └───────────────────────────────┬───────────────────────────────────┘      │
│                                  │                                          │
│                    ┌─────────────┴─────────────┐                            │
│                    │                           │                            │
│              Alpaca OK                   Alpaca Error                       │
│                    │                           │                            │
│                    ▼                           ▼                            │
│  ┌─────────────────────────────┐  ┌─────────────────────────────┐           │
│  │  Update Order in DB         │  │  Update Order in DB         │           │
│  │  (status = submitted)       │  │  (status = rejected)        │           │
│  │  (alpaca_order_id = ...)    │  │  Return error               │           │
│  └─────────────────────────────┘  └─────────────────────────────┘           │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Directory Structure

```
services/trading/
├── src/
│   ├── main.py                    # FastAPI app, lifespan, health check
│   ├── models.py                  # Pydantic schemas
│   ├── alpaca_client.py           # Alpaca REST API client
│   ├── grpc/
│   │   └── servicer.py            # gRPC/Connect service implementation
│   ├── executor/
│   │   └── order_executor.py      # Order submission, risk checks, Alpaca sync
│   ├── services/
│   │   └── position_service.py    # Local position tracking, P&L
│   ├── risk/
│   │   └── risk_manager.py        # Risk checks, limits, daily P&L tracking
│   └── clients/
│       └── market_data.py         # HTTP client for market-data service
└── tests/
    └── test_*.py                  # Test suite
```

---

## Core Components

| Component               | File                           | Responsibility                                          |
| ----------------------- | ------------------------------ | ------------------------------------------------------- |
| **TradingServicer**     | `grpc/servicer.py`             | gRPC endpoint implementations                           |
| **OrderExecutor**       | `executor/order_executor.py`   | Submit orders, sync with Alpaca, manage order lifecycle |
| **PositionService**     | `services/position_service.py` | Local position tracking, P&L calculation                |
| **RiskManager**         | `risk/risk_manager.py`         | Validate orders, enforce limits, track daily P&L        |
| **AlpacaTradingClient** | `alpaca_client.py`             | REST client for Alpaca Trading API                      |
| **MarketDataClient**    | `clients/market_data.py`       | HTTP client for market-data service                     |

---

## RPC Endpoints

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

`RiskManager.check_order()` validates against 5 checks:

| #   | Check                 | Rule                            | Default   |
| --- | --------------------- | ------------------------------- | --------- |
| 1   | **Max Order Value**   | qty × price ≤ limit             | $5,000    |
| 2   | **Allowed Symbols**   | symbol in whitelist             | All       |
| 3   | **Max Position Size** | (current + new) × price ≤ limit | $10,000   |
| 4   | **Daily Loss Limit**  | daily_pnl > -limit              | $1,000    |
| 5   | **Order Rate Limit**  | orders in last 60s < limit      | 10/minute |

Returns: `RiskCheckResult(passed: bool, violations: list[str])`

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

### Price Fetching Fallback

Multi-layer fallback for price estimation:

1. **Market Data Service**: HTTP call to `/quotes/{symbol}/latest`
2. **Local Cache**: Price from recent successful fetch
3. **Database Position**: Last known price from position tracking
4. **Default**: Return 100.0 (last resort)

---

## Order Lifecycle

### Order Status States

```
PENDING ──► SUBMITTED ──► ACCEPTED ──► FILLED
    │           │             │
    │           │             └──► PARTIAL ──► FILLED
    │           │
    │           └──► CANCELLED
    │
    └──► REJECTED
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
   - Extracts `tenant_id` from context
   - Maps proto enums to internal enums

3. **OrderExecutor.submit_order()** is called
   - Calls `RiskManager.check_order()`
   - Risk checks: order value, position size, daily loss, rate limit

4. **Risk Check Passes**
   - Creates `Order` record in database (status=pending)
   - Generates `client_order_id`

5. **AlpacaTradingClient.submit_order()** is called
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
2. **Risk Controls**: 5-layer validation pipeline before every order
3. **Position Tracking**: Local database tracking with real-time P&L
4. **Alpaca Integration**: Direct connection to paper and live trading
5. **Real-Time Streaming**: gRPC streaming for order and position updates
6. **Multi-Tenancy**: Complete tenant isolation via session scoping
7. **Clean API**: gRPC/Connect protocol for type-safe communication

Architecture separates concerns: Servicer (gRPC) → OrderExecutor (business logic) → RiskManager (validation) → AlpacaClient (broker) → Database (persistence).

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
5. Add CORS middleware
6. Register health check endpoint (/health)
7. Register metrics endpoint (/metrics)
8. Start accepting requests
```

### Shutdown

```
1. Stop accepting new requests
2. Wait for active order submissions to complete
3. Close Alpaca client connections
4. Close market-data client connections
5. Close database connections
6. Flush Prometheus metrics
```

---

## Testing

### Test Structure

```
tests/
├── conftest.py                    # Shared fixtures (~7600 lines)
├── test_alert_service.py          # Alert service tests
├── test_audit_service.py          # Audit logging tests
├── test_bar_stream.py             # Bar data streaming tests
├── test_base_executor.py          # Base executor tests
├── test_bracket_orders.py         # Bracket order tests
├── test_cache.py                  # Cache layer tests
├── test_circuit_breaker.py        # Circuit breaker tests
├── test_compiler_adapter.py       # Strategy compilation tests
├── test_concurrency.py            # Concurrent execution tests
├── test_event_sourced_executor.py # Event sourcing tests
├── test_events.py                 # Event handling tests
├── test_fill_handling.py          # Order fill tests
├── test_grpc_servicer.py          # gRPC endpoint tests
├── test_health.py                 # Health check tests
├── test_live_session_service.py   # Live session tests
├── test_market_data_client.py     # Market data client tests
├── test_metrics.py                # Prometheus metrics tests
├── test_order_executor.py         # Order executor tests
├── test_position_service.py       # Position service tests
├── test_risk_manager.py           # Risk manager tests (~30k lines)
├── test_runner.py                 # Strategy runner tests
├── test_session_service.py        # Session service tests
├── test_streaming_endpoints.py    # Streaming endpoint tests
├── test_streaming.py              # Streaming tests
├── test_trade_stream.py           # Trade streaming tests
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

## Current Implementation Status

> **Project Stage:** Early Development

### What's Real (Implemented) ✓

- [x] **gRPC/Connect Endpoints**: SubmitOrder, CancelOrder, GetOrder, ListOrders, GetPosition, ListPositions, ClosePosition
- [x] **Order Executor**: Order submission pipeline with Alpaca integration
- [x] **Risk Manager**: 5-layer validation pipeline
- [x] **Position Service**: Local position tracking with P&L
- [x] **Alpaca Client**: REST client for paper/live trading
- [x] **Market Data Client**: HTTP client for price fetching
- [x] **Health Check**: Standard `/health` endpoint
- [x] **Prometheus Metrics**: `/metrics` endpoint

### What's Stubbed or Partial (TODO) ✗

- [ ] **Real-Time Streaming**: `StreamOrderUpdates`, `StreamPositionUpdates` - stubs
- [ ] **Alpaca WebSocket**: Real-time order/trade updates from Alpaca
- [ ] **Session Management**: Trading session lifecycle (start/stop/pause)
- [ ] **Strategy Execution**: Automated strategy-driven trading
- [ ] **Order Sync**: Periodic sync with Alpaca order status
- [ ] **Extended Hours**: Pre/post-market trading support

### Known Limitations

- **Streaming**: Currently polling-based, not real-time
- **Sessions**: Manual order placement only, no automated strategy execution
- **Order Types**: Basic types only (market, limit), no complex orders
- **Markets**: US equities only via Alpaca

---

## Related Documentation

- [Strategy Execution](../strategy-execution.md) - How strategies compile, evaluate, and generate orders
- [Strategy DSL](../strategy-dsl.md) - S-expression DSL reference
- [Market Data Service](market-data.md) - Real-time and historical market data
