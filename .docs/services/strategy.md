# Strategy Service Architecture

The strategy service is the core engine for defining, validating, and compiling algorithmic trading strategies, and for managing their paper/live executions. It owns the strategy lifecycle—from DSL parsing through versioning and cloning—plus a large template library and the execution lifecycle that funds and releases a ledger sleeve per running strategy.

---

## Overview

The strategy service is responsible for:

- **Strategy Management**: CRUD, versioning, and cloning of strategies with full version history
- **DSL Parsing & Validation**: parse/validate the S-expression DSL (via the shared `llamatrade_dsl` lib)
- **Compilation**: extract indicators and compute lookback requirements (via `llamatrade_dsl` static AST analysis)
- **Templates**: a large library of pre-built strategy templates
- **Execution lifecycle**: create/start/pause/stop paper & live executions, funding and releasing a ledger *sleeve* per execution via the portfolio service
- **Sleeve reconciliation**: a background sweep that retries deferred sleeve releases so capital is never trapped

The strategy language — parser, validator, and the **static AST analysis** that extracts indicators and computes lookbacks — lives in `llamatrade_dsl`. The 17-indicator library and the `StrategySession` evaluation engine live in `llamatrade_runtime`, driven by the backtest and trading services at run time. This service parses, validates, and analyzes strategies but does not run them against market data itself.

---

## Architecture Overview

### System Architecture

```
STRATEGY SERVICE · :8820 · FastAPI + Connect ASGI (StrategyServiceASGIApplication, /health, AuthMiddleware)
│
├─ StrategyServicer — 18 RPCs
│    Strategy CRUD  · CreateStrategy · GetStrategy · ListStrategies · UpdateStrategy
│                   · DeleteStrategy · CloneStrategy · UpdateStrategyStatus
│    Validation     · CompileStrategy · ValidateStrategy · ListStrategyVersions
│    Templates      · ListTemplates · GetTemplate
│    Executions     · CreateExecution · GetExecution · ListExecutions
│                   · StartExecution · PauseExecution · StopExecution
│
├─ Service layer
│    StrategyService  — CRUD, versioning, execution lifecycle, ledger-sleeve funding/release
│    TemplateService  — pre-built strategy templates
│    tasks.py         — stranded-sleeve reconcile sweep (Postgres advisory lock)
│
└─ Depends on
     PostgreSQL          — strategies · strategy_versions · strategy_executions (RLS-scoped)
     llamatrade_dsl      — parse / validate / (de)serialize + static AST analysis (extract indicators, lookbacks)
     LedgerClient        — portfolio service, sleeve open / fund / close
     consumers           — backtest · trading · frontend
```

### Strategy Lifecycle Flow

```
╔════════════════════════════════════════════════════════════════════════════════════════════╗
║             STRATEGY LIFECYCLE  ·  creation → compilation → runtime evaluation             ║
╚════════════════════════════════════════════════════════════════════════════════════════════╝

                 ╭───────────────────────────────────────────────────────────╮
                 │      1 · CREATION  (CreateStrategy / UpdateStrategy)      │
                 ├───────────────────────────────────────────────────────────┤
                 │ S-expression DSL ──► parse_strategy() ──► AST             │
                 │ validate_strategy() ──► ValidationResult                  │
                 │ INSERT Strategy + StrategyVersion vN (stores DSL text)   │
                 ╰───────────────────────────────────────────────────────────╯
                                               │
                                               ▼
                     ╭───────────────────────────────────────────────────╮
                     │        2 · COMPILATION  (one-time, at load)       │
                     ├───────────────────────────────────────────────────┤
                     │ compile_strategy(ast) ──► CompiledStrategy        │
                     │ extract_indicators() ──► [IndicatorSpec, …]       │
                     │ get_max_lookback() ──► min bars required (warmup) │
                     ╰───────────────────────────────────────────────────╯
                                               │
                                               ▼
                ╭────────────────────────────────────────────────────────────╮
                │           3 · RUNTIME EVALUATION  (per new bar)            │
                ├────────────────────────────────────────────────────────────┤
                │ StrategySession (llamatrade_runtime) evaluates the tree    │
                │ and produces target portfolio weights; the execution layer │
                │ turns weight deltas into orders (see ../strategy-dsl.md)   │
                ╰────────────────────────────────────────────────────────────╯

                    ╔════════════════════════════════════════════════════╗
                    ║                  StrategyVersion                   ║
                    ╠════════════════════════════════════════════════════╣
                    ║ editing always mints vN+1 — versions are immutable ║
                    ║ every backtest / live session pins an exact vN     ║
                    ╚════════════════════════════════════════════════════╝
```

