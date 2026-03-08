# Market Data Service Architecture

The market data service is the central data aggregation layer that provides real-time and historical market data to all other services and the frontend. It connects to Alpaca Markets for data and implements caching, streaming, and resilience patterns.

---

## Overview

The market data service is responsible for:

- **Real-Time Streaming**: WebSocket connection to Alpaca for live bars, quotes, and trades
- **Historical Data**: REST API integration for OHLCV bars with configurable timeframes
- **Snapshots**: Current market state (latest trade, quote, daily bars)
- **Caching**: Multi-tier Redis caching with appropriate TTLs
- **Resilience**: Rate limiting, circuit breakers, and retry logic
- **Multi-Client Streaming**: Efficient subscription aggregation across gRPC clients

---

## Architecture Overview

### System Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         MARKET DATA SERVICE :8840                           │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                      FastAPI + Connect ASGI                         │    │
│  │   /health    MarketDataServiceASGIApplication                       │    │
│  └─────────────────────────────┬───────────────────────────────────────┘    │
│                                │                                            │
│  ┌─────────────────────────────┴───────────────────────────────────────┐    │
│  │                      gRPC Servicer                                  │    │
│  │                                                                     │    │
│  │  GetHistoricalBars ──► Fetch bars with caching                      │    │
│  │  GetMultiBars ────────► Batch bar fetching                          │    │
│  │  GetSnapshot ─────────► Current market state                        │    │
│  │  GetSnapshots ────────► Batch snapshots                             │    │
│  │  GetMarketStatus ─────► Market hours info                           │    │
│  │  StreamBars ──────────► Real-time bar updates                       │    │
│  │  StreamQuotes ────────► Real-time bid/ask updates                   │    │
│  │  StreamTrades ────────► Real-time tick data                         │    │
│  └─────────────────────────────┬───────────────────────────────────────┘    │
│                                │                                            │
│  ┌─────────────────────────────┴───────────────────────────────────────┐    │
│  │                      Service Layer                                  │    │
│  │                                                                     │    │
│  │  MarketDataService ──► Business logic + caching                     │    │
│  │  AlpacaClient ───────► REST API client                              │    │
│  │  RedisCache ─────────► Multi-tier caching                           │    │
│  │  Resilience ─────────► Rate limiter + circuit breaker               │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                      Streaming Layer                                │    │
│  │                                                                     │    │
│  │  AlpacaStreamClient ──► WebSocket connection to Alpaca              │    │
│  │  StreamBridge ────────► Subscription aggregation                    │    │
│  │  StreamManager ───────► Client connection management                │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                             │
└─────────────────────────────────┬───────────────────────────────────────────┘
                                  │
        ┌─────────────────────────┼─────────────────────────┐
        ▼                         ▼                         ▼
   ┌─────────────┐        ┌─────────────┐           ┌─────────────┐
   │   Alpaca    │        │    Redis    │           │  Consumers  │
   │  REST API   │        │    Cache    │           │             │
   │  WebSocket  │        │  (Optional) │           │  Backtest   │
   └─────────────┘        └─────────────┘           │  Trading    │
                                                    │  Portfolio  │
                                                    │  Frontend   │
                                                    └─────────────┘
