# gRPC API Reference

This document describes the gRPC service contracts for inter-service communication in LlamaTrade.

---

## Overview

All backend services communicate via gRPC. The frontend uses gRPC-Web through the Kong gateway.

**Proto definitions:** `libs/proto/llamatrade/v1/`
**Generated code:** `libs/grpc/llamatrade_grpc/generated/`
**Client libraries:** `libs/grpc/llamatrade_grpc/clients/`

---

## Common Types

Defined in `common.proto`:

```protobuf
// Tenant context passed in all requests
message TenantContext {
  string tenant_id = 1;
  string user_id = 2;
  repeated string roles = 3;
}

// Standard timestamp
message Timestamp {
  int64 seconds = 1;
  int32 nanos = 2;
}

// Pagination
message PageRequest {
  int32 page = 1;       // 1-indexed
  int32 page_size = 2;  // Default: 20, Max: 100
}

message PageResponse {
  int32 total = 1;
  int32 page = 2;
  int32 page_size = 3;
  int32 total_pages = 4;
}
```

---

## Auth Service (port 8810)

### Service Definition

```protobuf
service AuthService {
  // Token validation (called by other services)
  rpc ValidateToken(ValidateTokenRequest) returns (ValidateTokenResponse);
  rpc ValidateAPIKey(ValidateAPIKeyRequest) returns (ValidateAPIKeyResponse);

  // User management (internal)
  rpc GetUser(GetUserRequest) returns (GetUserResponse);
  rpc GetTenant(GetTenantRequest) returns (GetTenantResponse);

  // Permission checks
  rpc CheckPermission(CheckPermissionRequest) returns (CheckPermissionResponse);
}
```

### Key Messages

**ValidateToken** — Called by gateway and services to validate JWT tokens:

```protobuf
message ValidateTokenRequest {
  string token = 1;
}

message ValidateTokenResponse {
  bool valid = 1;
  TenantContext context = 2;
  Timestamp expires_at = 3;
  string token_type = 4;  // "access", "refresh", "api_key"
}
```

**ValidateAPIKey** — Validate programmatic API keys:

```protobuf
message ValidateAPIKeyRequest {
  string api_key = 1;
  repeated string required_scopes = 2;
}

message ValidateAPIKeyResponse {
  bool valid = 1;
  TenantContext context = 2;
  repeated string granted_scopes = 3;
}
```

---

## Strategy Service (port 8820)

### Service Definition

```protobuf
service StrategyService {
  // CRUD operations
  rpc CreateStrategy(CreateStrategyRequest) returns (StrategyResponse);
  rpc GetStrategy(GetStrategyRequest) returns (StrategyResponse);
  rpc ListStrategies(ListStrategiesRequest) returns (ListStrategiesResponse);
  rpc UpdateStrategy(UpdateStrategyRequest) returns (StrategyResponse);
  rpc DeleteStrategy(DeleteStrategyRequest) returns (DeleteStrategyResponse);

  // Versioning
  rpc CreateVersion(CreateVersionRequest) returns (VersionResponse);
  rpc GetVersion(GetVersionRequest) returns (VersionResponse);
  rpc ListVersions(ListVersionsRequest) returns (ListVersionsResponse);

  // Templates
  rpc ListTemplates(ListTemplatesRequest) returns (ListTemplatesResponse);
  rpc GetTemplate(GetTemplateRequest) returns (TemplateResponse);

  // Compilation
  rpc CompileStrategy(CompileStrategyRequest) returns (CompileStrategyResponse);
  rpc ValidateStrategy(ValidateStrategyRequest) returns (ValidateStrategyResponse);
}
```

### Key Messages

**Strategy**:

```protobuf
message Strategy {
  string id = 1;
  string tenant_id = 2;
  string name = 3;
  string description = 4;
  StrategyType strategy_type = 5;
  StrategyStatus status = 6;
  int32 current_version = 7;
  Timestamp created_at = 8;
  Timestamp updated_at = 9;
}

enum StrategyType {
  STRATEGY_TYPE_UNSPECIFIED = 0;
  STRATEGY_TYPE_TREND_FOLLOWING = 1;
  STRATEGY_TYPE_MEAN_REVERSION = 2;
  STRATEGY_TYPE_MOMENTUM = 3;
  STRATEGY_TYPE_BREAKOUT = 4;
  STRATEGY_TYPE_CUSTOM = 5;
}

enum StrategyStatus {
  STRATEGY_STATUS_UNSPECIFIED = 0;
  STRATEGY_STATUS_DRAFT = 1;
  STRATEGY_STATUS_ACTIVE = 2;
  STRATEGY_STATUS_PAUSED = 3;
  STRATEGY_STATUS_ARCHIVED = 4;
}
```

