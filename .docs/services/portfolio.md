# Portfolio Service Architecture

The portfolio service is the central hub for tracking portfolio state, positions, transactions, and performance analytics. It aggregates data from trading sessions, syncs with the trading service, and provides real-time valuation by integrating with the market-data service.

---

## Overview

The portfolio service is responsible for:

- **Portfolio Summary**: Aggregated view of total equity, cash, market value, and P&L
- **Position Tracking**: Current positions with real-time price enrichment
- **Transaction History**: Complete audit trail of all portfolio transactions
- **Performance Analytics**: Risk metrics (Sharpe, Sortino, Max Drawdown), returns, and volatility
- **Asset Allocation**: Breakdown of portfolio composition by category
- **Trading Sync**: Sync portfolio state with active trading sessions

---

## Architecture Overview

### System Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         PORTFOLIO SERVICE :8860                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                      FastAPI + Connect ASGI                         │    │
│  │   /health    PortfolioServiceASGIApplication                        │    │
│  └─────────────────────────────┬───────────────────────────────────────┘    │
│                                │                                            │
│  ┌─────────────────────────────┴───────────────────────────────────────┐    │
│  │                      gRPC Servicer                                  │    │
│  │                                                                     │    │
│  │  GetPortfolio ──────► Portfolio summary + positions                 │    │
│  │  ListPortfolios ────► List all portfolios for tenant                │    │
│  │  GetPerformance ────► Risk metrics + time series                    │    │
│  │  GetAssetAllocation ► Category breakdown                            │    │
│  │  GetPositions ──────► All current positions                         │    │
│  │  ListTransactions ──► Paginated transaction history                 │    │
│  │  RecordTransaction ─► Create new transaction                        │    │
│  │  SyncPortfolio ─────► Sync with trading session                     │    │
│  └─────────────────────────────┬───────────────────────────────────────┘    │
│                                │                                            │
│  ┌─────────────────────────────┴───────────────────────────────────────┐    │
│  │                      Service Layer                                  │    │
│  │                                                                     │    │
│  │  PortfolioService ──► Summary, positions, sync operations           │    │
│  │  PerformanceService ► Analytics, metrics, equity curves             │    │
│  │  TransactionService ► Transaction CRUD, P&L calculations            │    │
│  │  MarketDataClient ──► HTTP client for price enrichment              │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                      Database Layer                                 │    │
│  │                                                                     │    │
│  │  PortfolioSummary ──► Aggregated portfolio state (JSONB positions)  │    │
│  │  Transaction ───────► Individual transaction records                │    │
│  │  PortfolioHistory ──► Daily snapshots for analytics                 │    │
│  │  PerformanceMetrics ► Cached metric calculations                    │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                             │
└─────────────────────────────────┬───────────────────────────────────────────┘
                                  │
        ┌─────────────────────────┼─────────────────────────┐
        ▼                         ▼                         ▼
   ┌─────────────┐        ┌─────────────┐           ┌─────────────┐
   │ PostgreSQL  │        │ Market-Data │           │  Consumers  │
   │  Database   │        │  Service    │           │             │
   │             │        │   :8840     │           │  Frontend   │
   └─────────────┘        └─────────────┘           │  Trading    │
                                                    │  Backtest   │
                                                    └─────────────┘
