# gRPC / Connect Protocol Guide

This document covers the gRPC and Connect protocol setup for LlamaTrade, including service contracts, debugging, and development workflows.

---

## Overview

LlamaTrade uses **Protocol Buffers** (protobuf) for service contracts and two protocols for communication:

- **Connect Protocol**: Frontend (browser) to backend services over HTTP/1.1 with JSON
- **gRPC**: Service-to-service communication over HTTP/2 with binary protobuf

**Proto definitions:** `libs/proto/llamatrade/v1/`
**Generated Python code:** `libs/grpc/llamatrade/v1/`
**Generated TypeScript code:** `apps/web/src/generated/proto/llamatrade/v1/`
**Client libraries:** `libs/grpc/llamatrade_grpc/clients/`

### Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│  Frontend (React)                                                       │
│  Connect client with JSON format (useBinaryFormat: false)               │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                    POST /llamatrade.v1.AuthService/Login
                    Content-Type: application/json
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  FastAPI + Connect ASGI Application                                     │
│  AuthServiceASGIApplication(servicer)                                   │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  Servicer (Business Logic)                                              │
│  AuthServicer.login(request, ctx) → LoginResponse                       │
└─────────────────────────────────────────────────────────────────────────┘
```

### Service Ports

| Service | Port |
|---------|------|
| Auth | 8810 |
| Strategy | 8820 |
| Backtest | 8830 |
| Market Data | 8840 |
| Trading | 8850 |
| Portfolio | 8860 |
| Notification | 8870 |
| Billing | 8880 |
| Frontend | 8800 |

---

## Debugging

### Complete Request Flow

Using `Login` as an example:

```
1. FRONTEND          LoginPage.tsx → authClient.login({ email, password })
        │
        ▼
2. CONNECT CLIENT    Serializes to JSON, adds headers
        │
        ▼
3. HTTP REQUEST      POST http://localhost:8810/llamatrade.v1.AuthService/Login
        │
        ▼
4. CONNECT ASGI      Routes to servicer method
        │
        ▼
5. SERVICER          AuthServicer.login() → business logic
        │
        ▼
6. DATABASE          SELECT * FROM users WHERE email = ?
```

### Layer 1: Frontend (React)

**File:** `apps/web/src/pages/LoginPage.tsx`

```typescript
// Add console logging for debugging
console.log('Login request:', { email, password: '***' });
try {
  const response = await authClient.login({ email, password });
  console.log('Login response:', response);
} catch (err) {
  console.error('Login error:', err);
  if (err instanceof ConnectError) {
    console.error('Code:', err.code, 'Message:', err.message);
  }
}
```

### Layer 2: Browser DevTools (Network Tab)

Since `useBinaryFormat: false` is set in `grpc-client.ts`, requests are JSON-readable:

```
Request URL: http://localhost:8810/llamatrade.v1.AuthService/Login
Request Method: POST
Content-Type: application/json

Request Payload:
{
  "email": "user@example.com",
  "password": "secret"
}

Response:
{
  "accessToken": "eyJhbGciOiJIUzI1NiIs...",
  "refreshToken": "eyJhbGciOiJIUzI1NiIs...",
  "user": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "email": "user@example.com",
    "roles": ["admin"]
  }
}
```

### Layer 3: curl (Test Without Frontend)

```bash
# Login request
curl -X POST http://localhost:8810/llamatrade.v1.AuthService/Login \
  -H "Content-Type: application/json" \
  -d '{"email": "user@example.com", "password": "secret"}'

# With verbose output
curl -v -X POST http://localhost:8810/llamatrade.v1.AuthService/Login \
  -H "Content-Type: application/json" \
  -d '{"email": "user@example.com", "password": "secret"}'

# Protected endpoint (requires token)
TOKEN=$(curl -s -X POST http://localhost:8810/llamatrade.v1.AuthService/Login \
  -H "Content-Type: application/json" \
  -d '{"email": "user@example.com", "password": "secret"}' \
  | jq -r '.accessToken')