**StrategyVersion** — Immutable configuration snapshot:

```protobuf
message StrategyVersion {
  string id = 1;
  string strategy_id = 2;
  int32 version = 3;
  string config_json = 4;    // Visual builder config
  string sexpr = 5;          // Compiled S-expression
  string change_notes = 6;
  Timestamp created_at = 7;
}
```

---

## Backtest Service (port 8830)

### Service Definition

```protobuf
service BacktestService {
  // Backtest execution
  rpc CreateBacktest(CreateBacktestRequest) returns (BacktestResponse);
  rpc GetBacktest(GetBacktestRequest) returns (BacktestResponse);
  rpc ListBacktests(ListBacktestsRequest) returns (ListBacktestsResponse);
  rpc CancelBacktest(CancelBacktestRequest) returns (BacktestResponse);

  // Results
  rpc GetBacktestResults(GetBacktestResultsRequest) returns (BacktestResultsResponse);

  // Streaming progress
  rpc StreamProgress(StreamProgressRequest) returns (stream BacktestProgress);
}
```

### Key Messages

**CreateBacktest**:

```protobuf
message CreateBacktestRequest {
  TenantContext context = 1;
  string strategy_id = 2;
  int32 strategy_version = 3;  // Optional, defaults to current
  string start_date = 4;       // YYYY-MM-DD
  string end_date = 5;
  double initial_capital = 6;
  repeated string symbols = 7; // Override strategy symbols
  BacktestConfig config = 8;
}

message BacktestConfig {
  double commission = 1;       // Per-trade commission
  double slippage = 2;         // Slippage rate (0.0005 = 0.05%)
}
```

**BacktestResults**:

```protobuf
message BacktestResultsResponse {
  string backtest_id = 1;
  BacktestMetrics metrics = 2;
  repeated EquityPoint equity_curve = 3;
  repeated Trade trades = 4;
  map<string, double> monthly_returns = 5;
  BenchmarkComparison benchmarks = 6;
}

message BacktestMetrics {
  double total_return = 1;
  double annual_return = 2;
  double sharpe_ratio = 3;
  double sortino_ratio = 4;
  double max_drawdown = 5;
  double calmar_ratio = 6;
  double volatility = 7;
  int32 total_trades = 8;
  int32 winning_trades = 9;
  int32 losing_trades = 10;
  double win_rate = 11;
  double profit_factor = 12;
  double alpha = 13;
  double beta = 14;
}
```

**Streaming Progress**:

```protobuf
message BacktestProgress {
  string backtest_id = 1;
  int32 progress = 2;        // 0-100
  string status = 3;         // "running", "completed", "failed"
  string message = 4;        // Current step description
  Timestamp timestamp = 5;
}
```

---

## Market Data Service (port 8840)

### Service Definition

```protobuf
service MarketDataService {
  // Historical bars
  rpc GetBars(GetBarsRequest) returns (GetBarsResponse);
  rpc GetLatestBar(GetLatestBarRequest) returns (Bar);

  // Quotes
  rpc GetQuote(GetQuoteRequest) returns (Quote);
  rpc GetQuotes(GetQuotesRequest) returns (GetQuotesResponse);

  // Streaming
  rpc StreamBars(StreamBarsRequest) returns (stream Bar);
  rpc StreamQuotes(StreamQuotesRequest) returns (stream Quote);
}
```

### Key Messages

**Bar** (OHLCV candle):

```protobuf
message Bar {
  string symbol = 1;
  Timestamp timestamp = 2;
  double open = 3;
  double high = 4;
  double low = 5;
  double close = 6;
  int64 volume = 7;
  double vwap = 8;        // Volume-weighted average price
  int32 trade_count = 9;
}

message GetBarsRequest {
  string symbol = 1;
  string timeframe = 2;   // "1Min", "5Min", "1Hour", "1Day"
  Timestamp start = 3;
  Timestamp end = 4;
  int32 limit = 5;        // Max bars to return
}
```