```

### Data Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         PORTFOLIO DATA FLOW                                 │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌───────────────────────────────────────────────────────────────────┐      │
│  │                    External Sources                               │      │
│  │                                                                   │      │
│  │   Trading Service ──► Order fills, position updates               │      │
│  │   Market-Data ──────► Current prices for valuation                │      │
│  │   User Actions ─────► Deposits, withdrawals                       │      │
│  └───────────────────────────────┬───────────────────────────────────┘      │
│                                  │                                          │
│                                  ▼                                          │
│  ┌───────────────────────────────────────────────────────────────────┐      │
│  │                  TransactionService                               │      │
│  │                                                                   │      │
│  │   • Records buy/sell transactions from order fills                │      │
│  │   • Records deposits/withdrawals/dividends/fees                   │      │
│  │   • Calculates net amounts after fees                             │      │
│  │   • Provides realized P&L calculations                            │      │
│  └───────────────────────────────┬───────────────────────────────────┘      │
│                                  │                                          │
│                                  ▼                                          │
│  ┌───────────────────────────────────────────────────────────────────┐      │
│  │                   PortfolioService                                │      │
│  │                                                                   │      │
│  │   • Aggregates positions from PortfolioSummary JSONB              │      │
│  │   • Enriches positions with current prices (via MarketDataClient) │      │
│  │   • Calculates unrealized P&L per position                        │      │
│  │   • Provides total equity, cash, market value                     │      │
│  └───────────────────────────────┬───────────────────────────────────┘      │
│                                  │                                          │
│                                  ▼                                          │
│  ┌───────────────────────────────────────────────────────────────────┐      │
│  │                  PerformanceService                               │      │
│  │                                                                   │      │
│  │   • Fetches PortfolioHistory for time periods                     │      │
│  │   • Calculates daily returns from equity series                   │      │
│  │   • Computes risk metrics: Sharpe, Sortino, Max Drawdown          │      │
│  │   • Provides equity curves, daily return series                   │      │
│  └───────────────────────────────────────────────────────────────────┘      │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Directory Structure

```
services/portfolio/
├── src/
│   ├── main.py                     # FastAPI app, lifespan, health check
│   ├── models.py                   # Pydantic schemas
│   ├── services/
│   │   ├── portfolio_service.py    # Summary, positions, sync
│   │   ├── performance_service.py  # Analytics, metrics, equity curves
│   │   └── transaction_service.py  # Transaction CRUD, P&L
│   ├── clients/
│   │   └── market_data.py          # HTTP client for price enrichment
│   └── grpc/
│       └── servicer.py             # gRPC/Connect service implementation
└── tests/
    ├── conftest.py                 # Fixtures
    ├── test_portfolio_service.py   # Portfolio service tests
    └── test_performance_service.py # Performance service tests
```

---

## Core Components

| Component              | File                              | Responsibility                       |
| ---------------------- | --------------------------------- | ------------------------------------ |
| **PortfolioServicer**  | `grpc/servicer.py`                | gRPC endpoint implementations        |
| **PortfolioService**   | `services/portfolio_service.py`   | Summary, positions, price enrichment |
| **PerformanceService** | `services/performance_service.py` | Risk metrics, equity curves, returns |
| **TransactionService** | `services/transaction_service.py` | Transaction CRUD, realized P&L       |
| **MarketDataClient**   | `clients/market_data.py`          | HTTP client for current prices       |

---

## RPC Endpoints

### Portfolio Management

| RPC              | Request                 | Response                 | Description                          |
| ---------------- | ----------------------- | ------------------------ | ------------------------------------ |
| `GetPortfolio`   | `GetPortfolioRequest`   | `GetPortfolioResponse`   | Portfolio summary with all positions |
| `ListPortfolios` | `ListPortfoliosRequest` | `ListPortfoliosResponse` | List portfolios (one per tenant)     |
| `SyncPortfolio`  | `SyncPortfolioRequest`  | `SyncPortfolioResponse`  | Sync with trading session            |

### Performance Analytics

| RPC                  | Request                     | Response                     | Description                     |
| -------------------- | --------------------------- | ---------------------------- | ------------------------------- |
| `GetPerformance`     | `GetPerformanceRequest`     | `GetPerformanceResponse`     | Risk metrics + time series      |
| `GetAssetAllocation` | `GetAssetAllocationRequest` | `GetAssetAllocationResponse` | Portfolio composition breakdown |

### Position & Transaction

| RPC                 | Request                    | Response                    | Description                   |
| ------------------- | -------------------------- | --------------------------- | ----------------------------- |
| `GetPositions`      | `GetPositionsRequest`      | `GetPositionsResponse`      | All current positions         |
| `ListTransactions`  | `ListTransactionsRequest`  | `ListTransactionsResponse`  | Paginated transaction history |
| `RecordTransaction` | `RecordTransactionRequest` | `RecordTransactionResponse` | Create new transaction        |

---

## Performance Metrics

The `PerformanceService` calculates comprehensive risk-adjusted metrics using NumPy.

### Metrics Calculated

| Metric                | Formula                                     | Description                              |
| --------------------- | ------------------------------------------- | ---------------------------------------- |
| **Total Return**      | `(final - initial) / initial * 100`         | Total percentage return                  |
| **Annualized Return** | `((1 + total_return)^(252/days) - 1) * 100` | Return projected to annual rate          |
| **Volatility**        | `std(daily_returns) * sqrt(252) * 100`      | Annualized standard deviation            |
| **Sharpe Ratio**      | `sqrt(252) * mean(excess_returns) / std`    | Risk-adjusted return (vs 2% risk-free)   |
| **Sortino Ratio**     | `sqrt(252) * mean(excess) / downside_std`   | Like Sharpe but only downside volatility |
| **Max Drawdown**      | `max((peak - current) / peak) * 100`        | Maximum peak-to-trough decline           |
| **Win Rate**          | `winning_days / total_days * 100`           | Percentage of profitable days            |
| **Profit Factor**     | `sum(gains) / sum(losses)`                  | Ratio of total gains to total losses     |
| **Best/Worst Day**    | `max/min(daily_returns) * 100`              | Best and worst single-day returns        |

### Period Options

```python
PERIODS = ["1D", "1W", "1M", "3M", "6M", "1Y", "YTD", "ALL"]
```

### Calculation Flow

```python
# 1. Fetch portfolio history
history = await _get_portfolio_history(tenant_id, start_date, end_date)