curl -X POST http://localhost:8820/llamatrade.v1.StrategyService/ListStrategies \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{}'
```

**Success response:**
```json
{
  "accessToken": "eyJhbGciOiJIUzI1NiIs...",
  "refreshToken": "eyJhbGciOiJIUzI1NiIs...",
  "user": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "tenantId": "tenant-123",
    "email": "user@example.com",
    "roles": ["admin"],
    "isActive": true
  }
}
```

**Error response:**
```json
{
  "code": "unauthenticated",
  "message": "Invalid email or password"
}
```

### Layer 4: Server Logs (uvicorn)

```bash
# Run with debug logging
cd services/auth
PYTHONPATH=. uvicorn src.main:app --host 0.0.0.0 --port 8810 --log-level debug
```

### Layer 5: Servicer Logging

**File:** `services/auth/src/grpc/servicer.py`

```python
import logging
logger = logging.getLogger(__name__)

async def login(self, request: auth_pb2.LoginRequest, ctx: Any) -> auth_pb2.LoginResponse:
    logger.info("Login attempt for email: %s", request.email)

    async with await self._get_db() as db:
        result = await db.execute(
            select(User).where(User.email == request.email)
        )
        user = result.scalar_one_or_none()

        logger.debug("User found: %s", user is not None)

        if not user:
            logger.warning("Login failed: user not found for %s", request.email)
            raise ConnectError(Code.UNAUTHENTICATED, "Invalid email or password")
```

Set log level:
```bash
LOG_LEVEL=DEBUG uvicorn src.main:app --port 8810
```

### Layer 6: Database Queries

Enable SQLAlchemy echo mode:

```python
# In database.py
engine = create_async_engine(
    DATABASE_URL,
    echo=True,  # Logs all SQL queries
)
```

Output:
```
INFO sqlalchemy.engine.Engine SELECT users.id, users.email, users.password_hash, ...
INFO sqlalchemy.engine.Engine FROM users WHERE users.email = $1
INFO sqlalchemy.engine.Engine [generated in 0.00012s] ('user@example.com',)
```

### Debugging Tools Summary

| Layer | Tool | Command/Setting |
|-------|------|-----------------|
| Frontend | Browser DevTools | Network tab → Filter by `Fetch/XHR` |
| Frontend | React DevTools | Inspect component state |
| HTTP | curl | `curl -v -X POST ...` |
| HTTP | HTTPie | `http POST localhost:8810/...` |
| Server | uvicorn logs | `--log-level debug` |
| Servicer | Python logging | `logger.debug(...)` |
| Database | SQLAlchemy echo | `echo=True` in engine |
| Database | psql | Direct query inspection |

### Inspect JWT Token

```bash
# Decode JWT payload
echo $TOKEN | cut -d'.' -f2 | base64 -d 2>/dev/null | jq

# Output:
{
  "sub": "user-uuid",
  "tenant_id": "tenant-uuid",
  "email": "user@example.com",
  "roles": ["admin"],
  "type": "access",
  "exp": 1709123456
}
```

### Quick Debug Checklist

```
□ Is the service running?           → curl localhost:8810/health
□ Is CORS configured?               → Check browser console for CORS errors
□ Is the URL correct?               → /llamatrade.v1.AuthService/Login
□ Is Content-Type set?              → application/json
□ Is the request body valid JSON?   → Check browser Network tab
□ Is auth token present?            → Check Authorization header
□ Is token expired?                 → Decode and check exp claim
□ Is database connected?            → Check service logs for DB errors
□ Is the user active?               → Check is_active in database
```

### Common Issues

**"Connection refused"**
```bash
# Check if service is running
curl http://localhost:8810/health