```

### Streaming Data Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         STREAMING ARCHITECTURE                              │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌───────────────────────────────────────────────────────────────────┐      │
│  │                    Alpaca WebSocket                               │      │
│  │         wss://stream.data.alpaca.markets/v2/iex                   │      │
│  │                                                                   │      │
│  │   Sends: [{"T":"b","S":"AAPL","o":185.0,"h":186.0,...}]           │      │
│  └───────────────────────────────┬───────────────────────────────────┘      │
│                                  │                                          │
│                                  ▼                                          │
│  ┌───────────────────────────────────────────────────────────────────┐      │
│  │                  AlpacaStreamClient                               │      │
│  │                                                                   │      │
│  │   • Maintains authenticated WebSocket connection                  │      │
│  │   • Parses JSON → TradeData / QuoteData / BarData                 │      │
│  │   • Calls registered callbacks (on_trade, on_quote, on_bar)       │      │
│  │   • Auto-reconnects with exponential backoff                      │      │
│  └───────────────────────────────┬───────────────────────────────────┘      │
│                                  │                                          │
│                                  ▼                                          │
│  ┌───────────────────────────────────────────────────────────────────┐      │
│  │                     StreamBridge                                  │      │
│  │                                                                   │      │
│  │   • Reference-counts subscriptions across all clients             │      │
│  │   • Only subscribes to Alpaca when first client needs symbol      │      │
│  │   • Only unsubscribes when last client disconnects                │      │
│  │   • Routes data to StreamManager for broadcast                    │      │
│  └───────────────────────────────┬───────────────────────────────────┘      │
│                                  │                                          │
│                                  ▼                                          │
│  ┌───────────────────────────────────────────────────────────────────┐      │
│  │                    StreamManager                                  │      │
│  │                                                                   │      │
│  │   • Maps client_id → asyncio.Queue                                │      │
│  │   • Tracks symbol subscriptions per client                        │      │
│  │   • Broadcasts messages to subscribed clients' queues             │      │
│  │   • Handles connect / disconnect / subscribe / unsubscribe        │      │
│  └───────────────────────────────┬───────────────────────────────────┘      │
│                                  │                                          │
│                    ┌─────────────┼─────────────┐                            │
│                    ▼             ▼             ▼                            │
│              ┌──────────┐  ┌──────────┐  ┌──────────┐                       │
│              │ Client 1 │  │ Client 2 │  │ Client 3 │                       │
│              │  Queue   │  │  Queue   │  │  Queue   │                       │
│              │ (AAPL)   │  │(AAPL,SPY)│  │  (SPY)   │                       │
│              └──────────┘  └──────────┘  └──────────┘                       │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Directory Structure

```
services/market-data/
├── src/
│   ├── main.py                     # FastAPI app, lifespan, health check
│   ├── models.py                   # Pydantic schemas, exceptions
│   ├── cache.py                    # Redis caching layer
│   ├── error_handlers.py           # Global exception handlers
│   ├── resilience.py               # Rate limiting, circuit breaker, retry
│   ├── services/
│   │   └── market_data_service.py  # Service layer with caching logic
│   ├── alpaca/
│   │   └── client.py               # Alpaca REST API client
│   ├── grpc/
│   │   └── servicer.py             # gRPC/Connect service implementation
│   └── streaming/
│       ├── manager.py              # StreamManager - client management
│       ├── alpaca_stream.py        # AlpacaStreamClient - WebSocket
│       └── bridge.py               # StreamBridge - subscription aggregation
└── tests/
    └── test_*.py                   # Comprehensive test suite
