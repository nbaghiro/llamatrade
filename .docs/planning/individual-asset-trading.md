# Individual Asset Trading Support - Implementation Plan

## Overview

Add individual stock trading support outside of strategies. Users can place buy/sell orders directly without creating a strategy first.

**Design Approach**: Create auto-managed "manual trading sessions" per user/credentials. This reuses existing order infrastructure with minimal schema changes.

---

## Current Architecture

```
Strategy → TradingSession (strategy_id required) → Orders (session_id required) → Alpaca
```

**Constraints:**
- `Order.session_id` is mandatory FK
- `TradingSession.strategy_id` is mandatory
- All order execution flows through `OrderExecutor`

---

## Proposed Architecture

```
Manual Trade Request → Auto-create ManualSession → Orders → Alpaca
                              ↑
                    (One per credentials_id, reused)
```

---

## Phase 1: Database Schema Changes

### 1.1 Modify TradingSession Model

**File:** `libs/db/llamatrade_db/models/trading.py`

```python
class TradingSession(Base, ...):
    # Existing fields...

    # NEW: Flag for manual trading sessions
    is_manual: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # MODIFY: Make strategy_id nullable for manual sessions
    strategy_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
```

### 1.2 Migration

**File:** `libs/db/llamatrade_db/alembic/versions/20250312_000000_015_add_manual_trading_sessions.py`

```sql
-- Add is_manual flag
ALTER TABLE trading_sessions ADD COLUMN is_manual BOOLEAN NOT NULL DEFAULT FALSE;

-- Make strategy_id nullable
ALTER TABLE trading_sessions ALTER COLUMN strategy_id DROP NOT NULL;

-- Constraint: strategy sessions must have strategy_id
ALTER TABLE trading_sessions ADD CONSTRAINT chk_session_strategy
    CHECK ((is_manual = FALSE AND strategy_id IS NOT NULL) OR is_manual = TRUE);

-- Index for finding manual sessions
CREATE INDEX ix_trading_sessions_manual
    ON trading_sessions(tenant_id, credentials_id, is_manual) WHERE is_manual = TRUE;
```

---

## Phase 2: Proto Changes

**File:** `libs/proto/llamatrade_proto/protos/trading.proto`

### 2.1 New Messages

```protobuf
// Get or create manual trading session
message GetManualSessionRequest {
  TenantContext context = 1;
  string credentials_id = 2;
}

message GetManualSessionResponse {
  TradingSession session = 1;
  bool created = 2;
}

// Submit order for manual trading
message SubmitManualOrderRequest {
  TenantContext context = 1;
  string credentials_id = 2;
  string symbol = 3;
  OrderSide side = 4;
  OrderType type = 5;
  TimeInForce time_in_force = 6;
  Decimal quantity = 7;
  Decimal limit_price = 8;      // For limit orders
  Decimal stop_price = 9;       // For stop orders
  bool extended_hours = 10;
  // Optional bracket
  Decimal stop_loss_price = 11;
  Decimal take_profit_price = 12;
}

message SubmitManualOrderResponse {
  Order order = 1;
  string session_id = 2;
}

// Get account-level positions from Alpaca
message GetAccountPositionsRequest {
  TenantContext context = 1;
  string credentials_id = 2;
}

message GetAccountPositionsResponse {
  repeated Position positions = 1;
  Decimal equity = 2;
  Decimal cash = 3;
  Decimal buying_power = 4;
}

// Get account-level order history
message ListAccountOrdersRequest {
  TenantContext context = 1;
  string credentials_id = 2;
  OrderStatus status_filter = 3;  // Optional filter
  int32 limit = 4;
}

message ListAccountOrdersResponse {
  repeated Order orders = 1;
}
```

### 2.2 Extend TradingService

```protobuf
service TradingService {
  // ... existing methods ...

  // Manual trading
  rpc GetManualSession(GetManualSessionRequest) returns (GetManualSessionResponse);
  rpc SubmitManualOrder(SubmitManualOrderRequest) returns (SubmitManualOrderResponse);
  rpc GetAccountPositions(GetAccountPositionsRequest) returns (GetAccountPositionsResponse);
  rpc ListAccountOrders(ListAccountOrdersRequest) returns (ListAccountOrdersResponse);
}
```

---