# 2. Extract equity values
equities = np.array([float(h.equity) for h in history])

# 3. Calculate daily returns
daily_returns = np.diff(equities) / equities[:-1]

# 4. Compute metrics
sharpe = np.sqrt(252) * np.mean(excess_returns) / np.std(daily_returns)
sortino = np.sqrt(252) * np.mean(excess_returns) / np.std(negative_returns)
max_drawdown = np.max((np.maximum.accumulate(equities) - equities) / peak)
```

---

## Data Models

### Pydantic Schemas (`models.py`)

```python
class PositionResponse(BaseModel):
    symbol: str
    qty: float
    side: str                    # "long" | "short"
    cost_basis: float
    market_value: float
    unrealized_pnl: float
    unrealized_pnl_percent: float
    current_price: float
    avg_entry_price: float

class PortfolioSummary(BaseModel):
    total_equity: float
    cash: float
    market_value: float
    total_unrealized_pnl: float
    total_realized_pnl: float
    day_pnl: float
    day_pnl_percent: float
    total_pnl_percent: float
    positions_count: int
    updated_at: datetime

class PerformanceMetrics(BaseModel):
    period: str                  # 1D, 1W, 1M, 3M, 6M, 1Y, YTD, ALL
    total_return: float
    total_return_percent: float
    annualized_return: float
    volatility: float
    sharpe_ratio: float
    sortino_ratio: float
    max_drawdown: float
    win_rate: float
    profit_factor: float
    best_day: float
    worst_day: float
    avg_daily_return: float

class TransactionType(StrEnum):
    BUY = "buy"
    SELL = "sell"
    DIVIDEND = "dividend"
    DEPOSIT = "deposit"
    WITHDRAWAL = "withdrawal"
    FEE = "fee"

class TransactionResponse(BaseModel):
    id: UUID
    type: TransactionType
    symbol: str | None = None
    qty: float | None = None
    price: float | None = None
    amount: float
    commission: float = 0
    description: str | None = None
    executed_at: datetime
```

### Database Models (`libs/db`)

```python
class PortfolioSummary(Base):
    """Aggregated portfolio state for a tenant."""
    tenant_id: UUID
    equity: Decimal              # Total account value
    cash: Decimal                # Available cash
    buying_power: Decimal        # Available buying power
    portfolio_value: Decimal     # Total portfolio value
    daily_pl: Decimal            # Day's P&L
    daily_pl_percent: Decimal    # Day's P&L percentage
    total_pl: Decimal            # Total P&L
    total_pl_percent: Decimal    # Total P&L percentage
    positions: JSONB             # Array of position dicts
    position_count: int          # Number of positions
    last_synced_at: datetime     # Last sync with trading