# Check port binding
lsof -i :8810
```

**"CORS error" (browser only)**
```python
# Check CORS_ORIGINS in service main.py
CORS_ORIGINS = os.getenv(
    "CORS_ORIGINS",
    "http://localhost:8800,http://localhost:3000"
).split(",")
```

**"Unauthenticated" on protected endpoint**
```bash
# Verify token is being sent
# Check Authorization header in Network tab
# Ensure token hasn't expired
```

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
message PaginationRequest {
  int32 page = 1;       // 1-indexed
  int32 page_size = 2;  // Default: 20, Max: 100
}

message PaginationResponse {
  int32 total = 1;
  int32 page = 2;
  int32 page_size = 3;
  int32 total_pages = 4;
}

// Decimal for financial precision
message Decimal {
  string value = 1;  // String representation to avoid floating point issues
}
```

---

## Auth Service (port 8810)

### Service Definition

```protobuf
service AuthService {
  // Public endpoints (no auth required)
  rpc Login(LoginRequest) returns (LoginResponse);
  rpc Register(RegisterRequest) returns (RegisterResponse);
  rpc RefreshToken(RefreshTokenRequest) returns (RefreshTokenResponse);

  // Protected endpoints
  rpc Logout(LogoutRequest) returns (LogoutResponse);
  rpc GetCurrentUser(GetCurrentUserRequest) returns (GetCurrentUserResponse);
  rpc ChangePassword(ChangePasswordRequest) returns (ChangePasswordResponse);

  // Internal (service-to-service)
  rpc ValidateToken(ValidateTokenRequest) returns (ValidateTokenResponse);
  rpc ValidateAPIKey(ValidateAPIKeyRequest) returns (ValidateAPIKeyResponse);
  rpc GetUser(GetUserRequest) returns (GetUserResponse);
  rpc GetTenant(GetTenantRequest) returns (GetTenantResponse);
  rpc CheckPermission(CheckPermissionRequest) returns (CheckPermissionResponse);
}
```

### Key Messages

**Login**:
```protobuf
message LoginRequest {
  string email = 1;
  string password = 2;
}

message LoginResponse {
  string access_token = 1;
  string refresh_token = 2;
  User user = 3;
  Timestamp access_token_expires_at = 4;
  Timestamp refresh_token_expires_at = 5;
}
```

**ValidateToken** (called by all services):
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

---

## Strategy Service (port 8820)

### Service Definition

```protobuf
service StrategyService {
  // CRUD
  rpc GetStrategy(GetStrategyRequest) returns (GetStrategyResponse);
  rpc ListStrategies(ListStrategiesRequest) returns (ListStrategiesResponse);
  rpc CreateStrategy(CreateStrategyRequest) returns (CreateStrategyResponse);
  rpc UpdateStrategy(UpdateStrategyRequest) returns (UpdateStrategyResponse);
  rpc DeleteStrategy(DeleteStrategyRequest) returns (DeleteStrategyResponse);

  // Versioning
  rpc ListStrategyVersions(ListStrategyVersionsRequest) returns (ListStrategyVersionsResponse);

  // Compilation
  rpc CompileStrategy(CompileStrategyRequest) returns (CompileStrategyResponse);
  rpc ValidateStrategy(ValidateStrategyRequest) returns (ValidateStrategyResponse);

  // Status
  rpc UpdateStrategyStatus(UpdateStrategyStatusRequest) returns (UpdateStrategyStatusResponse);
}
```

### Key Messages

```protobuf
message Strategy {
  string id = 1;
  string tenant_id = 2;
  string name = 3;
  string description = 4;
  StrategyType strategy_type = 5;
  StrategyStatus status = 6;
  int32 current_version = 7;
  string dsl_code = 8;
  string compiled_json = 9;
  Timestamp created_at = 10;
  Timestamp updated_at = 11;
}

enum StrategyStatus {
  STRATEGY_STATUS_UNSPECIFIED = 0;
  STRATEGY_STATUS_DRAFT = 1;
  STRATEGY_STATUS_ACTIVE = 2;
  STRATEGY_STATUS_PAUSED = 3;
  STRATEGY_STATUS_ARCHIVED = 4;
}
```

---

## Backtest Service (port 8830)

### Service Definition

