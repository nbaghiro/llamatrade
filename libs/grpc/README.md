# LlamaTrade gRPC Library

This library provides typed gRPC client wrappers and interceptors for inter-service communication in the LlamaTrade platform.

## Installation

```bash
pip install -e libs/grpc
```

## Generating Proto Code

Before using this library, you need to generate the Python code from proto files:

```bash
cd libs/proto
make generate
```

This requires the `buf` CLI to be installed:
```bash
brew install bufbuild/buf/buf
```

## Usage

### Market Data Client

```python
from llamatrade_grpc import MarketDataClient

async with MarketDataClient("market-data:8840") as client:
    # Fetch historical bars
    bars = await client.get_historical_bars(
        symbol="AAPL",
        start=datetime(2024, 1, 1),
        end=datetime(2024, 1, 31),
        timeframe="1D"
    )

    for bar in bars:
        print(f"{bar.timestamp}: O={bar.open} H={bar.high} L={bar.low} C={bar.close}")

    # Stream real-time bars
    async for bar in client.stream_bars(["AAPL", "GOOGL"]):
        print(f"{bar.symbol}: {bar.close}")
```

### Auth Client

```python
from llamatrade_grpc import AuthClient

auth_client = AuthClient("auth:8810")

# Validate a JWT token
result = await auth_client.validate_token(token)
if result.valid:
    print(f"User: {result.context.user_id}")
    print(f"Tenant: {result.context.tenant_id}")

# Validate an API key
result = await auth_client.validate_api_key(
    api_key,
    required_scopes=["read:orders"]
)
```

### Trading Client

```python
from llamatrade_grpc import TradingClient
from llamatrade_grpc.clients.trading import OrderSide, OrderType
from decimal import Decimal

async with TradingClient("trading:8850") as client:
    # Submit an order
    order = await client.submit_order(
        context=context,
        session_id="session-123",
        symbol="AAPL",
        side=OrderSide.BUY,
        quantity=Decimal("10"),
        order_type=OrderType.MARKET,
    )

    # Stream order updates
    async for update in client.stream_order_updates(context, session_id):
        print(f"Order {update.order.id}: {update.event_type}")
```

### Using Interceptors

```python
from llamatrade_grpc import AuthInterceptor, LoggingInterceptor

# Server-side auth interceptor
auth_interceptor = AuthInterceptor(
    auth_client,
    skip_methods=["/llamatrade.v1.AuthService/Login"]
)

# Logging interceptor
logging_interceptor = LoggingInterceptor(log_level=logging.INFO)

# Create server with interceptors
server = grpc.aio.server(interceptors=[logging_interceptor, auth_interceptor])
```

## Port Assignments (gRPC-only)

All services expose gRPC only. The API Gateway (Kong) handles gRPC-Web translation for browser clients.

| Service | gRPC Port |
|---------|-----------|
| Auth | 8810 |
| Strategy | 8820 |
| Backtest | 8830 |
| Market Data | 8840 |
| Trading | 8850 |
| Portfolio | 8860 |
| Notification | 8870 |
| Web (Frontend) | 8800 |
| Billing | 8880 |

**Note:** Billing also exposes HTTP port 8881 for Stripe webhooks (required by Stripe).

## Development

### Running Tests

```bash
pytest libs/grpc/tests
```

### Linting

```bash
ruff check libs/grpc
mypy libs/grpc
```