```

---

## Core Components

| Component              | File                              | Responsibility                          |
| ---------------------- | --------------------------------- | --------------------------------------- |
| **MarketDataServicer** | `grpc/servicer.py`                | gRPC endpoint implementations           |
| **MarketDataService**  | `services/market_data_service.py` | Business logic, caching                 |
| **AlpacaClient**       | `alpaca/client.py`                | REST API for historical data            |
| **AlpacaStreamClient** | `streaming/alpaca_stream.py`      | WebSocket for real-time data            |
| **StreamManager**      | `streaming/manager.py`            | Client connection/subscription tracking |
| **StreamBridge**       | `streaming/bridge.py`             | Alpaca ↔ StreamManager routing          |
| **RedisCache**         | `cache.py`                        | Multi-tier caching                      |
| **Resilience**         | `resilience.py`                   | Rate limiter, circuit breaker           |

---

## RPC Endpoints

### Streaming RPCs (Server-Side Streaming)

| RPC            | Request               | Response       | Description                 |
| -------------- | --------------------- | -------------- | --------------------------- |
| `StreamBars`   | `StreamBarsRequest`   | `stream Bar`   | Real-time OHLCV bar updates |
| `StreamQuotes` | `StreamQuotesRequest` | `stream Quote` | Real-time bid/ask updates   |
| `StreamTrades` | `StreamTradesRequest` | `stream Trade` | Real-time trade ticks       |

**Streaming Flow:**

1. Client sends request with symbol list
2. StreamManager registers client with an asyncio.Queue
3. StreamBridge forwards Alpaca messages to client's queue
4. Server yields messages until client disconnects

### Historical Data RPCs

| RPC                 | Request                    | Response                    | Description               |
| ------------------- | -------------------------- | --------------------------- | ------------------------- |
| `GetHistoricalBars` | `GetHistoricalBarsRequest` | `GetHistoricalBarsResponse` | Bars for single symbol    |
| `GetMultiBars`      | `GetMultiBarsRequest`      | `GetMultiBarsResponse`      | Bars for multiple symbols |

**Parameters:**

- `symbol(s)`: Stock ticker(s)
- `timeframe`: 1Min, 5Min, 15Min, 30Min, 1Hour, 4Hour, 1Day, 1Week
- `start`: Start datetime
- `end`: End datetime (optional, defaults to now)
- `limit`: Max bars to return (1-10000, default 1000)

### Snapshot RPCs

| RPC            | Request               | Response               | Description                  |
| -------------- | --------------------- | ---------------------- | ---------------------------- |
| `GetSnapshot`  | `GetSnapshotRequest`  | `Snapshot`             | Current state for one symbol |
| `GetSnapshots` | `GetSnapshotsRequest` | `GetSnapshotsResponse` | Batch snapshots              |

**Snapshot Contents:**

- `latest_trade`: Most recent trade
- `latest_quote`: Current bid/ask
- `minute_bar`: Latest 1-minute bar
- `daily_bar`: Current day's bar
- `prev_daily_bar`: Previous day's bar

### Market Info RPC

| RPC               | Request                  | Response                  | Description               |
| ----------------- | ------------------------ | ------------------------- | ------------------------- |
| `GetMarketStatus` | `GetMarketStatusRequest` | `GetMarketStatusResponse` | Market open/closed status |

---

## Caching Strategy

### Redis Cache Tiers

| Data Type       | Key Pattern                               | TTL        | Rationale           |
| --------------- | ----------------------------------------- | ---------- | ------------------- |
| Historical bars | `market:bars:{symbol}:{tf}:{start}:{end}` | 24 hours   | Immutable past data |
| Today's bars    | Same pattern (end ≥ today)                | 5 minutes  | Still updating      |
| Latest bar      | `market:bar:latest:{symbol}`              | 2 minutes  | Fast lookups        |
| Latest quote    | `market:quote:{symbol}`                   | 10 seconds | Near real-time      |
| Snapshot        | `market:snapshot:{symbol}`                | 15 seconds | Current state       |

### TTL Constants

```python
TTL_HISTORICAL_BARS = 24 * 60 * 60  # 24 hours
TTL_TODAY_BARS = 5 * 60              # 5 minutes
TTL_LATEST_BAR = 2 * 60              # 2 minutes
TTL_LATEST_QUOTE = 10                # 10 seconds
TTL_SNAPSHOT = 15                    # 15 seconds
```

### Cache Behavior

- **Graceful Degradation**: Service continues if Redis unavailable
- **Serialization**: Pydantic `model_dump_json()` / `model_validate_json()`
- **Cache-Aside Pattern**: Check cache → fetch from Alpaca → store in cache

---

## External Integrations

### Alpaca REST API

**Base URLs:**

- Live: `https://data.alpaca.markets/v2`
- Paper: `https://data.sandbox.alpaca.markets/v2`

**Authentication:**

```
APCA-API-KEY-ID: <api_key>
APCA-API-SECRET-KEY: <api_secret>
```

**Endpoints Used:**

| Method | Endpoint                         | Purpose                      |
| ------ | -------------------------------- | ---------------------------- |
| `GET`  | `/stocks/{symbol}/bars`          | Historical bars for symbol   |
| `GET`  | `/stocks/bars`                   | Multi-symbol historical bars |
| `GET`  | `/stocks/{symbol}/bars/latest`   | Latest bar                   |
| `GET`  | `/stocks/{symbol}/quotes/latest` | Latest quote                 |
| `GET`  | `/stocks/{symbol}/snapshot`      | Full snapshot                |
| `GET`  | `/stocks/snapshots`              | Multi-symbol snapshots       |

### Alpaca WebSocket

**Endpoints:**

- Live: `wss://stream.data.alpaca.markets/v2/iex`
- Paper: `wss://stream.data.sandbox.alpaca.markets/v2/iex`

**Authentication Flow:**