class Transaction(Base):
    """Individual transaction record."""
    tenant_id: UUID
    session_id: UUID | None      # Trading session reference
    order_id: UUID | None        # Order reference
    transaction_type: str        # buy, sell, dividend, etc.
    symbol: str | None           # Stock symbol
    side: str | None             # buy, sell
    qty: Decimal | None          # Quantity
    price: Decimal | None        # Price per share
    amount: Decimal              # Total amount
    fees: Decimal                # Transaction fees
    net_amount: Decimal          # Amount after fees
    description: str | None      # Description
    transaction_date: datetime   # When executed
    settlement_date: datetime    # When settled

class PortfolioHistory(Base):
    """Daily portfolio snapshots for analytics."""
    tenant_id: UUID
    snapshot_date: date          # Date of snapshot
    equity: Decimal              # Total equity
    cash: Decimal                # Cash balance
    portfolio_value: Decimal     # Portfolio value
    daily_return: Decimal        # Day's return percentage
    cumulative_return: Decimal   # Cumulative return
    positions_snapshot: JSONB    # Positions at snapshot time
```

---

## External Integrations

### Market-Data Service (Price Enrichment)

The portfolio service calls the market-data service via HTTP to get current prices for position valuation.

**Client Configuration:**

```python
class MarketDataClient:
    base_url = os.getenv("MARKET_DATA_URL", "http://localhost:8840")
    timeout = 10.0  # seconds

    async def get_latest_price(self, symbol: str) -> float:
        """Get latest price for a single symbol."""
        response = await client.get(f"/quotes/{symbol}/latest")
        return float(response.json().get("price", 0.0))

    async def get_prices(self, symbols: list[str]) -> dict[str, float]:
        """Get prices for multiple symbols."""
        prices = {}
        for symbol in symbols:
            prices[symbol] = await self.get_latest_price(symbol)
        return prices
```

**Usage in PortfolioService:**

```python
async def _enrich_positions_with_prices(self, positions: list[dict]) -> list[PositionResponse]:
    # Get symbols and fetch current prices
    symbols = [p.get("symbol") for p in positions]
    current_prices = await self.market_data.get_prices(symbols)

    for pos in positions:
        current_price = current_prices.get(pos["symbol"], pos["current_price"])
        market_value = qty * current_price
        unrealized_pnl = (current_price - entry_price) * qty
        # ... build PositionResponse
```

---

## Internal Service Connections

### Services That Call Portfolio

| Service      | Use Case                    | Method                               |
| ------------ | --------------------------- | ------------------------------------ |
| **Frontend** | Dashboard, portfolio view   | `GetPortfolio`, `GetPerformance`     |
| **Trading**  | Portfolio sync after trades | `SyncPortfolio`, `RecordTransaction` |
| **Backtest** | Performance comparison      | `GetPerformance` (similar metrics)   |

### Services That Portfolio Calls

| Service         | Use Case                     | Method                             |
| --------------- | ---------------------------- | ---------------------------------- |
| **Market-Data** | Current prices for valuation | HTTP `GET /quotes/{symbol}/latest` |

---

## Position P&L Calculation

The service handles both long and short positions:

```python
def _calculate_unrealized_pnl(
    self,
    side: str,
    qty: float,
    entry_price: float,
    current_price: float,
) -> float:
    """Calculate unrealized P&L based on position side."""
    if side == "long":
        # Long: profit when price goes up
        return (current_price - entry_price) * qty
    else:
        # Short: profit when price goes down
        return (entry_price - current_price) * qty