## Phase 3: Backend Service Changes

### 3.1 New ManualTradingService

**File:** `services/trading/src/services/manual_trading_service.py`

```python
class ManualTradingService:
    """Manages manual trading sessions and direct order placement."""

    async def get_or_create_session(
        self, tenant_id: UUID, user_id: UUID, credentials_id: UUID
    ) -> tuple[TradingSession, bool]:
        """Get existing manual session or create one."""
        # Find existing active manual session for these credentials
        # If none, create new one with is_manual=True, strategy_id=None

    async def submit_order(
        self, tenant_id: UUID, credentials_id: UUID, order: OrderCreate
    ) -> OrderResponse:
        """Submit manual order - auto-creates session if needed."""
        # Get/create session
        # Delegate to OrderExecutor.submit_order()

    async def get_account_positions(
        self, tenant_id: UUID, credentials_id: UUID
    ) -> AccountPositionsResponse:
        """Fetch positions directly from Alpaca."""
        # Load credentials
        # Call AlpacaTradingClient.get_positions()
        # Return with account equity/cash

    async def list_account_orders(
        self, tenant_id: UUID, credentials_id: UUID, limit: int
    ) -> list[Order]:
        """List recent orders from Alpaca."""
        # Call AlpacaTradingClient.list_orders()
```

### 3.2 Update gRPC Servicer

**File:** `services/trading/src/grpc/servicer.py`

Add implementations for the 4 new RPC methods:
- `GetManualSession` - Delegates to ManualTradingService
- `SubmitManualOrder` - Delegates to ManualTradingService
- `GetAccountPositions` - Fetches from Alpaca via credentials
- `ListAccountOrders` - Fetches from Alpaca via credentials

### 3.3 Risk Management

Manual orders go through existing `RiskManager.check_order()`. For manual sessions without specific risk config, use tenant-level defaults.

---

## Phase 4: Frontend Integration

### 4.1 TradingPage Layout

**File:** `apps/web/src/pages/trading/TradingPage.tsx`

Layout (3-column with chart):
```
┌─────────────────────────────────────────────────────────────────────────┐
│ [Credentials: Paper ▼]  Account: $10,000 equity | $5,000 cash | $15k BP │
├─────────────────────────────────────────────────────────────────────────┤
│                         PRICE CHART (Selected Symbol)                    │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │  AAPL - Apple Inc.  $178.50 (+2.3%)                               │  │
│  │  [===================~~~~~~~~~~~~~~~~~~~~~~] 1D 1W 1M 3M 1Y       │  │
│  └───────────────────────────────────────────────────────────────────┘  │
├───────────────────┬─────────────────────────┬───────────────────────────┤
│ WATCHLIST         │ ORDER ENTRY             │ POSITIONS / ORDERS        │
│                   │                         │                           │
│ AAPL  $178.50 ▲   │ Symbol: [AAPL      ]    │ [Positions] [Orders]      │
│ TSLA  $245.00 ▼   │ Side:   [Buy] [Sell]    │                           │
│ NVDA  $890.00 ▲   │ Qty:    [100       ]    │ AAPL  100 @ $150          │
│ GOOGL $142.00 ▲   │ Type:   [Market    ▼]   │   +$2,850 (+19.0%)        │
│ MSFT  $415.00 ▲   │ Price:  [-------   ]    │                           │
│                   │                         │ TSLA  50 @ $200           │
│ [+ Add Symbol]    │ Est: $17,850            │   +$2,250 (+22.5%)        │
│                   │ [Submit Order]          │                           │
└───────────────────┴─────────────────────────┴───────────────────────────┘
```

### 4.2 New Components

**Core Trading:**
- `components/trading/OrderEntryForm.tsx` - Symbol, side, qty, type, price inputs
- `components/trading/AccountPositions.tsx` - Live positions from Alpaca API
- `components/trading/RecentOrders.tsx` - Order history with status badges
- `components/trading/CredentialsSelector.tsx` - Paper/Live account picker

**Watchlist & Charts:**
- `components/trading/Watchlist.tsx` - User's saved symbols with live quotes
- `components/trading/PriceChart.tsx` - Candlestick/line chart for selected symbol
- `components/trading/SymbolSearch.tsx` - Search and add symbols to watchlist

