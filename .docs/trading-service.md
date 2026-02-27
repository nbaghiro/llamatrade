# Trading Service Architecture

The trading service is the execution engine that connects user-defined strategies to real markets via Alpaca Markets. It handles everything from receiving real-time market data to executing orders with comprehensive risk controls.

## Table of Contents

1. [Overview](#overview)
2. [High-Level Architecture](#high-level-architecture)
3. [Core Components](#core-components)
4. [Session Lifecycle](#session-lifecycle)
5. [Strategy Runner](#strategy-runner)
6. [Order Execution Flow](#order-execution-flow)
7. [Risk Management](#risk-management)
8. [Real-Time Data Streaming](#real-time-data-streaming)
9. [Position & P&L Tracking](#position--pl-tracking)
10. [External Service Integrations](#external-service-integrations)
11. [Data Models](#data-models)
12. [API Endpoints](#api-endpoints)
13. [Complete Data Flow Example](#complete-data-flow-example)

---

## Overview

The trading service is responsible for:

- **Live Strategy Execution**: Running compiled strategies against real-time market data
- **Order Management**: Submitting, tracking, and syncing orders with Alpaca
- **Risk Controls**: Enforcing position limits, daily loss limits, and order validation
- **Position Tracking**: Maintaining local position records with P&L calculations
- **Session Management**: Starting, stopping, pausing trading sessions
- **Audit Logging**: Recording all trading events for compliance

```
┌───────────────────────────────────────────────────────────────────────┐
│                         TRADING SERVICE                               │
│                                                                       │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐   │
│  │   Orders    │  │  Sessions   │  │  Positions  │  │    Risk     │   │
│  │   Router    │  │   Router    │  │   Router    │  │   Manager   │   │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘   │
│         │                │                │                │          │
│         └────────────────┴────────────────┴────────────────┘          │
│                                   │                                   │
│                    ┌──────────────┴──────────────┐                    │
│                    │      Strategy Runner        │                    │
│                    │   (Real-time Execution)     │                    │
│                    └──────────────┬──────────────┘                    │
│                                   │                                   │
└───────────────────────────────────┼───────────────────────────────────┘
                                    │
              ┌─────────────────────┼─────────────────────┐
              │                     │                     │
              ▼                     ▼                     ▼
     ┌────────────────┐   ┌────────────────┐   ┌────────────────┐
     │ Alpaca Trading │   │  Market Data   │   │    Strategy    │
     │      API       │   │    Service     │   │    Service     │
     └────────────────┘   └────────────────┘   └────────────────┘
```

---

## High-Level Architecture

### Service Interactions

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              USER / WEB APP                                 │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      │ HTTP REST
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                              KONG API GATEWAY                               │
│                              (Authentication)                               │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                    ┌─────────────────┼─────────────────┐
                    │                 │                 │
                    ▼                 ▼                 ▼
           ┌───────────────┐ ┌───────────────┐ ┌───────────────┐
           │    Auth       │ │   Strategy    │ │   Trading     │◀── This doc
           │   Service     │ │   Service     │ │   Service     │
           └───────────────┘ └───────────────┘ └───────┬───────┘
                                      │                │
                                      │                │
                    ┌─────────────────┴────────────────┤
                    │                                  │
                    ▼                                  ▼
           ┌───────────────┐                 ┌───────────────┐
           │  Market Data  │                 │   Alpaca      │
           │   Service     │                 │   Markets     │
           └───────────────┘                 │   (Broker)    │
                    │                        └───────────────┘
                    │                                │
                    ▼                                │
           ┌───────────────┐                         │
           │   Alpaca      │◀────────────────────────┘
           │   Data API    │
           └───────────────┘
```

### Internal Component Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           TRADING SERVICE                                   │
│                                                                             │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │                         FastAPI Application                           │  │
│  │                            (main.py)                                  │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│                                    │                                        │
│           ┌────────────────────────┼────────────────────────┐               │
│           │                        │                        │               │
│           ▼                        ▼                        ▼               │
│  ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐          │
│  │  /orders        │    │  /sessions      │    │  /positions     │          │
│  │  Router         │    │  Router         │    │  Router         │          │
│  └────────┬────────┘    └────────┬────────┘    └────────┬────────┘          │
│           │                      │                      │                   │
│           ▼                      ▼                      ▼                   │
│  ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐          │
│  │ OrderExecutor   │    │ LiveSession     │    │ Position        │          │
│  │                 │    │ Service         │    │ Service         │          │
│  └────────┬────────┘    └────────┬────────┘    └─────────────────┘          │
│           │                      │                                          │
│           │              ┌───────┴───────┐                                  │
│           │              │               │                                  │
│           │              ▼               ▼                                  │
│           │     ┌──────────────┐ ┌──────────────┐                           │
│           │     │ Runner       │ │ Strategy     │                           │
│           │     │ Manager      │ │ Adapter      │                           │
│           │     └──────┬───────┘ └──────────────┘                           │
│           │            │                                                    │
│           │            ▼                                                    │
│           │     ┌──────────────┐                                            │
│           │     │ Strategy     │                                            │
│           └────▶│ Runner       │◀── Per-session instance                    │
│                 └──────┬───────┘                                            │
│                        │                                                    │
│           ┌────────────┼────────────┐                                       │
│           │            │            │                                       │
│           ▼            ▼            ▼                                       │
│  ┌─────────────┐ ┌──────────┐ ┌──────────┐                                  │
│  │ Bar Stream  │ │ Risk     │ │ Audit    │                                  │
│  │ (WebSocket) │ │ Manager  │ │ Service  │                                  │
│  └─────────────┘ └──────────┘ └──────────┘                                  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Core Components

### Directory Structure

```
services/trading/
├── src/
│   ├── main.py                    # FastAPI app, routers, health check
│   ├── models.py                  # Pydantic schemas (Order, Session, Position)
│   ├── alpaca_client.py           # Alpaca REST API client
│   │
│   ├── routers/
│   │   ├── orders.py              # Order CRUD endpoints
│   │   ├── sessions.py            # Session lifecycle endpoints
│   │   └── positions.py           # Position tracking endpoints
│   │
│   ├── services/
│   │   ├── session_service.py     # Session CRUD, P&L calculation
│   │   ├── live_session_service.py # Session + Runner lifecycle
│   │   ├── position_service.py    # Local position tracking
│   │   ├── audit_service.py       # Event logging for compliance
│   │   └── alert_service.py       # Webhook notifications
│   │
│   ├── runner/
│   │   ├── runner.py              # StrategyRunner, RunnerManager
│   │   └── bar_stream.py          # AlpacaBarStream (WebSocket)
│   │
│   ├── executor/
│   │   └── order_executor.py      # Order submission, Alpaca sync
│   │
│   ├── risk/
│   │   └── risk_manager.py        # Risk checks, limits, daily P&L
│   │
│   ├── clients/
│   │   └── market_data.py         # HTTP client for market-data service
│   │
│   └── compiler_adapter.py        # Bridges CompiledStrategy ↔ Runner
│
└── tests/
    ├── test_market_data_client.py
    ├── test_position_service.py
    └── ...
```

### Component Responsibilities

| Component               | File                               | Responsibility                                          |
| ----------------------- | ---------------------------------- | ------------------------------------------------------- |
| **OrderExecutor**       | `executor/order_executor.py`       | Submit orders, sync with Alpaca, manage order lifecycle |
| **RiskManager**         | `risk/risk_manager.py`             | Validate orders, enforce limits, track daily P&L        |
| **SessionService**      | `services/session_service.py`      | CRUD for trading sessions, P&L aggregation              |
| **LiveSessionService**  | `services/live_session_service.py` | Session + Runner lifecycle integration                  |
| **PositionService**     | `services/position_service.py`     | Local position tracking, P&L calculation                |
| **StrategyRunner**      | `runner/runner.py`                 | Real-time strategy execution loop                       |
| **RunnerManager**       | `runner/runner.py`                 | Manage multiple concurrent runners                      |
| **AlpacaBarStream**     | `runner/bar_stream.py`             | WebSocket connection for real-time bars                 |
| **StrategyAdapter**     | `compiler_adapter.py`              | Adapt CompiledStrategy to runner interface              |
| **AlpacaTradingClient** | `alpaca_client.py`                 | REST client for Alpaca Trading API                      |
| **MarketDataClient**    | `clients/market_data.py`           | HTTP client for market-data service                     |
| **AuditService**        | `services/audit_service.py`        | Log all trading events                                  |
| **AlertService**        | `services/alert_service.py`        | Send webhook notifications                              |

---

## Session Lifecycle

A trading session represents a single strategy running against the market. Sessions have a defined lifecycle:

```
                    ┌─────────────────┐
                    │                 │
                    │     CREATED     │
                    │                 │
                    └────────┬────────┘
                             │
                             │ start_session()
                             ▼
                    ┌─────────────────┐
         ┌──────────│                 │─────────┐
         │          │     ACTIVE      │         │
         │          │                 │         │
         │          └────────┬────────┘         │
         │                   │                  │
         │ pause_session()   │                  │ error
         ▼                   │                  ▼
┌─────────────────┐          │         ┌─────────────────┐
│                 │          │         │                 │
│     PAUSED      │          │         │      ERROR      │
│                 │          │         │                 │
└────────┬────────┘          │         └─────────────────┘
         │                   │
         │ resume_session()  │
         │                   │
         └────────►──────────┤
                             │
                             │ stop_session()
                             ▼
                    ┌─────────────────┐
                    │                 │
                    │     STOPPED     │
                    │                 │
                    └─────────────────┘
```

### Session Start Flow

```
┌────────────────────────────────────────────────────────────────────────────┐
│                         POST /sessions (Start)                             │
└────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────────┐
│                      LiveSessionService.start_session()                    │
│                                                                            │
│  1. Validate request (strategy exists, credentials valid)                  │
│  2. Create TradingSession record in database (status=ACTIVE)               │
│  3. Load strategy S-expression from StrategyVersion                        │
│  4. Create StrategyAdapter (parse + compile strategy)                      │
│  5. Create AlpacaBarStream with API credentials                            │
│  6. Configure RunnerConfig (symbols, timeframe, warmup_bars)               │
│  7. Start StrategyRunner via RunnerManager                                 │
│  8. Return SessionResponse                                                 │
│                                                                            │
└────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────────┐
│                         StrategyRunner (Background)                        │
│                                                                            │
│  • Syncs equity from Alpaca account                                        │
│  • Connects to bar stream WebSocket                                        │
│  • Subscribes to configured symbols                                        │
│  • Enters main loop processing bars                                        │
│                                                                            │
└────────────────────────────────────────────────────────────────────────────┘
```

### Session Stop Flow

```
┌────────────────────────────────────────────────────────────────────────────┐
│                      POST /sessions/{id}/stop                              │
└────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────────┐
│                      LiveSessionService.stop_session()                     │
│                                                                            │
│  1. Stop StrategyRunner via RunnerManager                                  │
│     • Set _running = False                                                 │
│     • Disconnect bar stream                                                │
│     • Cancel background tasks                                              │
│  2. Update TradingSession (status=STOPPED, stopped_at=now)                 │
│  3. Return SessionResponse with final P&L                                  │
│                                                                            │
└────────────────────────────────────────────────────────────────────────────┘
```

---

## Strategy Runner

The StrategyRunner is the core execution engine that processes market data and generates trading signals.

### Runner Architecture

```
┌────────────────────────────────────────────────────────────────────────────┐
│                            STRATEGY RUNNER                                 │
│                                                                            │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                         Configuration                               │   │
│  │  • tenant_id        • deployment_id (session_id)                    │   │
│  │  • strategy_id      • symbols: ["AAPL", "GOOGL", ...]               │   │
│  │  • timeframe: "1Min"  • warmup_bars: 50                             │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                            │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                            State                                    │   │
│  │  • _running: bool           • _paused: bool                         │   │
│  │  • _equity: float           • _positions: dict[symbol, Position]    │   │
│  │  • _bar_history: dict[symbol, list[BarData]]                        │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                            │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                         Dependencies                                │   │
│  │  • strategy_fn: StrategyAdapter    • bar_stream: AlpacaBarStream    │   │
│  │  • order_executor: OrderExecutor   • risk_manager: RiskManager      │   │
│  │  • alpaca_client: AlpacaTradingClient                               │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                            │
└────────────────────────────────────────────────────────────────────────────┘
```

### Main Execution Loop

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        StrategyRunner.start()                               │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
                    ┌───────────────────────────────┐
                    │   Sync equity from Alpaca     │
                    │   _equity = account.equity    │
                    └───────────────┬───────────────┘
                                    │
                                    ▼
                    ┌───────────────────────────────┐
                    │   Connect to bar stream       │
                    │   bar_stream.connect()        │
                    └───────────────┬───────────────┘
                                    │
                                    ▼
                    ┌───────────────────────────────┐
                    │   Subscribe to symbols        │
                    │   bar_stream.subscribe(...)   │
                    └───────────────┬───────────────┘
                                    │
                                    ▼
                    ┌───────────────────────────────┐
                    │   Start equity sync loop      │
                    │   (every 60 seconds)          │
                    └───────────────┬───────────────┘
                                    │
                                    ▼
              ┌─────────────────────────────────────────────┐
              │                                             │
              │        MAIN LOOP: Process Bars              │
              │                                             │
              │    async for bar in bar_stream.stream():    │
              │        if _paused: continue                 │
              │        signal = _process_bar(bar)           │
              │        if signal:                           │
              │            _process_signal(signal)          │
              │                                             │
              └─────────────────────────────────────────────┘
```

### Bar Processing Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        _process_bar(bar: BarData)                           │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
                    ┌───────────────────────────────┐
                    │   Add bar to symbol history   │
                    │   _bar_history[symbol].append │
                    └───────────────┬───────────────┘
                                    │
                                    ▼
                    ┌───────────────────────────────┐
                    │   Trim history to max size    │
                    │   (warmup_bars + 100)         │
                    └───────────────┬───────────────┘
                                    │
                                    ▼
                    ┌───────────────────────────────┐
                    │   Check warmup complete?      │
                    │   len(history) >= warmup_bars │
                    └───────────────┬───────────────┘
                                    │
                         ┌──────────┴──────────┐
                         │ No                  │ Yes
                         ▼                     ▼
                ┌─────────────────┐   ┌─────────────────────────┐
                │  Return None    │   │  Call strategy function │
                │  (still warming │   │                         │
                │   up)           │   │  strategy_fn(           │
                └─────────────────┘   │    symbol,              │
                                      │    bars,                │
                                      │    position,            │
                                      │    equity               │
                                      │  ) -> Signal | None     │
                                      └───────────┬─────────────┘
                                                  │
                                                  ▼
                                      ┌─────────────────────────┐
                                      │   Return Signal or None │
                                      └─────────────────────────┘
```

### Signal Processing Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                      _process_signal(signal: Signal)                        │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
                    ┌───────────────────────────────┐
                    │   Create OrderCreate from     │
                    │   signal (symbol, side, qty)  │
                    └───────────────┬───────────────┘
                                    │
                                    ▼
                    ┌───────────────────────────────┐
                    │   risk_manager.check_order()  │
                    └───────────────┬───────────────┘
                                    │
                         ┌──────────┴──────────┐
                         │                     │
                    Failed                  Passed
                         │                     │
                         ▼                     ▼
            ┌─────────────────────┐  ┌─────────────────────────┐
            │  Log rejection      │  │  order_executor.        │
            │  Update metrics     │  │    submit_order()       │
            │  (orders_rejected)  │  └───────────┬─────────────┘
            └─────────────────────┘              │
                                                 ▼
                                    ┌─────────────────────────┐
                                    │  _update_position()     │
                                    │  Update internal        │
                                    │  position tracking      │
                                    └───────────┬─────────────┘
                                                │
                                                ▼
                                    ┌─────────────────────────┐
                                    │  Update metrics         │
                                    │  (signals_generated,    │
                                    │   orders_submitted)     │
                                    └─────────────────────────┘
```

### Runner Manager

The RunnerManager maintains a registry of active runners:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                            RUNNER MANAGER                                   │
│                                                                             │
│  active_runners: dict[UUID, StrategyRunner]                                 │
│  _tasks: dict[UUID, asyncio.Task]                                           │
│                                                                             │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │  Session A (UUID-1)                                                  │   │
│  │  ├─ StrategyRunner instance                                          │   │
│  │  └─ asyncio.Task (background)                                        │   │
│  ├──────────────────────────────────────────────────────────────────────┤   │
│  │  Session B (UUID-2)                                                  │   │
│  │  ├─ StrategyRunner instance                                          │   │
│  │  └─ asyncio.Task (background)                                        │   │
│  ├──────────────────────────────────────────────────────────────────────┤   │
│  │  Session C (UUID-3)                                                  │   │
│  │  ├─ StrategyRunner instance                                          │   │
│  │  └─ asyncio.Task (background)                                        │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  Methods:                                                                   │
│  • start_runner(config, strategy_fn, bar_stream, ...) -> UUID               │
│  • stop_runner(deployment_id) -> None                                       │
│  • stop_all() -> None                                                       │
│  • get_runner(deployment_id) -> StrategyRunner | None                       │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Order Execution Flow

### Complete Order Lifecycle

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           ORDER LIFECYCLE                                   │
│                                                                             │
│    ┌──────────┐    ┌───────────┐    ┌──────────┐    ┌──────────┐            │
│    │ PENDING  │───▶│ SUBMITTED │───▶│ ACCEPTED │───▶│  FILLED  │            │
│    └──────────┘    └───────────┘    └──────────┘    └──────────┘            │
│         │                │               │               │                  │
│         │                │               │               │                  │
│         ▼                ▼               ▼               │                  │
│    ┌──────────┐    ┌───────────┐    ┌──────────┐         │                  │
│    │ REJECTED │    │ CANCELLED │    │ PARTIAL  │─────────┘                  │
│    └──────────┘    └───────────┘    └──────────┘                            │
│                                          │                                  │
│                                          ▼                                  │
│                                     ┌──────────┐                            │
│                                     │  FILLED  │                            │
│                                     └──────────┘                            │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Order Submission Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│              Signal / API Request                                           │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                      OrderExecutor.submit_order()                           │
│                                                                             │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │  Step 1: Risk Validation                                             │   │
│  │                                                                      │   │
│  │  risk_manager.check_order(order, tenant_id, session_id)              │   │
│  │                                                                      │   │
│  │  Checks:                                                             │   │
│  │  • Max order value ($10,000 default)                                 │   │
│  │  • Allowed symbols (whitelist)                                       │   │
│  │  • Max position size ($50,000 default)                               │   │
│  │  • Daily loss limit ($5,000 default)                                 │   │
│  │  • Order rate limit (10/minute)                                      │   │
│  │                                                                      │   │
│  │  If ANY check fails → raise ValueError with violations               │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                    │                                        │
│                                    ▼                                        │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │  Step 2: Create Database Record                                      │   │
│  │                                                                      │   │
│  │  Order(                                                              │   │
│  │      tenant_id=...,                                                  │   │
│  │      session_id=...,                                                 │   │
│  │      symbol=order.symbol,                                            │   │
│  │      side=order.side,                                                │   │
│  │      qty=order.qty,                                                  │   │
│  │      status=OrderStatus.PENDING                                      │   │
│  │  )                                                                   │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                    │                                        │
│                                    ▼                                        │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │  Step 3: Submit to Alpaca                                            │   │
│  │                                                                      │   │
│  │  alpaca_client.submit_order(                                         │   │
│  │      symbol="AAPL",                                                  │   │
│  │      qty=10,                                                         │   │
│  │      side="buy",                                                     │   │
│  │      type="market",                                                  │   │
│  │      time_in_force="day"                                             │   │
│  │  )                                                                   │   │
│  │                                                                      │   │
│  │  POST https://paper-api.alpaca.markets/v2/orders                     │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                    │                                        │
│                                    ▼                                        │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │  Step 4: Update Database                                             │   │
│  │                                                                      │   │
│  │  order.alpaca_order_id = response["id"]                              │   │
│  │  order.status = map_status(response["status"])                       │   │
│  │  order.submitted_at = now()                                          │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                    │                                        │
│                                    ▼                                        │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │  Step 5: Return Response                                             │   │
│  │                                                                      │   │
│  │  OrderResponse(                                                      │   │
│  │      id=order.id,                                                    │   │
│  │      alpaca_order_id=...,                                            │   │
│  │      status=ACCEPTED,                                                │   │
│  │      ...                                                             │   │
│  │  )                                                                   │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Risk Management

### Risk Check Pipeline

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    RiskManager.check_order()                                │
│                                                                             │
│  Input: OrderCreate, tenant_id, session_id                                  │
│  Output: RiskCheckResult(passed: bool, violations: list[str])               │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
        ┌───────────────────────────┼───────────────────────────┐
        │                           │                           │
        ▼                           ▼                           ▼
┌───────────────┐          ┌───────────────┐          ┌───────────────┐
│ Check 1       │          │ Check 2       │          │ Check 3       │
│ MAX ORDER     │          │ ALLOWED       │          │ MAX POSITION  │
│ VALUE         │          │ SYMBOLS       │          │ SIZE          │
│               │          │               │          │               │
│ qty × price   │          │ symbol in     │          │ (current +    │
│ ≤ $10,000     │          │ whitelist?    │          │  new) × price │
│               │          │               │          │ ≤ $50,000     │
└───────┬───────┘          └───────┬───────┘          └───────┬───────┘
        │                          │                          │
        └──────────────────────────┼──────────────────────────┘
                                   │
        ┌──────────────────────────┼──────────────────────────┐
        │                          │                          │
        ▼                          ▼                          ▼
┌───────────────┐          ┌───────────────┐          ┌───────────────┐
│ Check 4       │          │ Check 5       │          │ Aggregate     │
│ DAILY LOSS    │          │ ORDER RATE    │          │ Results       │
│ LIMIT         │          │ LIMIT         │          │               │
│               │          │               │          │ passed = all  │
│ daily_pnl     │          │ orders in     │          │   checks pass │
│ > -$5,000     │          │ last 60s < 10 │          │               │
│               │          │               │          │ violations =  │
└───────┬───────┘          └───────┬───────┘          │   [failed]    │
        │                          │                  └───────────────┘
        └──────────────────────────┘
```

### Risk Limits Configuration

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           RiskLimits                                        │
│                                                                             │
│  Can be configured at session level or tenant level                         │
│                                                                             │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │  max_position_size: float | None                                     │   │
│  │  └─ Maximum dollar value for a single position                       │   │
│  │     Default: $50,000                                                 │   │
│  ├──────────────────────────────────────────────────────────────────────┤   │
│  │  max_daily_loss: float | None                                        │   │
│  │  └─ Maximum loss allowed per day before trading halts                │   │
│  │     Default: $5,000                                                  │   │
│  ├──────────────────────────────────────────────────────────────────────┤   │
│  │  max_order_value: float | None                                       │   │
│  │  └─ Maximum value for a single order                                 │   │
│  │     Default: $10,000                                                 │   │
│  ├──────────────────────────────────────────────────────────────────────┤   │
│  │  allowed_symbols: list[str] | None                                   │   │
│  │  └─ Whitelist of tradeable symbols                                   │   │
│  │     Default: None (all symbols allowed)                              │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Daily P&L Tracking

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        Daily P&L Tracking                                   │
│                                                                             │
│  The RiskManager tracks daily P&L metrics:                                  │
│                                                                             │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │  DailyPnL Record                                                     │   │
│  │  ├─ date: today's date                                               │   │
│  │  ├─ realized_pnl: sum of closed position P&L                         │   │
│  │  ├─ unrealized_pnl: sum of open position P&L                         │   │
│  │  ├─ equity_high: highest equity seen today                           │   │
│  │  ├─ equity_low: lowest equity seen today                             │   │
│  │  ├─ trades_count: number of trades today                             │   │
│  │  ├─ win_count: winning trades                                        │   │
│  │  └─ loss_count: losing trades                                        │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  Drawdown Calculation:                                                      │
│  drawdown = (equity_high - current_equity) / equity_high                    │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Price Fetching Fallback Strategy

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    _get_current_price(symbol)                               │
│                                                                             │
│  Multi-layer fallback for price estimation:                                 │
│                                                                             │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │  Layer 1: Market Data Service                                        │   │
│  │  market_data.get_latest_price(symbol)                                │   │
│  │  └─ HTTP call to market-data service                                 │   │
│  └─────────────────────────────────┬────────────────────────────────────┘   │
│                                    │ If unavailable                         │
│                                    ▼                                        │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │  Layer 2: Local Cache                                                │   │
│  │  _price_cache[symbol]                                                │   │
│  │  └─ Price from recent successful fetch                               │   │
│  └─────────────────────────────────┬────────────────────────────────────┘   │
│                                    │ If not in cache                        │
│                                    ▼                                        │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │  Layer 3: Database Position                                          │   │
│  │  SELECT current_price FROM positions WHERE symbol = ?                │   │
│  │  └─ Last known price from position tracking                          │   │
│  └─────────────────────────────────┬────────────────────────────────────┘   │
│                                    │ If no position                         │
│                                    ▼                                        │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │  Layer 4: Default                                                    │   │
│  │  return 100.0                                                        │   │
│  │  └─ Last resort fallback                                             │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Real-Time Data Streaming

### AlpacaBarStream Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          AlpacaBarStream                                    │
│                                                                             │
│  WebSocket connection to Alpaca's real-time data feed                       │
│                                                                             │
│  URLs:                                                                      │
│  • Paper: wss://stream.data.sandbox.alpaca.markets/v2/iex                   │
│  • Live:  wss://stream.data.alpaca.markets/v2/iex                           │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         Connection Flow                                     │
│                                                                             │
│  ┌─────────────┐      ┌─────────────┐      ┌─────────────┐                  │
│  │   Connect   │─────▶│  Receive    │─────▶│   Send      │                  │
│  │  WebSocket  │      │  Welcome    │      │   Auth      │                  │
│  └─────────────┘      └─────────────┘      └──────┬──────┘                  │
│                                                   │                         │
│                                                   ▼                         │
│  ┌─────────────┐      ┌─────────────┐      ┌─────────────┐                  │
│  │   Stream    │◀─────│  Subscribe  │◀─────│  Auth OK    │                  │
│  │   Bars      │      │  to Symbols │      │  Message    │                  │
│  └─────────────┘      └─────────────┘      └─────────────┘                  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Message Types

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        WebSocket Messages                                   │
│                                                                             │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │  Welcome Message (on connect)                                        │   │
│  │  [{"T": "success", "msg": "connected"}]                              │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │  Auth Response                                                       │   │
│  │  [{"T": "success", "msg": "authenticated"}]                          │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │  Subscription Confirmation                                           │   │
│  │  [{"T": "subscription", "bars": ["AAPL", "GOOGL"]}]                  │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │  Bar Data                                                            │   │
│  │  [{                                                                  │   │
│  │    "T": "b",           // Type: bar                                  │   │
│  │    "S": "AAPL",        // Symbol                                     │   │
│  │    "t": "2024-...",    // Timestamp                                  │   │
│  │    "o": 185.00,        // Open                                       │   │
│  │    "h": 186.50,        // High                                       │   │
│  │    "l": 184.75,        // Low                                        │   │
│  │    "c": 185.50,        // Close                                      │   │
│  │    "v": 1234567,       // Volume                                     │   │
│  │    "vw": 185.25,       // VWAP                                       │   │
│  │    "n": 5432           // Trade count                                │   │
│  │  }]                                                                  │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Auto-Reconnection

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        Reconnection Strategy                                │
│                                                                             │
│  On disconnect:                                                             │
│  1. Log warning                                                             │
│  2. Attempt reconnection with exponential backoff                           │
│  3. Re-authenticate                                                         │
│  4. Re-subscribe to symbols                                                 │
│                                                                             │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │  Retry Configuration                                                 │   │
│  │  • Max attempts: 10                                                  │   │
│  │  • Base delay: 5 seconds                                             │   │
│  │  • Backoff: exponential (5s, 10s, 20s, 40s, ...)                     │   │
│  │  • Max delay: capped at reasonable limit                             │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  Attempt 1: wait 5s  ──▶ connect                                            │
│  Attempt 2: wait 10s ──▶ connect                                            │
│  Attempt 3: wait 20s ──▶ connect                                            │
│  ...                                                                        │
│  Attempt 10: give up ──▶ raise ConnectionError                              │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Position & P&L Tracking

### Position Service Operations

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         PositionService                                     │
│                                                                             │
│  Local position tracking (separate from Alpaca positions)                   │
│  Enables session-specific P&L and historical tracking                       │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│  open_position(tenant_id, session_id, symbol, side, qty, entry_price)       │
│                                                                             │
│  Creates:                                                                   │
│  Position(                                                                  │
│      symbol = "AAPL"                                                        │
│      side = "long"                                                          │
│      qty = 10                                                               │
│      avg_entry_price = 185.50                                               │
│      cost_basis = 1855.00  (qty × entry_price)                              │
│      current_price = 185.50                                                 │
│      market_value = 1855.00                                                 │
│      unrealized_pl = 0.00                                                   │
│      is_open = True                                                         │
│      opened_at = now()                                                      │
│  )                                                                          │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│  close_position(tenant_id, session_id, symbol, exit_price)                  │
│                                                                             │
│  Updates:                                                                   │
│  position.is_open = False                                                   │
│  position.closed_at = now()                                                 │
│  position.realized_pl = calculated P&L                                      │
│                                                                             │
│  P&L Calculation:                                                           │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │  Long Position:                                                      │   │
│  │  realized_pl = (exit_price - entry_price) × qty                      │   │
│  │                                                                      │   │
│  │  Example: Buy 10 @ $185.50, Sell @ $190.00                           │   │
│  │  realized_pl = (190.00 - 185.50) × 10 = $45.00 profit                │   │
│  ├──────────────────────────────────────────────────────────────────────┤   │
│  │  Short Position:                                                     │   │
│  │  realized_pl = (entry_price - exit_price) × qty                      │   │
│  │                                                                      │   │
│  │  Example: Short 10 @ $185.50, Cover @ $180.00                        │   │
│  │  realized_pl = (185.50 - 180.00) × 10 = $55.00 profit                │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│  update_prices(tenant_id, session_id, prices=None)                          │
│                                                                             │
│  For each open position:                                                    │
│  1. Fetch current price (from market-data or provided dict)                 │
│  2. Update current_price                                                    │
│  3. Update market_value = qty × current_price                               │
│  4. Calculate unrealized_pl:                                                │
│     • Long: (current_price - entry_price) × qty                             │
│     • Short: (entry_price - current_price) × qty                            │
│  5. Calculate unrealized_plpc = unrealized_pl / cost_basis                  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### P&L Aggregation

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                      Session P&L Calculation                                │
│                                                                             │
│  get_session_pnl(tenant_id, session_id) -> (realized, unrealized)           │
│                                                                             │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │  Realized P&L                                                        │   │
│  │  SELECT SUM(realized_pl) FROM positions                              │   │
│  │  WHERE tenant_id = ? AND session_id = ?                              │   │
│  │                                                                      │   │
│  │  (Includes ALL positions - both open and closed)                     │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │  Unrealized P&L                                                      │   │
│  │  SELECT SUM(unrealized_pl) FROM positions                            │   │
│  │  WHERE tenant_id = ? AND session_id = ? AND is_open = TRUE           │   │
│  │                                                                      │   │
│  │  (Only open positions)                                               │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  Total P&L = Realized + Unrealized                                          │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## External Service Integrations

### Alpaca Trading Client

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        AlpacaTradingClient                                  │
│                                                                             │
│  File: src/alpaca_client.py                                                 │
│  Protocol: REST API over HTTPS                                              │
│                                                                             │
│  Base URLs:                                                                 │
│  • Paper: https://paper-api.alpaca.markets/v2                               │
│  • Live:  https://api.alpaca.markets/v2                                     │
│                                                                             │
│  Authentication:                                                            │
│  Headers:                                                                   │
│    APCA-API-KEY-ID: <api_key>                                               │
│    APCA-API-SECRET-KEY: <api_secret>                                        │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│                            Methods                                          │
│                                                                             │
│  Account:                                                                   │
│  ├─ get_account() -> cash, equity, buying_power, ...                        │
│                                                                             │
│  Orders:                                                                    │
│  ├─ submit_order(symbol, qty, side, type, time_in_force, ...)               │
│  ├─ get_order(order_id) -> order details                                    │
│  ├─ list_orders(status, limit) -> list of orders                            │
│  └─ cancel_order(order_id) -> cancelled order                               │
│                                                                             │
│  Positions:                                                                 │
│  ├─ get_positions() -> all open positions                                   │
│  ├─ get_position(symbol) -> single position                                 │
│  ├─ close_position(symbol) -> closed position                               │
│  └─ close_all_positions() -> close everything                               │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Market Data Client

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         MarketDataClient                                    │
│                                                                             │
│  File: src/clients/market_data.py                                           │
│  Protocol: HTTP REST                                                        │
│  Target: market-data service (internal)                                     │
│                                                                             │
│  Base URL: http://market-data:8840 (configurable via MARKET_DATA_URL)       │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│                            Methods                                          │
│                                                                             │
│  get_latest_price(symbol: str) -> float | None                              │
│  └─ GET /bars/{symbol}/latest                                               │
│     Returns close price from latest bar                                     │
│                                                                             │
│  get_prices(symbols: list[str]) -> dict[str, float]                         │
│  └─ Batch fetch prices for multiple symbols                                 │
│     Calls get_latest_price for each                                         │
│                                                                             │
│  get_bars(symbol, timeframe, start, end) -> list[dict]                      │
│  └─ GET /bars/{symbol}?timeframe=...&start=...&end=...                      │
│     Returns historical bars                                                 │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Strategy Adapter

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         StrategyAdapter                                      │
│                                                                             │
│  File: src/compiler_adapter.py                                              │
│  Purpose: Bridge CompiledStrategy with StrategyRunner interface             │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│                          Initialization                                      │
│                                                                             │
│  StrategyAdapter(strategy_sexpr: str)                                       │
│                                                                             │
│  1. Parse S-expression → AST                                                │
│     ast = parse_strategy(strategy_sexpr)                                    │
│                                                                             │
│  2. Compile AST → Executable                                                │
│     compiled = compile_strategy(ast)                                        │
│                                                                             │
│  3. Initialize state                                                        │
│     _initialized = False                                                    │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│                          __call__ Method                                     │
│                                                                             │
│  Called by StrategyRunner for each bar                                      │
│                                                                             │
│  __call__(symbol, bars, position, equity) -> Signal | None                  │
│                                                                             │
│  1. Convert BarData → Compiler's Bar format                                 │
│     Bar(timestamp, open, high, low, close, volume)                          │
│                                                                             │
│  2. Sync position state with compiled strategy                              │
│     if position:                                                            │
│         compiled.set_position(Position(...))                                │
│     else:                                                                   │
│         compiled.close_position()                                           │
│                                                                             │
│  3. On first call, warm up with historical bars                             │
│     for bar in bars[:-1]:                                                   │
│         compiled.add_bar(bar)                                               │
│                                                                             │
│  4. Evaluate strategy with latest bar                                       │
│     signals = compiled.evaluate(latest_bar)                                 │
│                                                                             │
│  5. Convert compiler Signal → Runner Signal                                 │
│     Signal(type, symbol, quantity, price)                                   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Data Models

### Order Models

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           OrderCreate                                       │
│                                                                             │
│  symbol: str                    # "AAPL"                                    │
│  side: OrderSide                # BUY or SELL                               │
│  qty: float                     # 10                                        │
│  order_type: OrderType          # MARKET, LIMIT, STOP, STOP_LIMIT, TRAILING │
│  limit_price: float | None      # For LIMIT orders                          │
│  stop_price: float | None       # For STOP orders                           │
│  trail_percent: float | None    # For TRAILING_STOP                         │
│  time_in_force: TimeInForce     # DAY, GTC, IOC, FOK                        │
│  extended_hours: bool           # Trade in extended hours                   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│                          OrderResponse                                      │
│                                                                             │
│  id: UUID                       # Internal order ID                         │
│  alpaca_order_id: str | None    # Alpaca's order ID                         │
│  symbol: str                                                                │
│  side: OrderSide                                                            │
│  qty: float                                                                 │
│  order_type: OrderType                                                      │
│  limit_price: float | None                                                  │
│  stop_price: float | None                                                   │
│  status: OrderStatus            # PENDING → FILLED                          │
│  filled_qty: float | None                                                   │
│  filled_avg_price: float | None                                             │
│  submitted_at: datetime | None                                              │
│  filled_at: datetime | None                                                 │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│                            Enums                                            │
│                                                                             │
│  OrderStatus: PENDING, SUBMITTED, ACCEPTED, PARTIAL, FILLED,                │
│               CANCELLED, REJECTED, EXPIRED                                  │
│                                                                             │
│  OrderSide: BUY, SELL                                                       │
│                                                                             │
│  OrderType: MARKET, LIMIT, STOP, STOP_LIMIT, TRAILING_STOP                  │
│                                                                             │
│  TimeInForce: DAY, GTC, IOC, FOK                                            │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Session Models

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          SessionCreate                                      │
│                                                                             │
│  strategy_id: UUID              # Strategy to execute                       │
│  credentials_id: UUID           # API credentials to use                    │
│  name: str                      # Human-readable name                       │
│  mode: TradingMode              # PAPER or LIVE                             │
│  strategy_version: int | None   # Specific version (None = current)         │
│  symbols: list[str] | None      # Override strategy symbols                 │
│  config: dict | None            # Additional configuration                  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│                         SessionResponse                                     │
│                                                                             │
│  id: UUID                       # Session ID                                │
│  tenant_id: UUID                # Tenant isolation                          │
│  strategy_id: UUID                                                          │
│  mode: TradingMode                                                          │
│  status: SessionStatus          # ACTIVE, PAUSED, STOPPED, ERROR            │
│  started_at: datetime                                                       │
│  stopped_at: datetime | None                                                │
│  pnl: float                     # Total P&L (realized + unrealized)         │
│  trades_count: int              # Number of completed trades                │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Position Models

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        PositionResponse                                     │
│                                                                             │
│  symbol: str                    # "AAPL"                                    │
│  qty: float                     # 10                                        │
│  side: str                      # "long" or "short"                         │
│  cost_basis: float              # Entry value (qty × entry_price)           │
│  market_value: float            # Current value (qty × current_price)       │
│  unrealized_pnl: float          # Current unrealized P&L                    │
│  unrealized_pnl_percent: float  # P&L as percentage of cost basis           │
│  current_price: float           # Latest price                              │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Risk Models

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           RiskLimits                                        │
│                                                                             │
│  max_position_size: float | None    # Max $ per position                    │
│  max_daily_loss: float | None       # Max daily loss before halt            │
│  max_order_value: float | None      # Max $ per order                       │
│  allowed_symbols: list[str] | None  # Symbol whitelist                      │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│                        RiskCheckResult                                      │
│                                                                             │
│  passed: bool                   # All checks passed?                        │
│  violations: list[str]          # List of failed checks                     │
│                                                                             │
│  Example violations:                                                        │
│  • "Order value $15,000 exceeds limit $10,000"                              │
│  • "Symbol CRYPTO not in allowed symbols"                                   │
│  • "Daily loss $5,500 exceeds limit $5,000"                                 │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## API Endpoints

### Orders Router (`/orders`)

| Method   | Endpoint                  | Description                             |
| -------- | ------------------------- | --------------------------------------- |
| `POST`   | `/orders`                 | Submit a new order                      |
| `GET`    | `/orders`                 | List orders (filter by session, status) |
| `GET`    | `/orders/{order_id}`      | Get order details                       |
| `DELETE` | `/orders/{order_id}`      | Cancel an order                         |
| `POST`   | `/orders/{order_id}/sync` | Sync order status from Alpaca           |
| `POST`   | `/orders/sync`            | Sync all pending orders                 |

### Sessions Router (`/sessions`)

| Method | Endpoint                        | Description                 |
| ------ | ------------------------------- | --------------------------- |
| `POST` | `/sessions`                     | Start a new trading session |
| `GET`  | `/sessions`                     | List sessions               |
| `GET`  | `/sessions/{session_id}`        | Get session details         |
| `POST` | `/sessions/{session_id}/stop`   | Stop a session              |
| `POST` | `/sessions/{session_id}/pause`  | Pause a session             |
| `POST` | `/sessions/{session_id}/resume` | Resume a paused session     |

### Positions Router (`/positions`)

| Method   | Endpoint              | Description                        |
| -------- | --------------------- | ---------------------------------- |
| `GET`    | `/positions`          | List positions (session or Alpaca) |
| `GET`    | `/positions/{symbol}` | Get position for symbol            |
| `DELETE` | `/positions/{symbol}` | Close position                     |
| `POST`   | `/positions/sync`     | Sync prices from market data       |

---

## Complete Data Flow Example

### Scenario: Strategy Generates Buy Signal

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  Step 1: Bar Arrives via WebSocket                                          │
│                                                                             │
│  AlpacaBarStream receives:                                                  │
│  {"T": "b", "S": "AAPL", "c": 185.50, "v": 1234567, ...}                    │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  Step 2: Runner Processes Bar                                               │
│                                                                             │
│  StrategyRunner._process_bar()                                              │
│  • Adds bar to _bar_history["AAPL"]                                         │
│  • Checks warmup complete (50 bars)                                         │
│  • Calls strategy_fn(symbol, bars, position, equity)                        │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  Step 3: Strategy Evaluates                                                 │
│                                                                             │
│  StrategyAdapter.__call__()                                                 │
│  • Converts bars to compiler format                                         │
│  • compiled.evaluate(latest_bar)                                            │
│  • Strategy: SMA(20) crossed above SMA(50)                                  │
│  • Returns Signal(type="buy", symbol="AAPL", quantity=10, price=185.50)     │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  Step 4: Risk Validation                                                    │
│                                                                             │
│  RiskManager.check_order()                                                  │
│  ✓ Order value: $1,855 ≤ $10,000 max                                        │
│  ✓ Symbol: AAPL in allowed list                                             │
│  ✓ Position size: $1,855 ≤ $50,000 max                                      │
│  ✓ Daily loss: -$200 > -$5,000 limit                                        │
│  ✓ Order rate: 3 orders in last 60s < 10 limit                              │
│  → RiskCheckResult(passed=True, violations=[])                              │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  Step 5: Order Submission                                                   │
│                                                                             │
│  OrderExecutor.submit_order()                                               │
│  • Creates Order record in database (status=PENDING)                        │
│  • Calls AlpacaTradingClient.submit_order()                                 │
│    POST https://paper-api.alpaca.markets/v2/orders                          │
│    {"symbol": "AAPL", "qty": 10, "side": "buy", "type": "market"}           │
│  • Alpaca returns: {"id": "abc123", "status": "accepted"}                   │
│  • Updates Order (alpaca_order_id="abc123", status=ACCEPTED)                │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  Step 6: Position Tracking                                                  │
│                                                                             │
│  StrategyRunner._update_position()                                          │
│  • Creates Position(symbol="AAPL", side="long", quantity=10)                │
│  • Updates _positions["AAPL"]                                               │
│                                                                             │
│  PositionService.open_position() (in database)                              │
│  • Creates Position record with entry price, cost basis                     │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  Step 7: Audit & Alerts                                                     │
│                                                                             │
│  AuditService.log_signal()                                                  │
│  • Records signal generation event                                          │
│                                                                             │
│  AuditService.log_order_submitted()                                         │
│  • Records order submission event                                           │
│                                                                             │
│  AlertService.on_order_filled() (when fill confirmed)                       │
│  • Sends webhook notification to configured endpoints                       │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  Step 8: Metrics Update                                                     │
│                                                                             │
│  Runner metrics updated:                                                    │
│  • signals_generated: 1                                                     │
│  • orders_submitted: 1                                                      │
│  • orders_rejected: 0                                                       │
│  • positions_count: 1                                                       │
│                                                                             │
│  RiskManager metrics updated:                                               │
│  • order_count_last_minute: 4                                               │
│  • positions tracking updated                                               │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Summary

The trading service provides a complete, production-grade execution engine with:

1. **Real-time Execution**: WebSocket streaming for live market data, async processing loop
2. **Risk Controls**: 5-layer validation pipeline protecting against excessive losses
3. **Session Management**: Full lifecycle management with runner integration
4. **Position Tracking**: Local database tracking with P&L calculations
5. **Audit Trail**: Comprehensive logging for compliance and debugging
6. **Alert System**: Webhook notifications for critical events
7. **Broker Integration**: Direct connection to Alpaca for order execution
8. **Multi-tenancy**: Complete tenant isolation across all operations

The architecture separates concerns cleanly:

- **Routers** handle HTTP interface
- **Services** handle business logic
- **Runner** handles real-time execution
- **Executor** handles order lifecycle
- **Risk Manager** enforces trading limits
- **Clients** abstract external services