```

---

## Asset Allocation

The `GetAssetAllocation` RPC breaks down portfolio composition:

```python
async def GetAssetAllocation(self, request, context):
    positions = await service.list_positions(tenant_id)
    total_value = sum(p.market_value for p in positions)

    # Group positions by category (currently all stocks)
    items = []
    for pos in positions:
        percentage = (pos.market_value / total_value) * 100
        items.append(AllocationItem(
            symbol=pos.symbol,
            value=pos.market_value,
            percentage=percentage,
            return_percent=pos.unrealized_pnl_percent,
        ))

    return GetAssetAllocationResponse(allocations=[
        AssetAllocation(
            category="Stocks",
            value=total_value,
            percentage=100.0,
            items=items,
        )
    ])
```

---

## Configuration

### Environment Variables

```bash
# Database (required)
DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/llamatrade

# Market-Data service for price enrichment
MARKET_DATA_URL=http://localhost:8840

# CORS configuration
CORS_ORIGINS=http://localhost:8800,http://localhost:3000

# Logging
LOG_LEVEL=INFO
```

### Service Port

- **Port**: 8860
- **Health Check**: `GET http://localhost:8860/health`

---

## Health Check

**Endpoint:** `GET /health`

```json
{
  "status": "healthy",
  "service": "portfolio",
  "version": "0.1.0"
}
```

---

## Transaction Types

| Type         | When Used                           | Fields Required            |
| ------------ | ----------------------------------- | -------------------------- |
| `buy`        | Order fill (buy side)               | symbol, qty, price, amount |
| `sell`       | Order fill (sell side)              | symbol, qty, price, amount |
| `dividend`   | Dividend payment received           | symbol, amount             |
| `deposit`    | Cash deposited into account         | amount                     |
| `withdrawal` | Cash withdrawn from account         | amount                     |
| `fee`        | Platform fee, commission adjustment | amount, description        |

---

## Startup Sequence

1. **Initialize Database** → `init_db()` (connection pool)
2. **Create Servicer** → `PortfolioServicer()`
3. **Mount Connect ASGI** → `PortfolioServiceASGIApplication(servicer)`

## Shutdown Sequence

1. **Close Database** → `close_db()`

---

## Complete Data Flow Example

**Scenario: Frontend requests portfolio summary**

1. **Frontend** calls `portfolioClient.getPortfolio({ context: { tenant_id } })`

2. **gRPC Servicer** receives `GetPortfolioRequest`
   - Extracts `tenant_id` from request context
   - Opens database session

3. **PortfolioService.get_summary()** is called
   - Queries `PortfolioSummary` table by tenant_id
   - Gets positions from JSONB column
   - Calls `_enrich_positions_with_prices(positions)`

4. **MarketDataClient.get_prices()** is called
   - For each symbol, calls `GET /quotes/{symbol}/latest`
   - Returns map of symbol → current price

5. **PortfolioService** calculates P&L
   - For each position:
     - `market_value = qty * current_price`
     - `unrealized_pnl = (current_price - entry_price) * qty`
   - Aggregates totals

6. **Servicer** converts to protobuf
   - `PortfolioSummary` → `Portfolio` proto message
   - `PositionResponse[]` → `Position[]` proto messages

7. **Response** returned to frontend
   ```json
   {
     "portfolio": {
       "total_value": "125000.00",
       "cash_balance": "25000.00",
       "positions_value": "100000.00",
       "total_return": "5000.00",
       "total_return_percent": "4.17"
     },
     "positions": [
       {
         "symbol": "AAPL",
         "quantity": "100",
         "market_value": "18500.00",
         "unrealized_pnl": "500.00"
       }
     ]
   }
   ```

---

## Summary

The portfolio service provides a comprehensive portfolio management layer with:

1. **Real-Time Valuation**: Position prices enriched via market-data service
2. **Performance Analytics**: Risk metrics using NumPy (Sharpe, Sortino, Max Drawdown)
3. **Transaction History**: Complete audit trail with filtering and pagination
4. **Asset Allocation**: Portfolio composition breakdown
5. **Multi-Tenancy**: All operations scoped by tenant_id
6. **Clean API**: gRPC/Connect protocol for type-safe communication
7. **Database Persistence**: SQLAlchemy async with PostgreSQL

