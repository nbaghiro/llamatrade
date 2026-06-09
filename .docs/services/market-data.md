# Market Data Service

The market data service is the platform's data aggregation layer: it provides real-time and historical market data to the frontend and to other backend services. All Alpaca access goes through the shared `llamatrade_alpaca` library (REST + WebSocket); this service adds a Redis caching layer and a multi-client streaming fan-out, and re-exposes everything over gRPC/Connect.

---

## Overview

Responsibilities:

- **Historical data** — OHLCV bars (single and multi-symbol) with configurable timeframes, served from a Redis cache backed by Alpaca's Market Data REST API.
- **Snapshots & latest quotes** — current market state (latest trade/quote, minute/daily bars).
- **Real-time streaming** — fans out Alpaca's IEX WebSocket (trades/quotes/bars) to many gRPC stream clients via demand-based subscription aggregation.
- **Market status** — open/closed + next open/close via Alpaca's clock.
- **Caching** — Redis with per-data-type TTLs.
- **Data features** — historical quote/trade ticks, corporate actions with split/dividend adjustment, paginated bar windows, asset listing and tradability metadata, crypto and options coverage, and the Alpaca news feed.

This service is **read-only** with respect to Alpaca (market data + clock); it never places orders.

---

## Architecture & Data Flow

- **Transport:** FastAPI hosting a **Connect/gRPC** ASGI app (`MarketDataServiceASGIApplication`). There is **no REST/JSON API** — clients use the Connect protocol.
- **Port:** `8840` (published host→container `8840:8840` in dev; the dev compose runs uvicorn on `8840`). The container also exposes Prometheus metrics via `llamatrade_common.observability`.
- **Alpaca access:** via the shared `llamatrade_alpaca` library only — `MarketDataClient` (REST) and `MarketDataStreamClient` (WebSocket). This service does **not** contain its own Alpaca HTTP/WebSocket client.

```
Frontend / other services
        │  Connect (HTTP/1.1 + JSON)  /  gRPC streams
        ▼
┌──────────────────────────────────────────────────────────┐
│ MarketDataServicer (grpc/servicer.py)                      │
│   • unary RPCs   • streaming RPCs                          │
└───────────────┬───────────────────────┬───────────────────┘
                │                        │
   (cached path)│                        │(stream path)
                ▼                        ▼
   MarketDataService            StreamBridge ── StreamManager
   (services/…) + Redis          (streaming/bridge.py,           per-client
                │                  manager.py)                    asyncio.Queue
                ▼                        ▲
   llamatrade_alpaca.MarketDataClient    │ callbacks
   (REST: data.alpaca.markets/v2)        │
                                  llamatrade_alpaca.MarketDataStreamClient
                                  (wss://stream.data.alpaca.markets/v2/iex)
```

The gRPC servicer's unary handlers route through the Redis-cached `MarketDataService`, so the public gRPC path and direct `MarketDataService` callers share the same cache layer.

---

## Directory Structure

```
services/market-data/src/
├── main.py                       # FastAPI app, lifespan (cache + stream + bridge), /health
├── models.py                     # request/response schemas; re-exports shared models
├── cache.py                      # MarketDataCache + TTL constants
├── error_handlers.py             # maps llamatrade_alpaca errors → responses
├── metrics.py                    # Prometheus stream/cache metrics
├── grpc/servicer.py              # MarketDataServicer — all 8 RPCs
├── services/market_data_service.py  # cached business logic over MarketDataClient
└── streaming/
    ├── bridge.py                 # StreamBridge: Alpaca stream ↔ StreamManager, ref-counted subs
    └── manager.py                # StreamManager: per-client queues, broadcast, subscription tracking
```

The Alpaca REST client, WebSocket client, resilience (rate limiter/circuit breaker), and streaming models live in the shared **`llamatrade_alpaca`** library — **not** in this service.

---

## API Surface (gRPC/Connect — `MarketDataService`)