---

## Directory Structure

```
services/strategy/
├── src/
│   ├── main.py                # FastAPI app, Connect mount, AuthMiddleware, /health
│   ├── models.py              # Pydantic request/response + ConfigOverride/ExecutionCreate
│   ├── proto_mappers.py       # DB rows ↔ proto messages
│   ├── tasks.py               # stranded-sleeve reconcile sweep (advisory-locked)
│   ├── grpc/
│   │   ├── servicer.py        # StrategyServicer — all 18 RPCs (main API entry point)
│   │   └── error_handler.py   # @handle_service_errors, parse_uuid
│   └── services/
│       ├── strategy_service.py   # CRUD, versioning, execution lifecycle, ledger sleeves
│       └── template_service.py   # pre-built template library
└── tests/
```

The DSL language + analysis, the indicator library, and the runtime evaluation loop live in shared libs, **not** in this service:

| Concern | Lib | Key modules |
|---|---|---|
| DSL parse/validate | `llamatrade_dsl` | `parse_strategy`, `validate_strategy`, `to_json`/`from_json` |
| Static AST analysis (compilation) | `llamatrade_dsl` | `analysis.py` (extract indicators, required symbols, lookbacks), `window.py` (history window) |
| Indicators & evaluation | `llamatrade_runtime` | `evaluation/` (conditions, compiled, state), `indicators/library.py` (17 indicators), `session.py` (`StrategySession`) |
| Runtime signal loop | `llamatrade_runtime` | `StrategyRuntime` — driven by the backtest & trading services, not by this service |

---

## Core Components

| Component | Location | Responsibility |
|-----------|----------|----------------|
| **StrategyServicer** | `grpc/servicer.py` | Connect RPC handlers (18 RPCs) |
| **StrategyService** | `services/strategy_service.py` | CRUD, versioning, execution lifecycle, ledger sleeves |
| **TemplateService** | `services/template_service.py` | pre-built template library |
| **reconcile sweep** | `tasks.py` | retries deferred sleeve releases (advisory-locked) |
| **StrategySession** | `llamatrade_runtime/session.py` | shared evaluation engine |
| **indicator library** | `llamatrade_runtime/indicators/library.py` | 17 NumPy indicators |
| **DSL** | `llamatrade_dsl` | parse / validate / (de)serialize |

---

## RPC Endpoints

The service exposes **18 RPCs** across five groups.

### Strategy Management

| RPC | Description |
|-----|-------------|
| `CreateStrategy` | Parse DSL (or instantiate a template), validate, create strategy + v1 |
| `GetStrategy` | Fetch strategy with an optional pinned version |
| `ListStrategies` | List with status filter, search, sort, and pagination |
| `UpdateStrategy` | Update metadata or mint a new version |
| `CloneStrategy` | Copy a strategy (optionally from a specific version) under a new name |
| `DeleteStrategy` | Soft delete (archive); refused while an execution is running |
| `UpdateStrategyStatus` | DRAFT→ACTIVE, ACTIVE↔PAUSED, any→ARCHIVED |

### Validation & Versions

| RPC | Description |
|-----|-------------|
| `CompileStrategy` | Validate + compile DSL to JSON without saving (no tenant scope) |
| `ValidateStrategy` | Validate an existing strategy's current config |
| `ListStrategyVersions` | List versions with pagination |

### Templates (public — no auth)

| RPC | Description |
|-----|-------------|
| `ListTemplates` | List templates filtered by category / asset class / difficulty |
| `GetTemplate` | Fetch a single template by id |

### Execution Lifecycle

| RPC | Description |
|-----|-------------|
| `CreateExecution` | Create a paper/live execution for a strategy version |
| `GetExecution` | Fetch an execution |
| `ListExecutions` | List executions (filter by strategy / status / mode) |
| `StartExecution` | PENDING→RUNNING; funds a ledger sleeve when funding intent is set |
| `PauseExecution` | RUNNING→PAUSED |
| `StopExecution` | RUNNING/PAUSED→STOPPED; releases the ledger sleeve |

