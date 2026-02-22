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

async with MarketDataClient("market-data:50054") as client:
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

auth_client = AuthClient("auth:50051")

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

async with TradingClient("trading:50055") as client:
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

## Port Assignments

| Service | REST Port | gRPC Port |
|---------|-----------|-----------|
| Auth | 8001 | 50051 |
| Strategy | 8002 | 50052 |
| Backtest | 8003 | 50053 |
| Market Data | 8004 | 50054 |
| Trading | 8005 | 50055 |
| Portfolio | 8006 | 50056 |
| Notification | 8007 | 50057 |
| Billing | 8008 | 50058 |

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