**Quote**:

```protobuf
message Quote {
  string symbol = 1;
  Timestamp timestamp = 2;
  double bid_price = 3;
  double ask_price = 4;
  int32 bid_size = 5;
  int32 ask_size = 6;
}
```

---

## Trading Service (port 8850)

### Service Definition

```protobuf
service TradingService {
  // Sessions
  rpc CreateSession(CreateSessionRequest) returns (SessionResponse);
  rpc GetSession(GetSessionRequest) returns (SessionResponse);
  rpc ListSessions(ListSessionsRequest) returns (ListSessionsResponse);
  rpc StartSession(StartSessionRequest) returns (SessionResponse);
  rpc StopSession(StopSessionRequest) returns (SessionResponse);
  rpc PauseSession(PauseSessionRequest) returns (SessionResponse);
  rpc ResumeSession(ResumeSessionRequest) returns (SessionResponse);

  // Orders
  rpc SubmitOrder(SubmitOrderRequest) returns (OrderResponse);
  rpc GetOrder(GetOrderRequest) returns (OrderResponse);
  rpc ListOrders(ListOrdersRequest) returns (ListOrdersResponse);
  rpc CancelOrder(CancelOrderRequest) returns (OrderResponse);

  // Positions
  rpc GetPositions(GetPositionsRequest) returns (GetPositionsResponse);
  rpc ClosePosition(ClosePositionRequest) returns (OrderResponse);
  rpc CloseAllPositions(CloseAllPositionsRequest) returns (CloseAllPositionsResponse);

  // Streaming
  rpc StreamOrders(StreamOrdersRequest) returns (stream OrderUpdate);
  rpc StreamPositions(StreamPositionsRequest) returns (stream PositionUpdate);
}
```

### Key Messages

**Session**:

```protobuf
message Session {
  string id = 1;
  string tenant_id = 2;
  string strategy_id = 3;
  int32 strategy_version = 4;
  string name = 5;
  TradingMode mode = 6;
  SessionStatus status = 7;
  repeated string symbols = 8;
  double realized_pnl = 9;
  double unrealized_pnl = 10;
  int32 trades_count = 11;
  Timestamp started_at = 12;
  Timestamp stopped_at = 13;
}

enum TradingMode {
  TRADING_MODE_UNSPECIFIED = 0;
  TRADING_MODE_PAPER = 1;
  TRADING_MODE_LIVE = 2;
}

enum SessionStatus {
  SESSION_STATUS_UNSPECIFIED = 0;
  SESSION_STATUS_CREATED = 1;
  SESSION_STATUS_ACTIVE = 2;
  SESSION_STATUS_PAUSED = 3;
  SESSION_STATUS_STOPPED = 4;
  SESSION_STATUS_ERROR = 5;
}
```

**Order**:

```protobuf
message Order {
  string id = 1;
  string session_id = 2;
  string alpaca_order_id = 3;
  string symbol = 4;
  OrderSide side = 5;
  OrderType order_type = 6;
  TimeInForce time_in_force = 7;
  double qty = 8;
  double limit_price = 9;
  double stop_price = 10;
  OrderStatus status = 11;
  double filled_qty = 12;
  double filled_avg_price = 13;
  Timestamp submitted_at = 14;
  Timestamp filled_at = 15;
}

enum OrderSide { BUY = 0; SELL = 1; }
enum OrderType { MARKET = 0; LIMIT = 1; STOP = 2; STOP_LIMIT = 3; TRAILING_STOP = 4; }
enum TimeInForce { DAY = 0; GTC = 1; IOC = 2; FOK = 3; }
enum OrderStatus { PENDING = 0; SUBMITTED = 1; ACCEPTED = 2; PARTIAL = 3; FILLED = 4; CANCELLED = 5; REJECTED = 6; }
```

---

## Portfolio Service (port 8860)

### Service Definition

```protobuf
service PortfolioService {
  // Positions
  rpc GetPositions(GetPositionsRequest) returns (GetPositionsResponse);
  rpc GetPosition(GetPositionRequest) returns (PositionResponse);

  // Performance
  rpc GetPerformance(GetPerformanceRequest) returns (PerformanceResponse);
  rpc GetDailyReturns(GetDailyReturnsRequest) returns (DailyReturnsResponse);

  // Transactions
  rpc ListTransactions(ListTransactionsRequest) returns (ListTransactionsResponse);
}
```