```protobuf
service BacktestService {
  // Execution
  rpc RunBacktest(RunBacktestRequest) returns (RunBacktestResponse);
  rpc GetBacktest(GetBacktestRequest) returns (GetBacktestResponse);
  rpc ListBacktests(ListBacktestsRequest) returns (ListBacktestsResponse);
  rpc CancelBacktest(CancelBacktestRequest) returns (CancelBacktestResponse);
  rpc CompareBacktests(CompareBacktestsRequest) returns (CompareBacktestsResponse);

  // Streaming progress (server-side streaming)
  rpc StreamBacktestProgress(StreamBacktestProgressRequest) returns (stream BacktestProgressUpdate);
}
```

### Key Messages

```protobuf
message BacktestConfig {
  string strategy_id = 1;
  int32 strategy_version = 2;
  Timestamp start_date = 3;
  Timestamp end_date = 4;
  Decimal initial_capital = 5;
  repeated string symbols = 6;
  Decimal commission = 7;
  Decimal slippage_percent = 8;
  bool allow_shorting = 9;
  string timeframe = 10;
}

message BacktestMetrics {
  Decimal total_return = 1;
  Decimal annualized_return = 2;
  Decimal sharpe_ratio = 3;
  Decimal sortino_ratio = 4;
  Decimal max_drawdown = 5;
  int32 total_trades = 6;
  int32 winning_trades = 7;
  Decimal win_rate = 8;
  Decimal profit_factor = 9;
}

message BacktestProgressUpdate {
  string backtest_id = 1;
  BacktestStatus status = 2;
  int32 progress_percent = 3;
  string current_date = 4;
  string message = 5;
  Timestamp timestamp = 6;
}
```

---

## Market Data Service (port 8840)

### Service Definition

```protobuf
service MarketDataService {
  // Historical data
  rpc GetHistoricalBars(GetHistoricalBarsRequest) returns (GetHistoricalBarsResponse);
  rpc GetMultiBars(GetMultiBarsRequest) returns (GetMultiBarsResponse);

  // Snapshots
  rpc GetSnapshot(GetSnapshotRequest) returns (Snapshot);
  rpc GetSnapshots(GetSnapshotsRequest) returns (GetSnapshotsResponse);

  // Market info
  rpc GetMarketStatus(GetMarketStatusRequest) returns (GetMarketStatusResponse);

  // Streaming (server-side streaming)
  rpc StreamBars(StreamBarsRequest) returns (stream Bar);
  rpc StreamQuotes(StreamQuotesRequest) returns (stream Quote);
  rpc StreamTrades(StreamTradesRequest) returns (stream Trade);
}
```

### Key Messages

```protobuf
message Bar {
  string symbol = 1;
  Timestamp timestamp = 2;
  Decimal open = 3;
  Decimal high = 4;
  Decimal low = 5;
  Decimal close = 6;
  int64 volume = 7;
  Decimal vwap = 8;
  int32 trade_count = 9;
}

message Quote {
  string symbol = 1;
  Timestamp timestamp = 2;
  Decimal bid_price = 3;
  Decimal ask_price = 4;
  int32 bid_size = 5;
  int32 ask_size = 6;
}
```

---

## Trading Service (port 8850)

### Service Definition

```protobuf
service TradingService {
  // Orders
  rpc SubmitOrder(SubmitOrderRequest) returns (SubmitOrderResponse);
  rpc GetOrder(GetOrderRequest) returns (GetOrderResponse);
  rpc ListOrders(ListOrdersRequest) returns (ListOrdersResponse);
  rpc CancelOrder(CancelOrderRequest) returns (CancelOrderResponse);

  // Positions
  rpc GetPosition(GetPositionRequest) returns (GetPositionResponse);
  rpc ListPositions(ListPositionsRequest) returns (ListPositionsResponse);
  rpc ClosePosition(ClosePositionRequest) returns (ClosePositionResponse);

  // Streaming (server-side streaming)
  rpc StreamOrderUpdates(StreamOrderUpdatesRequest) returns (stream OrderUpdate);
  rpc StreamPositionUpdates(StreamPositionUpdatesRequest) returns (stream PositionUpdate);
}
```

### Key Messages