1. Connect to WebSocket
2. Receive welcome message: `[{"T":"success","msg":"connected"}]`
3. Send auth: `{"action":"auth","key":"...","secret":"..."}`
4. Receive confirmation: `[{"T":"success","msg":"authenticated"}]`
5. Subscribe: `{"action":"subscribe","bars":["AAPL"],"quotes":["SPY"]}`

**Message Types:**

| Type  | Field `T` | Description                  |
| ----- | --------- | ---------------------------- |
| Trade | `t`       | Individual trade tick        |
| Quote | `q`       | Bid/ask update               |
| Bar   | `b`       | OHLCV bar (1-min aggregated) |

**Bar Message Example:**

```json
[
  {
    "T": "b",
    "S": "AAPL",
    "o": 185.0,
    "h": 186.5,
    "l": 184.75,
    "c": 185.5,
    "v": 1234567,
    "t": "2024-01-15T14:30:00Z",
    "n": 5432,
    "vw": 185.25
  }
]
```

**Reconnection:**

- Max attempts: 10
- Backoff: Exponential (5s, 10s, 20s, 40s, ...)
- On reconnect: Re-authenticate and re-subscribe to all symbols

---

## Internal Service Connections

### Services That Call Market-Data

| Service       | Use Case                       | Method                              |
| ------------- | ------------------------------ | ----------------------------------- |
| **Backtest**  | Historical bars for simulation | `GetHistoricalBars`, `GetMultiBars` |
| **Trading**   | Current prices for risk checks | `GetSnapshot`, `GetSnapshots`       |
| **Portfolio** | Position valuation             | `GetSnapshots`                      |
| **Strategy**  | Indicator calculations         | `GetHistoricalBars`                 |
| **Frontend**  | Charts, real-time updates      | All RPCs including streaming        |

### Client Usage Example

```python
from llamatrade_proto.clients import MarketDataClient

async with MarketDataClient("market-data:8840") as client:
    # Historical bars
    bars = await client.get_historical_bars(
        symbol="AAPL",
        start=datetime(2024, 1, 1),
        end=datetime(2024, 1, 31),
        timeframe="1Day"
    )

    # Snapshot
    snapshot = await client.get_snapshot("AAPL")
    print(f"Latest price: {snapshot.latest_trade.price}")

    # Stream real-time bars
    async for bar in client.stream_bars(["AAPL", "GOOGL"]):
        print(f"{bar.symbol}: {bar.close}")
```

---

## Data Models

### Bar (OHLCV)

```python
class Bar(BaseModel):
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int
    vwap: float | None = None        # Volume-weighted average price
    trade_count: int | None = None
```

### Quote (Bid/Ask)

```python
class Quote(BaseModel):
    symbol: str
    bid_price: float
    bid_size: int
    ask_price: float
    ask_size: int
    timestamp: datetime
```

### Trade (Tick)

```python
class Trade(BaseModel):
    symbol: str
    price: float
    size: int
    timestamp: datetime
    exchange: str | None = None
```

### Snapshot (Current State)

```python
class Snapshot(BaseModel):
    symbol: str
    latest_trade: Trade | None = None
    latest_quote: Quote | None = None
    minute_bar: Bar | None = None
    daily_bar: Bar | None = None
    prev_daily_bar: Bar | None = None
```

### Timeframe Enum

```python
class Timeframe(StrEnum):
    MINUTE_1 = "1Min"
    MINUTE_5 = "5Min"
    MINUTE_15 = "15Min"
    MINUTE_30 = "30Min"
    HOUR_1 = "1Hour"
    HOUR_4 = "4Hour"
    DAY_1 = "1Day"
    WEEK_1 = "1Week"
```

---

## Resilience Patterns

### Rate Limiter (Token Bucket)

```python
RateLimiter(
    capacity=200,           # Max tokens
    refill_rate=200/60      # Tokens per second (Alpaca free tier)
)
```

- Blocks requests until token available
- Prevents hitting Alpaca rate limits (200 req/min)

### Circuit Breaker

```
CLOSED ──(failures exceed threshold)──► OPEN
   ▲                                       │
   │                                       │ (timeout)
   │                                       ▼
   └────(success)──── HALF_OPEN ◄──────────┘
```