Architecture separates concerns: Servicer (gRPC) → Services (business logic) → MarketDataClient (price enrichment) → Database (persistence).

---

## Error Handling

### gRPC Status Codes

| Status Code | When Raised | Example |
|-------------|-------------|---------|
| `NOT_FOUND` | Portfolio or transaction not found | Get non-existent portfolio |
| `INVALID_ARGUMENT` | Invalid request parameters | Invalid transaction type |
| `INTERNAL` | Unexpected server error | Database connection failure |

### P&L Calculation Edge Cases

```python
# Handle division by zero in percentage calculations
def _calculate_pnl_percent(unrealized_pnl: float, cost_basis: float) -> float:
    if cost_basis == 0:
        return 0.0
    return (unrealized_pnl / cost_basis) * 100

# Handle empty history for performance metrics
if len(history) < 2:
    return PerformanceMetrics(
        sharpe_ratio=0.0,
        sortino_ratio=0.0,
        max_drawdown=0.0,
        ...
    )
```

### Market Data Failures

Price enrichment failures are handled gracefully:

```python
async def get_prices(symbols: list[str]) -> dict[str, float]:
    prices = {}
    for symbol in symbols:
        try:
            prices[symbol] = await self.get_latest_price(symbol)
        except Exception:
            # Use last known price from position data
            prices[symbol] = 0.0
    return prices
```

### Error Response Format

```json
{
  "code": "NOT_FOUND",
  "message": "Portfolio not found for tenant",
  "details": []
}
```

---

## Testing

### Test Structure

```
tests/
├── conftest.py                    # Shared fixtures (~5200 lines)
├── test_grpc_servicer.py          # gRPC endpoint tests
├── test_health.py                 # Health check tests
├── test_performance_service.py    # Performance metrics tests
├── test_portfolio_service.py      # Portfolio service tests
└── test_transaction_service.py    # Transaction CRUD tests (~20k lines)
```

### Running Tests

```bash
# Run all tests
cd services/portfolio && pytest

# Run with coverage
pytest --cov=src --cov-report=term-missing

# Run specific test file
pytest tests/test_performance_service.py

# Run specific test
pytest tests/test_performance_service.py::test_calculate_sharpe_ratio
```

### Key Test Scenarios

- **Portfolio summary**: Position aggregation, P&L calculation
- **Price enrichment**: Market data integration, fallback handling
- **Performance metrics**: Sharpe, Sortino, drawdown calculations
- **Transaction recording**: Buy/sell, deposits, withdrawals
- **Asset allocation**: Category breakdown, percentage calculation
- **Edge cases**: Empty portfolio, zero cost basis, no history

---

## Current Implementation Status

> **Project Stage:** Early Development

### What's Real (Implemented) ✓

- [x] **gRPC/Connect Endpoints**: GetPortfolio, ListPortfolios, GetPerformance, GetAssetAllocation, GetPositions, ListTransactions, RecordTransaction, SyncPortfolio
- [x] **Portfolio Service**: Summary, position aggregation, price enrichment
- [x] **Performance Service**: Sharpe, Sortino, max drawdown, volatility
- [x] **Transaction Service**: CRUD operations, P&L calculation
- [x] **Market Data Client**: HTTP client for price fetching
- [x] **Health Check**: Standard `/health` endpoint

### What's Stubbed or Partial (TODO) ✗

- [ ] **Real-Time Streaming**: No streaming endpoint for portfolio updates
- [ ] **Trading Sync**: `SyncPortfolio` implementation incomplete
- [ ] **Historical Snapshots**: Daily snapshot generation not automated
- [ ] **Benchmark Comparison**: No SPY comparison in portfolio performance
- [ ] **Tax Lot Tracking**: FIFO/LIFO cost basis not implemented
- [ ] **Multi-Currency**: USD only, no forex support

### Known Limitations

- **Prices**: Requires market-data service for valuation
- **Sync**: Manual sync required after trades
- **History**: No automated daily snapshot generation
- **Asset Classes**: Stocks only, no bonds/options/crypto