```protobuf
message Order {
  string id = 1;
  string tenant_id = 2;
  string symbol = 3;
  OrderSide side = 4;
  OrderType order_type = 5;
  TimeInForce time_in_force = 6;
  Decimal quantity = 7;
  Decimal limit_price = 8;
  Decimal stop_price = 9;
  OrderStatus status = 10;
  Decimal filled_quantity = 11;
  Decimal filled_avg_price = 12;
  Timestamp submitted_at = 13;
  Timestamp filled_at = 14;
}

enum OrderSide { ORDER_SIDE_UNSPECIFIED = 0; ORDER_SIDE_BUY = 1; ORDER_SIDE_SELL = 2; }
enum OrderType { ORDER_TYPE_UNSPECIFIED = 0; ORDER_TYPE_MARKET = 1; ORDER_TYPE_LIMIT = 2; ORDER_TYPE_STOP = 3; }
enum OrderStatus { ORDER_STATUS_UNSPECIFIED = 0; ORDER_STATUS_PENDING = 1; ORDER_STATUS_FILLED = 2; ORDER_STATUS_CANCELLED = 3; }
```

---

## Portfolio Service (port 8860)

### Service Definition

```protobuf
service PortfolioService {
  rpc GetPortfolio(GetPortfolioRequest) returns (GetPortfolioResponse);
  rpc ListPortfolios(ListPortfoliosRequest) returns (ListPortfoliosResponse);
  rpc GetPerformance(GetPerformanceRequest) returns (GetPerformanceResponse);
  rpc GetAssetAllocation(GetAssetAllocationRequest) returns (GetAssetAllocationResponse);
  rpc GetPositions(GetPositionsRequest) returns (GetPositionsResponse);
  rpc ListTransactions(ListTransactionsRequest) returns (ListTransactionsResponse);
  rpc RecordTransaction(RecordTransactionRequest) returns (RecordTransactionResponse);
  rpc SyncPortfolio(SyncPortfolioRequest) returns (SyncPortfolioResponse);
}
```

---

## Notification Service (port 8870)

### Service Definition

```protobuf
service NotificationService {
  rpc ListNotifications(ListNotificationsRequest) returns (ListNotificationsResponse);
  rpc MarkAsRead(MarkAsReadRequest) returns (MarkAsReadResponse);
  rpc ListAlerts(ListAlertsRequest) returns (ListAlertsResponse);
  rpc CreateAlert(CreateAlertRequest) returns (CreateAlertResponse);
  rpc DeleteAlert(DeleteAlertRequest) returns (DeleteAlertResponse);
  rpc ToggleAlert(ToggleAlertRequest) returns (ToggleAlertResponse);
  rpc ListChannels(ListChannelsRequest) returns (ListChannelsResponse);
  rpc UpdateChannel(UpdateChannelRequest) returns (UpdateChannelResponse);
  rpc TestChannel(TestChannelRequest) returns (TestChannelResponse);
}
```

---

## Billing Service (port 8880)

### Service Definition

```protobuf
service BillingService {
  // Subscriptions
  rpc GetSubscription(GetSubscriptionRequest) returns (GetSubscriptionResponse);
  rpc CreateSubscription(CreateSubscriptionRequest) returns (CreateSubscriptionResponse);
  rpc UpdateSubscription(UpdateSubscriptionRequest) returns (UpdateSubscriptionResponse);
  rpc CancelSubscription(CancelSubscriptionRequest) returns (CancelSubscriptionResponse);
  rpc ResumeSubscription(ResumeSubscriptionRequest) returns (ResumeSubscriptionResponse);

  // Usage & Invoices
  rpc GetUsage(GetUsageRequest) returns (GetUsageResponse);
  rpc ListInvoices(ListInvoicesRequest) returns (ListInvoicesResponse);
  rpc GetInvoice(GetInvoiceRequest) returns (GetInvoiceResponse);

  // Plans
  rpc ListPlans(ListPlansRequest) returns (ListPlansResponse);

  // Payment Methods
  rpc ListPaymentMethods(ListPaymentMethodsRequest) returns (ListPaymentMethodsResponse);
  rpc AddPaymentMethod(AddPaymentMethodRequest) returns (AddPaymentMethodResponse);
  rpc RemovePaymentMethod(RemovePaymentMethodRequest) returns (RemovePaymentMethodResponse);

  // Stripe integration
  rpc CreateCheckoutSession(CreateCheckoutSessionRequest) returns (CreateCheckoutSessionResponse);
  rpc CreatePortalSession(CreatePortalSessionRequest) returns (CreatePortalSessionResponse);
}
```