- **CLOSED**: Normal operation
- **OPEN**: All requests fail fast (no Alpaca calls)
- **HALF_OPEN**: Test with single request

### Retry with Exponential Backoff

```python
@retry_with_backoff(RetryConfig(
    max_attempts=3,
    initial_delay=1.0,
    max_delay=30.0,
    exponential_base=2.0,
    jitter=True  # Prevent thundering herd
))
async def get_bars(...):
    ...
```

---

## Error Handling

### Custom Exceptions

| Exception              | HTTP/gRPC Code         | When Raised           |
| ---------------------- | ---------------------- | --------------------- |
| `SymbolNotFoundError`  | 404 / NOT_FOUND        | Symbol doesn't exist  |
| `InvalidRequestError`  | 400 / INVALID_ARGUMENT | Bad parameters        |
| `AlpacaRateLimitError` | 503 / UNAVAILABLE      | Alpaca rate limit hit |
| `AlpacaServerError`    | 502 / UNAVAILABLE      | Alpaca 5xx error      |
| `CircuitOpenError`     | 503 / UNAVAILABLE      | Circuit breaker open  |

### Error Response Format

```json
{
  "error": "symbol_not_found",
  "message": "Symbol INVALID not found",
  "symbol": "INVALID"
}
```

---

## Configuration

### Environment Variables

```bash
# Required - Alpaca API credentials
ALPACA_API_KEY=your_api_key
ALPACA_API_SECRET=your_api_secret

# Optional - Redis (graceful degradation if unavailable)
REDIS_URL=redis://localhost:6379

# Optional - Service configuration
ALPACA_PAPER=true              # Use paper trading endpoints
ENVIRONMENT=development        # development | production
LOG_LEVEL=INFO                 # DEBUG | INFO | WARNING | ERROR
CORS_ORIGINS=http://localhost:8800,http://localhost:3000
```

### Service Port

- **Port**: 8840
- **Health Check**: `GET http://localhost:8840/health`

---

## Health Check

**Endpoint:** `GET /health`

```json
{
  "status": "healthy",
  "service": "market-data",
  "version": "0.1.0",
  "dependencies": {
    "redis": {
      "status": "healthy",
      "critical": false
    },
    "alpaca_stream": {
      "status": "healthy",
      "critical": false
    }
  }
}
```

**Dependency Status:**

- `healthy`: Connected and operational
- `unavailable`: Not connected (service continues in degraded mode)

---

## Startup Sequence

1. **Initialize Redis Cache** → `init_cache()` (logs warning if unavailable)
2. **Initialize Alpaca Stream** → `init_alpaca_stream()` (WebSocket connection)
3. **Initialize Stream Bridge** → `init_stream_bridge()` (routing layer)
4. **Mount Connect ASGI** → `MarketDataServiceASGIApplication(servicer)`

## Shutdown Sequence

1. Close stream bridge
2. Close Alpaca WebSocket
3. Close Alpaca REST client
4. Close Redis cache

---

## Complete Data Flow Example

**Scenario: Frontend requests real-time AAPL bars**

1. **Frontend** calls `marketDataClient.streamBars({ symbols: ["AAPL"] })`

2. **gRPC Servicer** receives `StreamBarsRequest`
   - Calls `stream_manager.connect(client_id)` → gets asyncio.Queue
   - Calls `stream_manager.subscribe(client_id, bars=["AAPL"])`

3. **StreamManager** tracks subscription
   - Adds client_id to `_bar_subs["AAPL"]`
   - Calls `on_subscribe` callback (set by StreamBridge)

4. **StreamBridge** handles new subscription
   - Increments `_bar_refs["AAPL"]` from 0 → 1
   - Calls `alpaca_stream.subscribe(bars=["AAPL"])`

5. **AlpacaStreamClient** sends to Alpaca
   - Sends: `{"action": "subscribe", "bars": ["AAPL"]}`
   - Alpaca confirms: `[{"T": "subscription", "bars": ["AAPL"]}]`

6. **Alpaca sends bar update**
   - `[{"T": "b", "S": "AAPL", "o": 185.0, "c": 185.5, ...}]`

7. **AlpacaStreamClient** parses and calls callback
   - Calls `on_bar("AAPL", {"open": 185.0, "close": 185.5, ...})`