---

## Execution Lifecycle & Ledger Sleeves

Beyond authoring strategies, the service owns the lifecycle of **executions** — a strategy version put into paper or live trading — and coordinates capital with the portfolio service's double-entry ledger.

An execution is a `StrategyExecution` row (`strategy_executions`): strategy id + version, `mode` (paper/live), `status` (PENDING → RUNNING → PAUSED/STOPPED/ERROR), `allocated_capital`, and ledger identity (`credentials_id`, `sleeve_id`, `account_id`). Live value and position count are projected from the ledger sleeve rather than stored on the row.

- **Funding** (`start_execution` → `_fund_sleeve`): when an execution carries funding intent (allocated capital + credentials), starting it opens and funds a dedicated ledger *sleeve* via `LedgerClient` (portfolio service, `PORTFOLIO_GRPC_TARGET`). Trading threads the returned `sleeve_id`/`account_id` through orders and fills (see `ledger.proto` and the [integration contract](../portfolio-ledger.md#integration-contract-trading--portfolio--strategy)).
- **Release** (`stop_execution` → `_close_sleeve`): stopping closes the sleeve, re-homing open positions to the Unmanaged sleeve and free cash to Unallocated, so a stopped strategy never traps capital. The close is best-effort: the stop succeeds even if the ledger is unreachable, leaving `sleeve_id` set as a "needs release" marker.
- **Reconciliation** (`reconcile_stranded_sleeves`, `tasks.py`): a background sweep retries sleeve release for terminal (STOPPED/ERROR) executions whose close was deferred (ledger outage, or an in-flight order holding reserved cash). Each pass is gated by a per-cycle Postgres advisory lock so scaled replicas don't duplicate ledger calls; a dead pod is transparently taken over on the next tick.

`StartExecution` enforces a per-tenant live-strategy limit (`live_strategies` from the tenant's plan; free-tier default 1) via `llamatrade_db.plan_limits.enforce_plan_limit` — it counts RUNNING `StrategyExecution` rows and returns `RESOURCE_EXHAUSTED` when the limit is reached.

Archiving a strategy is refused (`FAILED_PRECONDITION`) while it has a running execution — the operator must stop it first.

### Notifications

Lifecycle transitions publish onto the `lt.notifications` Kafka topic (fire-and-forget `publish_safe`, deterministic dedup ids). Six emission sites:

| Category | Trigger | Default severity / email |
|----------|---------|--------------------------|
| `EXECUTION_STARTED` | `StartExecution` succeeds | Info, in-app only |
| `EXECUTION_STOPPED` | `StopExecution` completes | Info, in-app only |
| `EXECUTION_CANCELLED` | Execution cancelled | Info, in-app only |
| `FUNDING_FAILED` | `_fund_sleeve` cannot open/fund the ledger sleeve | Actionable, emailed |
| `SLEEVE_RELEASE_DEFERRED` | Sleeve release fails at stop and is deferred to the sweep | Critical, emailed |
| `PLAN_LIMIT_REACHED` | `StartExecution` hits the `live_strategies` plan limit | Info, in-app only |

---

## Strategy Language

The strategy language is specified in [../strategy-dsl.md](../strategy-dsl.md); allocation semantics are specified in [../signals-and-weights.md](../signals-and-weights.md).

Two facts matter for this service:

- The DSL is an allocation language. Evaluating a strategy produces target portfolio weights, not entry/exit signals; the execution layer turns weight deltas into orders.
- The stored representation is the DSL text itself (`strategy_versions.config_sexpr`). The JSON IR and the visual block tree are derived from it on demand; `symbols` and `rebalance` are projections recomputed on write.

This service parses, validates, and statically analyzes that text via `llamatrade_dsl`. Evaluation happens in `llamatrade_runtime` (`compile_strategy()` -> `CompiledStrategy`, wrapped by `StrategySession`), driven by the backtest and trading services.

---

## Strategy Templates

`TemplateService` ships ~80 pre-built strategy definitions (public, no auth). Each has a hyphenated `id`, a category, an asset class, and a difficulty, and `ListTemplates` filters on those three fields. Representative examples:

| Template id | Category | Description |
|-------------|----------|-------------|
| `ma-crossover` | Trend Following | EMA fast/slow crossover |
| `rsi-mean-reversion` | Mean Reversion | RSI oversold buy / overbought sell |
| `macd-strategy` | Momentum | MACD line crosses signal |
| `bollinger-bounce` | Mean Reversion | Price bounces off bands |
| `donchian-breakout` | Breakout | Turtle-style channel breakout |
| `dual-momentum` | Momentum | Relative + absolute momentum |
| `momentum-sectors` | Momentum | Sector rotation |
| `adx-trend-confirmation` | Trend Following | ADX strength filter |

The full set lives in `services/strategy/src/services/template_service.py`.

---

## Data Models

### Pydantic Schemas (`models.py`)

Requests are validated with Pydantic; responses are proto messages built in `proto_mappers.py` (there is no Pydantic response layer). Statuses and modes are proto enums: `strategy_pb2.StrategyStatus` (DRAFT / ACTIVE / PAUSED / ARCHIVED) and `common_pb2.ExecutionStatus` / `ExecutionMode`, stored as integers via TypeDecorators.

```python
class StrategyCreate(BaseModel):
    name: str
    description: str | None = None
    config_sexpr: str  # S-expression DSL code (length-capped)

class StrategyUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    status: StrategyStatus.ValueType | None = None
    config_sexpr: str | None = None  # Creates new version if changed
    changelog: str | None = None     # Used when config_sexpr changes

class ExecutionCreate(BaseModel):
    version: int | None = None            # defaults to the strategy's current version
    mode: int = EXECUTION_MODE_PAPER      # proto ExecutionMode
    config_override: ConfigOverride | None = None
    allocated_capital: Decimal | None = None
    credentials_id: UUID | None = None
```

### Database Models (`libs/db`)

```python
class Strategy(Base):
    """Trading strategy definition (metadata; config lives on versions)."""
    __tablename__ = "strategies"

    id: UUID
    tenant_id: UUID
    name: str
    description: str | None
    status: int                    # proto StrategyStatus (draft/active/paused/archived)
    is_public: bool
    current_version: int
    created_at: datetime
    updated_at: datetime
    created_by: UUID

class StrategyVersion(Base):
    """Immutable version snapshot. config_sexpr is the single source of truth."""
    __tablename__ = "strategy_versions"

    id: UUID
    tenant_id: UUID                # defense-in-depth (already scoped via strategy_id)
    strategy_id: UUID              # FK to Strategy
    version: int                   # 1, 2, 3, ...
    config_sexpr: str              # The DSL text - the only stored representation
    symbols: list[str]             # Projection derived on write (GIN-indexed)
    rebalance: str                 # Projection derived on write
    changelog: str | None
    created_at: datetime
    created_by: UUID

class StrategyExecution(Base):
    """A strategy version put into paper/live trading."""
    __tablename__ = "strategy_executions"

    id: UUID
    tenant_id: UUID
    strategy_id: UUID
    version: int
    mode: int                      # proto ExecutionMode (paper/live)
    status: int                    # proto ExecutionStatus (pending/running/paused/stopped/error)
    allocated_capital: Decimal | None
    config_override: dict | None   # JSONB
    error_message: str | None
    color: str | None              # UI color for charts
    # Ledger identity (set when the execution is funded)
    credentials_id: UUID | None
    sleeve_id: UUID | None
    account_id: UUID | None
    started_at: datetime | None
    stopped_at: datetime | None
```

---

## Multi-Tenancy

Identity is resolved at the Connect boundary from the authenticated principal (JWT via the fail-closed `AuthMiddleware`), **not** from the wire `TenantContext`:

1. `AuthMiddleware` verifies the JWT and populates the request identity.
2. `_validate_tenant_context()` → `resolve_identity_connect(request.context)` returns the verified `(tenant_id, user_id)`, rejecting a request whose wire tenant does not match the token.
3. Handlers open `tenant_session(tenant_id, ...)`, which applies Postgres **row-level security** so every query is scoped to the tenant.
4. Stateless compilation runs in `system_session` (touches no tenant rows).

```python
tenant_id, user_id = resolve_identity_connect(request.context)
async with tenant_session(tenant_id, self._maker()) as db:
    service = StrategyService(db)
    ...  # RLS scopes every query to tenant_id
```

---

## Internal Service Connections

### Consumers

| Consumer | Use Case | Mechanism |
|----------|----------|-----------|
| **Frontend** | Strategy builder, management, executions | All RPCs |
| **Backtest** | Load strategy for simulation | Reads `Strategy` / `StrategyVersion` rows (`config_sexpr`) from the shared DB via `llamatrade_db` |
| **Trading** | Load strategy for live execution | Reads `Strategy` / `StrategyVersion` rows (`config_sexpr`) from the shared DB via `llamatrade_db` |

Strategy **calls out** to the portfolio service (`LedgerClient`, `PORTFOLIO_GRPC_TARGET`) to open, fund, and close an execution's ledger sleeve.

### Shared Libraries Used

| Library | Import | Purpose |
|---------|--------|---------|
| `llamatrade_dsl` | `from llamatrade_dsl import parse_strategy, validate_strategy, extract_indicators, get_required_symbols` | DSL parsing, validation & static analysis |
| `llamatrade_db` | `from llamatrade_db import Strategy, StrategyVersion` | Database models |
| `llamatrade_proto` | `from llamatrade_proto.generated import strategy_pb2` | Proto definitions |

---

## Configuration

### Environment Variables

```bash
# Database
DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/llamatrade

# Service configuration
LOG_LEVEL=INFO
CORS_ORIGINS=http://localhost:8800,http://localhost:3000

# Integrations
KAFKA_BOOTSTRAP_SERVERS=localhost:9092   # notification publishing via llamatrade_events
PORTFOLIO_GRPC_TARGET=portfolio:8860     # LedgerClient target for sleeve funding/release
```

### Service Port

- **Port**: 8820
- **Health Check**: `GET http://localhost:8820/health`

---

## Health Check

**Endpoint:** `GET /health`

```json
{
  "status": "healthy",
  "service": "strategy",
  "version": "0.1.0"
}
```

---

## Data Flow: Strategy Creation

```
Frontend: CreateStrategy({name, config_sexpr})
    ↓
StrategyServicer.create_strategy()
    ↓
StrategyService.create_strategy()
    ├→ parse_strategy(config_sexpr) → Strategy AST
    ├→ validate_strategy(ast) → ValidationResult
    ├→ get_required_symbols(ast) / ast.rebalance → projections
    ├→ INSERT Strategy (status=DRAFT, current_version=1)
    └→ INSERT StrategyVersion (version=1, config_sexpr=DSL text, symbols, rebalance)
    ↓
Return proto Strategy
```

Compilation and bar-by-bar evaluation happen in the backtest and trading services via `llamatrade_runtime`; see [../strategy-dsl.md](../strategy-dsl.md) (Execution Pipeline) and [../execution-runtime.md](../execution-runtime.md).

---

## Key Design Patterns

| Pattern | Where | Purpose |
|---------|-------|---------|
| **Service Layer** | `services/*` | Separation of concerns |
| **Repository Pattern** | `StrategyService._get_strategy_by_id()` | DB abstraction |
| **Immutable AST** | Frozen dataclasses (`llamatrade_dsl`) | Prevent accidental mutation |
| **Immutable Versions** | `StrategyVersion` | Editing mints vN+1; runs pin an exact version |
| **Proto Mapping** | `proto_mappers.py` | DB rows ↔ proto messages |

---

## Summary

The strategy service provides a complete strategy management system with:

1. **DSL-Driven Strategies**: readable S-expression allocation language (see [../strategy-dsl.md](../strategy-dsl.md))
2. **Comprehensive Validation**: parse-time and semantic validation with clear errors
3. **Version Control**: full version history for audit and rollback
4. **Multi-Tenancy**: JWT-derived identity + Postgres row-level security
5. **Template Library**: ~80 pre-built strategies for quick start
6. **Execution Lifecycle**: paper/live executions with ledger-sleeve funding, release, and reconciliation
7. **Clean API**: gRPC/Connect protocol for type-safe communication

Evaluation (indicators, conditions, target weights) lives in `llamatrade_runtime` and is run by the backtest and trading services, not by this service.

Architecture separates concerns: Servicer (gRPC) → Service (business logic) → DSL (parsing/validation) → Database (persistence).

---

## Error Handling

### DSL Parsing Errors

Parse errors include position information for debugging:

```python
# Example parse error
ParseError(
    message="Unexpected token ')'",
    line=5,
    column=12,
    source="(strategy :entry )",
)
```

### Validation Errors

Semantic errors are returned in a `ValidationResult` (pass/fail plus a list of `ValidationError`s with node paths). The validation rules themselves are specified in [../strategy-dsl.md](../strategy-dsl.md) (Validation Rules).

### gRPC Status Codes

| Status Code | When Raised | Example |
|-------------|-------------|---------|
| `INVALID_ARGUMENT` | Invalid DSL syntax or validation failure | Parse error, missing fields |
| `NOT_FOUND` | Strategy or version not found | Get non-existent strategy |
| `ALREADY_EXISTS` | Strategy with same name exists | Create duplicate strategy |
| `INTERNAL` | Unexpected server error | Database connection failure |

### Error Response Format

```json
{
  "code": "INVALID_ARGUMENT",
  "message": "Strategy validation failed",
  "details": [
    {"field": "entry", "error": "Invalid indicator: 'sma' requires period parameter"}
  ]
}
```

---

## Startup/Shutdown Sequence

### Startup

```
1. Load environment configuration (DATABASE_URL, CORS_ORIGINS)
2. Initialize logging
3. Create FastAPI application with lifespan handler
4. In lifespan:
   a. Import Connect ASGI application from proto
   b. Create StrategyServicer instance
   c. Mount Connect app at root path
5. Add CORS middleware
6. Register health check endpoint (/health)
7. Start accepting requests
```

### Shutdown

```
1. Stop accepting new requests
2. Wait for active strategy operations to complete
3. Close database connections (via session maker)
4. FastAPI cleanup
```

---

## Testing

### Test Structure

```
tests/
├── test_error_handler.py       # Error decorator + UUID parsing tests
├── test_grpc_servicer.py       # gRPC endpoint tests
├── test_health.py              # Health check tests
├── test_models.py              # Request schema tests
├── test_notifications_emitted.py # Notification emission per lifecycle transition
├── test_proto_mappers.py       # DB row ↔ proto mapping tests
├── test_strategy_service.py    # Strategy CRUD + execution lifecycle tests
├── test_tasks.py               # Sleeve-reconcile sweep tests
├── test_template_service.py    # Template library tests
└── test_tenant_isolation_db.py # RLS / tenant isolation tests
```

### Running Tests

```bash
# Run all tests
cd services/strategy && pytest

# Run with coverage
pytest --cov=src --cov-report=term-missing

# Run specific test file
pytest tests/test_strategy_service.py

# Run specific test
pytest tests/test_strategy_service.py::test_create_strategy_success
```

### Key Test Scenarios

- **Strategy CRUD**: Create, read, update, delete with validation
- **DSL parsing**: Valid/invalid S-expressions, edge cases
- **Version management**: Create new versions, list versions
- **Indicator validation**: Parameter counts, output selectors
- **Template instantiation**: Generate strategy from template
- **Multi-tenancy**: Tenant isolation, cross-tenant access prevention
- **Compilation**: Extract indicators, compute lookback requirements

### Capabilities

- **gRPC/Connect Endpoints**: 18 RPCs across strategy management, validation/versions, templates, and execution lifecycle (see [RPC Endpoints](#rpc-endpoints))
- **Strategy Service**: full CRUD with version management, cloning, and execution lifecycle
- **DSL Parser**: complete S-expression parsing (`llamatrade_dsl`)
- **DSL Validator**: semantic validation with error messages
- **Indicator Library**: 17 indicators (SMA, EMA, RSI, MACD, etc.) in `llamatrade_runtime`
- **Template Service**: ~80 pre-built strategy templates
- **Compiler Pipeline**: indicator extraction, lookback calculation (`llamatrade_dsl` static analysis)
- **Health Check**: standard `/health` endpoint
- **Execution Lifecycle**: create/start/pause/stop executions with ledger-sleeve funding, release, and reconciliation