---

## Error Handling

### Connect/gRPC Status Codes

| Code | Name | Use Case |
|------|------|----------|
| 0 | `OK` | Success |
| 3 | `INVALID_ARGUMENT` | Validation error, bad input |
| 5 | `NOT_FOUND` | Resource doesn't exist |
| 6 | `ALREADY_EXISTS` | Duplicate resource |
| 7 | `PERMISSION_DENIED` | Insufficient permissions |
| 13 | `INTERNAL` | Server error |
| 16 | `UNAUTHENTICATED` | Missing or invalid auth |

### Python Error Handling

```python
from connectrpc.code import Code
from connectrpc.errors import ConnectError

# Raise an error
raise ConnectError(Code.NOT_FOUND, f"Strategy not found: {strategy_id}")

# With details
raise ConnectError(
    Code.INVALID_ARGUMENT,
    "Validation failed",
    details=[{"field": "email", "error": "Invalid format"}]
)
```

### TypeScript Error Handling

```typescript
import { ConnectError } from '@connectrpc/connect';

try {
  const response = await authClient.login({ email, password });
} catch (err) {
  if (err instanceof ConnectError) {
    console.error('Code:', err.code);      // e.g., "unauthenticated"
    console.error('Message:', err.message); // e.g., "Invalid email or password"
  }
}
```

---

## Client Usage

### Frontend (TypeScript/Connect)

```typescript
// apps/web/src/services/grpc-client.ts
import { createClient } from '@connectrpc/connect';
import { createConnectTransport } from '@connectrpc/connect-web';
import { AuthService } from '../generated/proto/llamatrade/v1/auth_pb';

const transport = createConnectTransport({
  baseUrl: 'http://localhost:8810',
  useBinaryFormat: false,  // JSON for debugging
});

export const authClient = createClient(AuthService, transport);

// Usage
const response = await authClient.login({ email, password });
```

### Python (Service-to-Service)

```python
from llamatrade_grpc.clients import BacktestClient, TenantContext

async with BacktestClient("backtest:8830") as client:
    context = TenantContext(tenant_id="...", user_id="...", roles=["admin"])

    config = BacktestConfig(
        strategy_id="strat-123",
        start_date=datetime(2023, 1, 1),
        end_date=datetime(2024, 1, 1),
        initial_capital=Decimal("100000"),
        symbols=["AAPL", "GOOGL"],
    )

    run = await client.run_backtest(context, config)

    # Stream progress
    async for update in client.stream_progress(context, run.id):
        print(f"Progress: {update.progress_percent}%")
```

---

## Code Generation

### Regenerating Code

After modifying `.proto` files:

```bash
cd libs/proto
make generate   # or: buf generate
```

This generates:
- Python: `libs/grpc/llamatrade/v1/*_pb2.py`, `*_connect.py`
- TypeScript: `apps/web/src/generated/proto/llamatrade/v1/*_pb.ts`

### Generated Files

| File Pattern | Purpose |
|--------------|---------|
| `*_pb2.py` | Python protobuf message classes |
| `*_pb2.pyi` | Python type stubs (mypy) |
| `*_connect.py` | Python Connect ASGI apps and clients |
| `*_pb2_grpc.py` | Legacy gRPC stubs (service-to-service) |
| `*_pb.ts` | TypeScript message types and service definitions |

### Naming Convention

- `_pb2` = "protocol buffer 2" (Python historical convention)
- `_pb` = "protocol buffer" (TypeScript)
- `_connect` = Connect protocol wrappers
