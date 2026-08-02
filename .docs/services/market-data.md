# Market Data Service

The market data service is the platform's data aggregation layer: it provides real-time and historical market data to the frontend and to other backend services. All Alpaca access goes through the shared `llamatrade_alpaca` library (REST + WebSocket). Historical reads are served **store-first** from a durable TimescaleDB bar store, gap-filled from Alpaca on demand; a Redis cache serves as the fallback path when the durable store is not configured. The service also runs an ingest worker (backfill, corporate actions, gap repair, live persistence) and a multi-client streaming fan-out, and re-exposes everything over gRPC/Connect.

---

## Overview

Responsibilities:

- **Historical data** — OHLCV bars (single and multi-symbol) with configurable timeframes, served **store-first** from a TimescaleDB bar store (`store/`) and gap-filled from Alpaca's Market Data REST API. A server-streaming variant (`StreamHistoricalBars`) feeds the backtest service.
- **Durable store + ingest** — closed bars are persisted to Timescale; an ingest worker (`ingest/`) backfills history, repairs interior gaps, applies corporate actions, and persists the live bar stream.
- **Snapshots & latest quotes** — current market state (latest trade/quote, minute/daily bars); falls back to the last stored daily bar when the live feed is unavailable.
- **Real-time streaming** — fans out Alpaca's IEX WebSocket (trades/quotes/bars) to many gRPC stream clients via demand-based subscription aggregation.
- **Market status** — open/closed + next open/close; prefers Alpaca's clock and falls back to a server-side NYSE calendar.
- **Assets** — asset reference/tradability metadata via `GetAssets`.
- **Caching** — a Redis cache with per-data-type TTLs serves reads when the durable store is not configured.

This service is **read-only** with respect to Alpaca (market data + clock); it never places orders.

---

## Architecture & Data Flow

- **Transport:** FastAPI hosting a **Connect/gRPC** ASGI app (`MarketDataServiceASGIApplication`). There is **no REST/JSON API** — clients use the Connect protocol.
- **Port:** `8840` (published host→container `8840:8840` in dev; the dev compose runs uvicorn on `8840`). The container also exposes Prometheus metrics.
- **Storage:** a durable TimescaleDB bar store (`store/`, `BarStore`) is the primary historical read path. A read selects stored bars, subtracts the covered interval to find gaps, fetches **only the gaps** from Alpaca, and writes the closed bars back. The store is active when `MARKET_DATA_DB_URL` is set; otherwise the service serves reads from the Redis-cache path.
- **Alpaca access:** via the shared `llamatrade_alpaca` library only — `MarketDataClient` (REST) and `MarketDataStreamClient` (WebSocket). This service does **not** contain its own Alpaca HTTP/WebSocket client.

```
          ┌────────────────────────────────────────┐
          │                CALLERS                 │
          ├────────────────────────────────────────┤
          │ frontend · backtest · trading sessions │
          └────────────────────────────────────────┘
                               │
                               ▼ Connect HTTP/1.1+JSON · gRPC streams
          ╭────────────────────────────────────────╮
          │ MarketDataServicer · grpc/servicer.py  │
          ├────────────────────────────────────────┤
          │ unary RPCs (cached)  ·  streaming RPCs │
          ╰────────────────────────────────────────╯
                               │
             ┌─────────────────┴─────────────────┐
             ▼ cached path                       ▼ stream path
╭────────────────────────╮      ╭─────────────────────────────────╮
│   MarketDataService    │      │          stream fan-out         │
├────────────────────────┤      ├─────────────────────────────────┤
│ store-first read-thru  │      │ StreamBridge → StreamManager    │
│ Timescale + gap-fill   │      │ ref-counted subs · per-client Q │
╰────────────────────────╯      ╰─────────────────────────────────╯
             │                                   │
             ▼                                   ▲ callbacks
╭─────────────────────────╮      ╭─────────────────────────────────╮
│    llamatrade_alpaca    │      │        llamatrade_alpaca        │
├─────────────────────────┤      ├─────────────────────────────────┤
│ MarketDataClient (REST) │      │ MarketDataStreamClient (WS)     │
│ data.alpaca.markets/v2  │      │ stream.data.alpaca.markets /iex │
╰─────────────────────────╯      ╰─────────────────────────────────╯
             ║                                   ║
             ▲                                   ▲
      Alpaca ═► REST                        Alpaca ═► WS IEX
```