### Key Messages

**Position**:

```protobuf
message Position {
  string symbol = 1;
  double qty = 2;
  string side = 3;            // "long", "short"
  double avg_entry_price = 4;
  double current_price = 5;
  double cost_basis = 6;
  double market_value = 7;
  double unrealized_pnl = 8;
  double unrealized_pnl_percent = 9;
}
```

**Performance**:

```protobuf
message PerformanceResponse {
  double total_value = 1;
  double total_pnl = 2;
  double total_pnl_percent = 3;
  double realized_pnl = 4;
  double unrealized_pnl = 5;
  double day_pnl = 6;
  double day_pnl_percent = 7;
}
```

---

## Notification Service (port 8870)

### Service Definition

```protobuf
service NotificationService {
  // Alerts
  rpc CreateAlert(CreateAlertRequest) returns (AlertResponse);
  rpc GetAlert(GetAlertRequest) returns (AlertResponse);
  rpc ListAlerts(ListAlertsRequest) returns (ListAlertsResponse);
  rpc DeleteAlert(DeleteAlertRequest) returns (DeleteAlertResponse);

  // Channels
  rpc CreateChannel(CreateChannelRequest) returns (ChannelResponse);
  rpc ListChannels(ListChannelsRequest) returns (ListChannelsResponse);
  rpc TestChannel(TestChannelRequest) returns (TestChannelResponse);

  // Send notifications
  rpc SendNotification(SendNotificationRequest) returns (SendNotificationResponse);
}
```

---

## Billing Service (port 8880)

### Service Definition

```protobuf
service BillingService {
  // Subscriptions
  rpc GetSubscription(GetSubscriptionRequest) returns (SubscriptionResponse);
  rpc CreateSubscription(CreateSubscriptionRequest) returns (SubscriptionResponse);
  rpc CancelSubscription(CancelSubscriptionRequest) returns (SubscriptionResponse);

  // Usage
  rpc GetUsage(GetUsageRequest) returns (UsageResponse);
  rpc RecordUsage(RecordUsageRequest) returns (RecordUsageResponse);

  // Payment methods
  rpc ListPaymentMethods(ListPaymentMethodsRequest) returns (ListPaymentMethodsResponse);
  rpc AddPaymentMethod(AddPaymentMethodRequest) returns (PaymentMethodResponse);
  rpc RemovePaymentMethod(RemovePaymentMethodRequest) returns (RemovePaymentMethodResponse);
}
```

---

## Error Handling

### gRPC Status Codes

| Code | Use Case |
|------|----------|
| `OK` (0) | Success |
| `INVALID_ARGUMENT` (3) | Validation error, bad input |
| `NOT_FOUND` (5) | Resource doesn't exist |
| `ALREADY_EXISTS` (6) | Duplicate resource |
| `PERMISSION_DENIED` (7) | Insufficient permissions |
| `UNAUTHENTICATED` (16) | Missing or invalid auth |
| `INTERNAL` (13) | Server error |

### Error Details

Errors include structured details:

```protobuf
message ErrorDetail {
  string code = 1;          // "VALIDATION_ERROR", "NOT_FOUND", etc.
  string message = 2;       // Human-readable message
  map<string, string> metadata = 3;
}
```

---

## Client Usage

### Python Example

```python
from llamatrade_grpc.clients import StrategyClient

async with StrategyClient() as client:
    # List strategies
    response = await client.list_strategies(
        tenant_id="...",
        page=1,
        page_size=20
    )

    for strategy in response.strategies:
        print(f"{strategy.name}: {strategy.status}")
```

### TypeScript Example (gRPC-Web)

```typescript
import { StrategyServiceClient } from '@/generated/strategy_grpc_web_pb';

const client = new StrategyServiceClient('http://localhost:8000');

const request = new ListStrategiesRequest();
request.setPage(1);
request.setPageSize(20);

client.listStrategies(request, metadata, (err, response) => {
  if (err) {
    console.error(err);
    return;
  }
  response.getStrategiesList().forEach(strategy => {
    console.log(strategy.getName());
  });
});
```

---

## Regenerating Code

After modifying `.proto` files:

```bash
cd libs/proto
buf generate
```

This generates:
- Python code in `libs/grpc/llamatrade_grpc/generated/`
- TypeScript code in `apps/web/src/generated/`