8. **StreamBridge** routes to StreamManager
   - Calls `stream_manager.broadcast_bar("AAPL", bar_data)`

9. **StreamManager** broadcasts to subscribed clients
   - Finds all client_ids in `_bar_subs["AAPL"]`
   - Puts bar_data in each client's queue

10. **gRPC Servicer** yields from queue
    - `bar = await queue.get()`
    - Converts to protobuf `Bar` message
    - Yields to client

11. **Frontend** receives bar in stream callback

---

## Summary

The market data service provides a production-ready data layer with:

1. **Real-Time Streaming**: WebSocket connection with efficient subscription aggregation
2. **Historical Data**: REST API with intelligent caching
3. **Resilience**: Rate limiting, circuit breakers, retry with backoff
4. **Multi-Tier Caching**: Redis with TTLs appropriate to data freshness needs
5. **Graceful Degradation**: Continues operating if Redis or streaming unavailable
6. **Clean API**: gRPC/Connect protocol for type-safe communication
7. **Centralized Data**: Single source of truth for all market data in the system

Architecture separates concerns: Servicer (gRPC) → Service (business logic) → Alpaca Client (REST) / Stream (WebSocket) → Cache (Redis).

---

## Testing

### Test Structure

```
tests/
├── conftest.py                    # Shared fixtures (~6000 lines)
├── test_alpaca_errors.py          # Alpaca error handling tests
├── test_alpaca_stream.py          # WebSocket streaming tests (~21k lines)
├── test_auth_validation.py        # Authentication validation tests
├── test_cache.py                  # Redis cache tests (~14k lines)
├── test_grpc_servicer.py          # gRPC endpoint tests (~19k lines)
├── test_grpc_streaming.py         # gRPC streaming tests (~16k lines)
├── test_health.py                 # Health check tests
├── test_market_data_service.py    # Service layer tests (~11k lines)
├── test_metrics.py                # Prometheus metrics tests
├── test_stream_bridge.py          # Subscription aggregation tests
├── test_stream_manager.py         # Client management tests (~16k lines)
└── test_streaming_integration.py  # End-to-end streaming tests (~14k lines)
```

### Running Tests

```bash
# Run all tests
cd services/market-data && pytest

# Run with coverage
pytest --cov=src --cov-report=term-missing

# Run specific test file
pytest tests/test_cache.py

# Run specific test
pytest tests/test_cache.py::test_redis_get_bars_cached
```

### Key Test Scenarios

- **Historical bars**: Fetch, cache, pagination
- **Snapshots**: Latest trade, quote, daily bar
- **Streaming**: Bar/quote/trade subscription, multi-client
- **Caching**: Cache hit/miss, TTL expiration, invalidation
- **Resilience**: Rate limiting, circuit breaker, reconnection
- **Error handling**: Alpaca errors, timeout, authentication

---

## Current Implementation Status

> **Project Stage:** Production-Ready (95%)

### What's Real (Implemented) ✓

- [x] **gRPC/Connect Endpoints**: GetHistoricalBars, GetMultiBars, GetSnapshot, GetSnapshots, GetMarketStatus, StreamBars, StreamQuotes, StreamTrades
- [x] **Alpaca REST Client**: Full integration with authentication
- [x] **Alpaca WebSocket**: Real-time streaming with auto-reconnect
- [x] **Redis Caching**: Multi-tier caching with TTLs
- [x] **Stream Bridge**: Efficient subscription aggregation
- [x] **Stream Manager**: Multi-client connection handling
- [x] **Rate Limiting**: Token bucket rate limiter
- [x] **Circuit Breaker**: Prevent cascade failures
- [x] **Prometheus Metrics**: `/metrics` endpoint
- [x] **Health Check**: Standard `/health` endpoint

### What's Stubbed or Partial (TODO) ✗

- [ ] **Pre-2016 Data**: Only Alpaca data available (2016+)
- [ ] **Extended Hours**: Pre/post-market data not fully tested
- [ ] **International Markets**: US equities only

### Known Limitations

- **Data Range**: Alpaca data starts from 2016
- **Markets**: US equities only (no forex, crypto, international)
- **Extended Hours**: Available but not all features tested
- **Redis Optional**: Service works without Redis but no caching