The gRPC servicer's unary handlers route through `MarketDataService`, so the public gRPC path and direct in-process callers share the same store-first read logic (with the Redis-cache path as fallback).

In bus mode (`MARKET_DATA_BARS_FROM_BUS`), the serving pod does not open its own Alpaca WebSocket: a separate ingest role (`src/ingest/main.py`) publishes live bars onto the `lt.market.bars.1m` Kafka topic, and a `BusBridge` (`src/streaming/bus_bridge.py`) tails that topic and feeds the same `StreamManager` fan-out.

---

## Directory Structure

```
services/market-data/src/
├── main.py                       # FastAPI app, lifespan (store + cache + stream + bridge), /health
├── models.py                     # request/response schemas; re-exports shared models
├── cache.py                      # MarketDataCache + TTL constants (fallback cache path)
├── market_calendar.py            # server-side NYSE calendar (market-status fallback)
├── error_handlers.py             # maps llamatrade_alpaca errors → responses
├── metrics.py                    # Prometheus stream/cache + data-quality metrics
├── grpc/servicer.py              # MarketDataServicer — all 10 RPCs
├── services/
│   ├── market_data_service.py    # store-first read-through business logic
│   └── asset_service.py          # asset reference data (GetAssets)
├── store/                        # durable TimescaleDB bar store
│   ├── repository.py             # BarStore: select/upsert/covered_interval/missing_ranges
│   ├── models.py                 # BarRow, base-table & continuous-aggregate mappings
│   ├── intervals.py              # interval subtraction (gap detection)
│   └── migrate.py + migrations/  # store schema (hypertables, continuous aggregates)
├── ingest/                       # ingest worker
│   ├── backfill.py               # historical backfill
│   ├── gaps.py                   # interior gap repair
│   ├── corporate_actions.py      # split/dividend handling
│   └── stream.py                 # persist the live bar stream
└── streaming/
    ├── bridge.py                 # StreamBridge: Alpaca stream ↔ StreamManager, ref-counted subs
    ├── manager.py                # StreamManager: per-client queues, broadcast, subscription tracking
    ├── bar_events.py             # bar event models/plumbing
    └── bus_bridge.py             # bridge stream events onto the event bus
```

The Alpaca REST client, WebSocket client, resilience (rate limiter/circuit breaker), and streaming models live in the shared **`llamatrade_alpaca`** library — **not** in this service.

---

## API Surface (gRPC/Connect — `MarketDataService`) — 10 RPCs

| RPC | Servicer method | Notes |
|---|---|---|
| `GetHistoricalBars` | `get_historical_bars` | single symbol; store-first with Alpaca gap-fill |
| `GetMultiBars` | `get_multi_bars` | multi-symbol; per-symbol store-first read-through |
| `StreamHistoricalBars` | `stream_historical_bars` | server-streaming multi-symbol history in timestamp order; consumed by the backtest service |
| `GetSnapshot` | `get_snapshot` | Alpaca snapshot, falling back to the last stored daily bar |
| `GetSnapshots` | `get_snapshots` | multi-symbol snapshots; per-symbol store fallback |
| `GetAssets` | `get_assets` | asset reference/tradability metadata (`asset_service`) |
| `GetMarketStatus` | `get_market_status` | Alpaca `/v2/clock`, NYSE-calendar fallback |
| `StreamBars` | `stream_bars` | server-streaming; demand-driven Alpaca subscription |
| `StreamQuotes` | `stream_quotes` | server-streaming |
| `StreamTrades` | `stream_trades` | server-streaming |

The `MarketDataService` layer additionally exposes `get_bars`, `get_multi_bars`, `get_latest_bar`, `get_latest_quote`, `get_snapshot`, `get_multi_snapshots` (store-first, with the Redis-cache path as fallback) for in-process callers.

---

## Storage & Caching