| RPC | Servicer method | Notes |
|---|---|---|
| `GetHistoricalBars` | `get_historical_bars` | single symbol; calls Alpaca `get_bars` through the cache |
| `GetMultiBars` | `get_multi_bars` | multi-symbol; Alpaca `get_multi_bars` through the cache |
| `GetSnapshot` | `get_snapshot` | Alpaca `get_snapshot` through the cache |
| `GetSnapshots` | `get_snapshots` | Alpaca `get_multi_snapshots` through the cache |
| `GetMarketStatus` | `get_market_status` | Alpaca Trading API `get_clock` |
| `StreamBars` | `stream_bars` | server-streaming; demand-driven Alpaca subscription |
| `StreamQuotes` | `stream_quotes` | server-streaming |
| `StreamTrades` | `stream_trades` | server-streaming |

The cached `MarketDataService` additionally exposes `get_bars`, `get_multi_bars`, `get_latest_bar`, `get_latest_quote`, `get_snapshot`, `get_multi_snapshots` (all cache-aware) for in-process callers.

---

## Caching (`cache.py`)

Redis, keyed per symbol/timeframe/range, with TTLs tuned to data volatility:

| Data | TTL constant | Value |
|---|---|---|
| Historical bars (immutable past) | `TTL_HISTORICAL_BARS` | 24 h |
| Today's bars (still forming) | `TTL_TODAY_BARS` | 5 min |
| Latest bar | `TTL_LATEST_BAR` | 2 min |
| Latest quote | `TTL_LATEST_QUOTE` | 10 s |
| Snapshot | `TTL_SNAPSHOT` | 15 s |

Bars TTL is chosen dynamically (`calculate_bars_ttl`) — historical vs. today.

---

## Streaming Architecture

1. **`MarketDataStreamClient`** (shared lib) holds one Alpaca IEX WebSocket; the service registers `on_trade/on_quote/on_bar` callbacks via `StreamBridge`.
2. **`StreamBridge`** (`streaming/bridge.py`) ref-counts symbol subscriptions across all clients and subscribes/unsubscribes to Alpaca on demand; it has a `BroadcastCircuitBreaker` to stop log-spam if broadcasts fail.
3. **`StreamManager`** (`streaming/manager.py`) holds a bounded `asyncio.Queue` per gRPC stream and broadcasts each message to subscribed clients (drops on full queue).
4. The servicer's `stream_*` RPCs register a client, subscribe symbols, and yield from the queue until disconnect.

Feed: **IEX** only (`/v2/iex`). SIP/paid feed is not used.

---

## Configuration

| Env var | Default | Purpose |
|---|---|---|
| `REDIS_URL` | `redis://localhost:6379` | cache backend (non-critical — service runs without it) |
| `ENVIRONMENT` | `development` | log format / behavior |
| `LOG_LEVEL` | `INFO` | logging |
| `GRPC_PORT` | `8840` (compose) | service port |
| `ALPACA_API_KEY` / `ALPACA_API_SECRET` | — | read by `llamatrade_alpaca` (env fallback) |

`/health` reports overall status plus non-critical `redis` and `alpaca_stream` dependency health.

---

## Dependencies

- **`llamatrade_alpaca`** — REST + WebSocket Alpaca access, models, errors, resilience.
- **`llamatrade_proto`** — generated `MarketDataService` Connect/gRPC code.
- **`llamatrade_common`** — observability (logging/metrics/tracing).
- **Redis** — cache (optional at runtime).
- **Consumers:** the frontend (charts/quotes) and the **backtest** service (historical bars over gRPC).

---

## Testing

`services/market-data/tests/`: `test_grpc_servicer.py`, `test_grpc_streaming.py`, `test_market_data_service.py`, `test_cache.py`, `test_stream_bridge.py`, `test_stream_manager.py`, `test_streaming_integration.py`, `test_alpaca_errors.py`, `test_auth_validation.py`, `test_metrics.py`, `test_health.py`.

---

## Data Features

- **Quote/trade history** — exposes Alpaca's historical quotes and trades alongside latest quote/trade and snapshots, supporting tick/quote history for fine-grained backtests and analytics.
- **Corporate actions & split/dividend adjustment** — surfaced for accurate long-range historical data and backtests.
- **Bar pagination beyond Alpaca's `limit`** — large historical windows (used by backtest) are paged transparently.
- **Asset listing / tradability metadata** — Alpaca `/assets` is exposed for symbol search and universe selection.
- **Additional asset classes** — covers IEX stocks, crypto symbols, and options.
- **News feed** — the Alpaca news API is surfaced for product use.

Rate limiting and circuit-breaking for Alpaca REST are provided by the shared `llamatrade_alpaca` library.