**Charting Library:** Use lightweight-charts (TradingView) - already common for trading UIs, small bundle size

### 4.3 Trading Store

**File:** `apps/web/src/store/trading.ts`

```typescript
interface TradingState {
  // Account
  selectedCredentialsId: string | null;
  accountInfo: { equity: number; cash: number; buyingPower: number } | null;

  // Positions & Orders
  positions: Position[];
  recentOrders: Order[];

  // Watchlist & Charts
  watchlist: string[];  // Persisted to localStorage
  selectedSymbol: string | null;
  quotes: Record<string, Quote>;  // Live prices

  // Actions
  selectCredentials: (id: string) => void;
  submitOrder: (order: ManualOrderCreate) => Promise<Order>;
  refreshPositions: () => Promise<void>;
  refreshOrders: () => Promise<void>;

  // Watchlist actions
  addToWatchlist: (symbol: string) => void;
  removeFromWatchlist: (symbol: string) => void;
  selectSymbol: (symbol: string) => void;
  subscribeToQuotes: () => void;  // WebSocket for live prices
}
```

### 4.4 Market Data Integration

The chart and watchlist need live price data. Use existing `marketDataClient`:
- `GetQuote(symbol)` - Current price for order form
- `GetBars(symbol, timeframe)` - Historical data for chart
- Subscribe to real-time quotes via market data streaming (if available)

---

## Phase 5: Testing

### Backend Tests
- `test_manual_trading_service.py` - Session creation, order submission
- `test_manual_trading_grpc.py` - RPC endpoint tests
- Integration test: Full flow from gRPC → Alpaca (paper)

### Frontend Tests
- Component tests for OrderEntryForm validation
- Store action tests with mocked gRPC

---

## Files to Modify

### Backend
| File | Changes |
|------|---------|
| `libs/db/llamatrade_db/models/trading.py` | Add `is_manual`, make `strategy_id` nullable |
| `libs/db/llamatrade_db/alembic/versions/xxx_add_manual_trading.py` | NEW - Migration |
| `libs/proto/llamatrade_proto/protos/trading.proto` | Add 4 new RPCs + messages |
| `services/trading/src/services/manual_trading_service.py` | NEW - Core logic |
| `services/trading/src/grpc/servicer.py` | Add 4 RPC implementations |
| `services/trading/src/models.py` | Add ManualOrderCreate schema |

### Frontend
| File | Changes |
|------|---------|
| `apps/web/src/pages/trading/TradingPage.tsx` | Implement full trading UI |
| `apps/web/src/components/trading/OrderEntryForm.tsx` | NEW - Order submission form |
| `apps/web/src/components/trading/AccountPositions.tsx` | NEW - Position list |
| `apps/web/src/components/trading/RecentOrders.tsx` | NEW - Order history |
| `apps/web/src/components/trading/CredentialsSelector.tsx` | NEW - Account picker |
| `apps/web/src/components/trading/Watchlist.tsx` | NEW - Symbol watchlist |
| `apps/web/src/components/trading/PriceChart.tsx` | NEW - TradingView chart |
| `apps/web/src/components/trading/SymbolSearch.tsx` | NEW - Add symbols |
| `apps/web/src/store/trading.ts` | NEW - Trading state |
| `apps/web/package.json` | Add lightweight-charts dependency |

---

## Verification

1. **Backend**: Run `pytest services/trading/tests/test_manual_trading*.py`
2. **Proto**: Run `make proto` and verify generated code
3. **Integration**:
   - Start services with `make dev`
   - Use gRPC UI or curl to call `SubmitManualOrder`
   - Verify order appears in Alpaca paper account
4. **Frontend**:
   - Navigate to `/trading`
   - Submit a paper order
   - Verify position updates

---

## Design Decisions (Confirmed)

1. **Position source**: Fetch from Alpaca API directly - always accurate, no drift
2. **Risk config**: Use tenant-level defaults - same limits for strategies and manual trades
3. **UI scope**: Include watchlist and basic charts for a more complete trading experience

---

## Implementation Order

1. Phase 1: Database schema changes + migration
2. Phase 2: Proto changes + `make proto`
3. Phase 3: Backend ManualTradingService + gRPC methods
4. Phase 4: Frontend components and store
5. Phase 5: Tests for all layers