### Durable store (`store/`) — primary historical read path

Closed bars are persisted to a TimescaleDB hypertable (`BarStore`). Reads are store-first: select stored bars for the range, compute the covered interval, subtract to find gaps, fetch **only the gaps** from Alpaca, write the closed bars back, and merge (de-duplicated by timestamp). Continuous aggregates answer coarser timeframes from finer base tables. The currently-forming bar is fetched for the response but never persisted. A failed gap fetch (missing credentials/outage) still serves the stored bars rather than failing the whole read.

The **daily bar base is split-adjusted**: the ingest (`ingest/backfill.py`, `ingest/gaps.py`, `ingest/corporate_actions.py`) fetches Alpaca daily bars with `adjustment="split"` — resolved through the single `ingest/config.py::adjustment_for(timeframe)` helper (daily = split-adjusted, intraday = raw). Each row's `adjustment` column records the adjustment applied, driving the corporate-action self-heal.

### Redis cache (`cache.py`) — read path when the store is not configured

When `MARKET_DATA_DB_URL` is unset, reads are served from Redis keyed per symbol/timeframe/range, with TTLs tuned to data volatility:

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
| `MARKET_DATA_DB_URL` | — | TimescaleDB store connection; when unset the service serves reads from the Redis-cache path |
| `REDIS_URL` | `redis://localhost:6379` | cache backend (non-critical — service runs without it) |
| `ENVIRONMENT` | `development` | log format / behavior |
| `LOG_LEVEL` | `INFO` | logging |
| `GRPC_PORT` | `8840` (compose) | service port |
| `ALPACA_API_KEY` / `ALPACA_API_SECRET` | — | read by `llamatrade_alpaca` (env fallback) |
| `KAFKA_BOOTSTRAP_SERVERS` | `localhost:9092` | bars topic transport (`llamatrade_events`) |
| `MARKET_DATA_BARS_FROM_BUS` | off | serve live bars from the Kafka bars topic (`BusBridge`) instead of a direct Alpaca stream |

`/health` reports overall status plus three non-critical checks: `redis` (cache backend), `kafka` (answered from the shared transport, or a running bus bridge, without opening a second broker connection), and `live_bars` (bus-bridge state in bus mode, otherwise Alpaca stream connectivity).

---

## Dependencies

- **`llamatrade_alpaca`** — REST + WebSocket Alpaca access, models, errors, resilience.
- **`llamatrade_proto`** — generated `MarketDataService` Connect/gRPC code.
- **`llamatrade_common`** — observability (logging/metrics/tracing).
- **TimescaleDB** — durable bar store + continuous aggregates (primary historical read path; `MARKET_DATA_DB_URL`).
- **Redis** — cache path when the store is not configured (optional at runtime).
- **Consumers:** the frontend (charts/quotes), the **backtest** service (historical bars over gRPC, via `StreamHistoricalBars`), and the **notification** service's price-alert market loop (tails the `lt.market.bars.1m` Kafka topic; leader-elected, one pod).

---

## Testing

`services/market-data/tests/`: `test_grpc_servicer.py`, `test_grpc_streaming.py`, `test_market_data_service.py`, `test_asset_service.py`, `test_cache.py`, `test_stream_bridge.py`, `test_stream_manager.py`, `test_streaming_integration.py`, `test_bus_bridge_supervision.py`, `test_alpaca_errors.py`, `test_auth_validation.py`, `test_metrics.py`, `test_health.py`, plus `unit/` and `integration/` subtrees and shared `fakes.py`.

---

## Data Features

- **Quote/trade history** — exposes Alpaca's historical quotes and trades alongside latest quote/trade and snapshots, supporting tick/quote history for fine-grained backtests and analytics.
- **Corporate actions & split/dividend adjustment** — surfaced for accurate long-range historical data and backtests.
- **Bar pagination beyond Alpaca's `limit`** — large historical windows (used by backtest) are paged transparently.
- **Asset listing / tradability metadata** — Alpaca `/assets` is exposed for symbol search and universe selection.

Rate limiting and circuit-breaking for Alpaca REST are provided by the shared `llamatrade_alpaca` library.
