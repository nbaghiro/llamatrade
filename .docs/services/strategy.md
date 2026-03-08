# Strategy Service Architecture

The strategy service is the core engine for defining, validating, compiling, and evaluating algorithmic trading strategies. It manages the complete strategy lifecycle—from DSL parsing through runtime signal generation—and provides versioning, deployment tracking, and a library of pre-built templates.

---

## Overview

The strategy service is responsible for:

- **Strategy Management**: CRUD operations for strategies with full version history
- **DSL Parsing & Validation**: Parse S-expression DSL into AST, validate semantics
- **Compilation**: Extract indicators, compute lookback requirements, prepare for execution
- **Runtime Evaluation**: Evaluate entry/exit conditions against live market data
- **Indicator Library**: 20+ technical indicators with NumPy-based computation
- **Templates**: Pre-built strategy templates for common trading patterns
- **Deployment Tracking**: Track which strategy versions are deployed to paper/live

---

## Architecture Overview

### System Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          STRATEGY SERVICE :8820                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                      FastAPI + Connect ASGI                         │    │
│  │   /health    StrategyServiceASGIApplication                         │    │
│  └─────────────────────────────┬───────────────────────────────────────┘    │
│                                │                                            │
│  ┌─────────────────────────────┴───────────────────────────────────────┐    │
│  │                      gRPC Servicer                                  │    │
│  │                                                                     │    │
│  │  CreateStrategy ──────► Parse DSL, validate, create strategy + v1   │    │
│  │  GetStrategy ─────────► Fetch strategy ± specific version           │    │
│  │  ListStrategies ──────► List with filters (status, type, pagination)│    │
│  │  UpdateStrategy ──────► Update metadata or create new version       │    │
│  │  DeleteStrategy ──────► Soft delete (archive)                       │    │
│  │  CompileStrategy ─────► Validate + parse DSL without saving         │    │
│  │  ValidateStrategy ────► Validate existing strategy config           │    │
│  │  ListStrategyVersions ► List versions with pagination               │    │
│  │  UpdateStrategyStatus ► Change status (ACTIVE/PAUSED/ARCHIVED)      │    │
│  └─────────────────────────────┬───────────────────────────────────────┘    │
│                                │                                            │
│  ┌─────────────────────────────┴───────────────────────────────────────┐    │
│  │                      Service Layer                                  │    │
│  │                                                                     │    │
│  │  StrategyService ─────► CRUD, versioning, deployment management     │    │
│  │  IndicatorService ────► Indicator metadata (params, outputs)        │    │
│  │  TemplateService ─────► Pre-built strategy templates                │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                      Compiler Pipeline                              │    │
│  │                                                                     │    │
│  │  Extractor ───────────► Extract indicator specs from AST            │    │
│  │  Pipeline ────────────► Compute indicators (NumPy)                  │    │
│  │  Evaluator ───────────► Evaluate conditions against state           │    │
│  │  CompiledStrategy ────► Runtime execution engine                    │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                      Database Layer                                 │    │
│  │                                                                     │    │
│  │  Strategy ────────────► Strategy metadata (name, type, status)      │    │
│  │  StrategyVersion ─────► Version history with config snapshots       │    │
│  │  StrategyDeployment ──► Deployment records (paper/live)             │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                             │
└─────────────────────────────────┬───────────────────────────────────────────┘
                                  │
        ┌─────────────────────────┼─────────────────────────────────┐
        ▼                         ▼                                 ▼
   ┌─────────────┐        ┌─────────────┐                   ┌─────────────┐
   │ PostgreSQL  │        │ Shared Libs │                   │  Consumers  │
   │  Database   │        │             │                   │             │
   │             │        │ llamatrade_ │                   │  Backtest   │
   │             │        │   dsl       │                   │  Trading    │
   │             │        │   compiler  │                   │  Frontend   │
   └─────────────┘        └─────────────┘                   └─────────────┘
```

### Strategy Lifecycle Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         STRATEGY LIFECYCLE                                  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌───────────────────────────────────────────────────────────────────┐      │
│  │                    1. CREATION                                    │      │
│  │                                                                   │      │
│  │   User writes S-expression DSL                                    │      │
│  │       ↓                                                           │      │
│  │   CreateStrategy RPC                                              │      │
│  │       ↓                                                           │      │
│  │   parse_strategy() → AST                                          │      │
│  │       ↓                                                           │      │
│  │   validate_strategy() → ValidationResult                          │      │
│  │       ↓                                                           │      │
│  │   to_json() → JSON for storage                                    │      │
│  │       ↓                                                           │      │
│  │   Create Strategy + StrategyVersion v1 in DB                      │      │
│  └───────────────────────────────────────────────────────────────────┘      │
│                                  │                                          │
│                                  ▼                                          │
│  ┌───────────────────────────────────────────────────────────────────┐      │
│  │                    2. COMPILATION                                 │      │
│  │                                                                   │      │
│  │   CompiledStrategy.compile(strategy_ast)                          │      │
│  │       ↓                                                           │      │
│  │   extract_indicators() → [IndicatorSpec, ...]                     │      │
│  │       ↓                                                           │      │
│  │   get_max_lookback() → min_bars required                          │      │
│  │       ↓                                                           │      │
│  │   CompiledStrategy ready for evaluation                           │      │
│  └───────────────────────────────────────────────────────────────────┘      │
│                                  │                                          │
│                                  ▼                                          │
│  ┌───────────────────────────────────────────────────────────────────┐      │
│  │                    3. RUNTIME EVALUATION                          │      │
│  │                                                                   │      │
│  │   For each new bar:                                               │      │
│  │       ↓                                                           │      │
│  │   add_bar(bar) → update history                                   │      │
│  │       ↓                                                           │      │
│  │   _compute_indicators() → NumPy arrays                            │      │
│  │       ↓                                                           │      │
│  │   Build EvaluationState                                           │      │
│  │       ↓                                                           │      │
│  │   evaluate_condition(entry/exit) → bool                           │      │
│  │       ↓                                                           │      │
│  │   Generate Signal(s) if conditions met                            │      │
│  └───────────────────────────────────────────────────────────────────┘      │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Directory Structure

```
services/strategy/
├── src/
│   ├── main.py                           # FastAPI app, Connect mount, health check
│   ├── models.py                         # Pydantic schemas (request/response)
│   ├── compiler/                         # Strategy compilation & evaluation
│   │   ├── __init__.py                   # Re-exports from shared llamatrade_compiler
│   │   ├── pipeline.py                   # Indicator computation (SMA, EMA, RSI, etc.)
│   │   ├── extractor.py                  # Extract indicator specs from strategy AST
│   │   ├── evaluator.py                  # Evaluate entry/exit conditions
│   │   ├── compiled.py                   # CompiledStrategy class
│   │   └── state.py                      # EvaluationState (runtime context)
│   ├── grpc/
│   │   ├── servicer.py                   # Connect RPC handler (main API entry point)
│   │   └── __init__.py
│   ├── indicators/                       # Technical indicator implementations
│   │   ├── __init__.py                   # Exports: SMA, EMA, MACD, ADX, RSI, etc.
│   │   ├── trend.py                      # SMA, EMA, MACD, ADX
│   │   ├── momentum.py                   # RSI, Stochastic, CCI, WilliamsR
│   │   ├── volatility.py                 # ATR, BollingerBands, KeltnerChannel
│   │   └── volume.py                     # OBV, MFI, VWAP
│   ├── services/                         # Business logic layer
│   │   ├── database.py                   # DB session management
│   │   ├── strategy_service.py           # CRUD + versioning + deployment
│   │   ├── indicator_service.py          # Indicator metadata service
│   │   └── template_service.py           # Pre-built strategy templates
│   ├── strategies/                       # Strategy implementation framework
│   │   ├── base.py                       # BaseStrategy abstract class
│   │   ├── mean_reversion/               # Mean reversion strategies
│   │   ├── momentum/                     # Momentum strategies
│   │   └── trend_following/              # Trend-following strategies
│   └── routers/                          # FastAPI routers (currently empty)
├── tests/                                # Test suite
│   ├── test_health.py
│   ├── test_grpc_servicer.py
│   ├── test_strategy_service.py
│   ├── test_indicator_service.py
│   ├── test_indicators.py
│   └── compiler/
│       ├── test_pipeline.py
│       ├── test_evaluator.py
│       ├── test_extractor.py
│       ├── test_compiled.py
│       └── test_dsl_strategies.py
├── Dockerfile
├── Dockerfile.dev
├── pyproject.toml
└── README.md
```

---

## Core Components

| Component | File | Responsibility |
|-----------|------|----------------|
| **StrategyServicer** | `grpc/servicer.py` | gRPC endpoint implementations |
| **StrategyService** | `services/strategy_service.py` | CRUD, versioning, deployment |
| **IndicatorService** | `services/indicator_service.py` | Indicator metadata |
| **TemplateService** | `services/template_service.py` | Pre-built templates |
| **CompiledStrategy** | `compiler/compiled.py` | Runtime execution engine |
| **Extractor** | `compiler/extractor.py` | Extract indicators from AST |
| **Pipeline** | `compiler/pipeline.py` | NumPy indicator computation |
| **Evaluator** | `compiler/evaluator.py` | Condition evaluation |
| **EvaluationState** | `compiler/state.py` | Runtime context |

---

## RPC Endpoints

### Strategy Management

| RPC | Request | Response | Description |
|-----|---------|----------|-------------|
| `CreateStrategy` | `CreateStrategyRequest` | `CreateStrategyResponse` | Parse DSL, validate, create strategy + v1 |
| `GetStrategy` | `GetStrategyRequest` | `GetStrategyResponse` | Fetch strategy with optional version |
| `ListStrategies` | `ListStrategiesRequest` | `ListStrategiesResponse` | List with status/type filters + pagination |
| `UpdateStrategy` | `UpdateStrategyRequest` | `UpdateStrategyResponse` | Update metadata or create new version |
| `DeleteStrategy` | `DeleteStrategyRequest` | `DeleteStrategyResponse` | Soft delete (archive) |
| `UpdateStrategyStatus` | `UpdateStrategyStatusRequest` | `UpdateStrategyStatusResponse` | Change status |

### Validation & Compilation

| RPC | Request | Response | Description |
|-----|---------|----------|-------------|
| `CompileStrategy` | `CompileStrategyRequest` | `CompileStrategyResponse` | Validate + parse DSL without saving |
| `ValidateStrategy` | `ValidateStrategyRequest` | `ValidateStrategyResponse` | Validate existing strategy config |

### Version Management

| RPC | Request | Response | Description |
|-----|---------|----------|-------------|
| `ListStrategyVersions` | `ListStrategyVersionsRequest` | `ListStrategyVersionsResponse` | List versions with pagination |

---

## S-Expression DSL

The strategy service uses a Lisp-style S-expression DSL to define trading strategies. This provides a readable, declarative syntax for specifying entry/exit conditions.

### Complete Strategy Example

```scheme
(strategy
  :name "EMA Crossover with RSI Filter"
  :description "Enter on EMA crossover when RSI confirms momentum"
  :type trend_following
  :symbols ["AAPL" "MSFT" "GOOGL"]
  :timeframe "1H"
  :entry (and
           (cross-above (ema close 12) (ema close 26))
           (> (rsi close 14) 50))
  :exit (or
          (cross-below (ema close 12) (ema close 26))
          (< (rsi close 14) 30))
  :position-size 10
  :stop-loss-pct 2.0
  :take-profit-pct 6.0
  :max-positions 5)
```

### Syntax Elements

| Element | Syntax | Example |
|---------|--------|---------|
| **Keywords** | Colon prefix | `:name`, `:entry`, `:timeframe` |
| **Symbols** | Bare identifiers | `close`, `open`, `high`, `low`, `volume` |
| **Numbers** | Integers or floats | `42`, `3.14`, `-5` |
| **Strings** | Double-quoted | `"AAPL"`, `"My Strategy"` |
| **Booleans** | Lowercase | `true`, `false` |
| **Vectors** | Square brackets | `["AAPL" "MSFT" "GOOGL"]` |
| **Function calls** | Parentheses | `(sma close 20)` |
| **Comments** | Semicolon | `; this is a comment` |

### Strategy Fields

#### Required Fields

| Field | Type | Description |
|-------|------|-------------|
| `:name` | string | Strategy name |
| `:symbols` | vector | List of ticker symbols |
| `:timeframe` | string | Bar timeframe: `1m`, `5m`, `15m`, `30m`, `1H`, `4H`, `1D`, `1W`, `1M` |
| `:entry` | expression | Boolean condition for entry |
| `:exit` | expression | Boolean condition for exit |

#### Optional Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `:description` | string | `""` | Strategy description |
| `:type` | symbol | `custom` | `trend_following`, `mean_reversion`, `momentum`, `breakout`, `custom` |
| `:position-size` | number | `10` | Percent of equity per position |
| `:sizing-type` | symbol | `percent-equity` | `percent-equity`, `fixed-quantity`, `risk-based` |
| `:stop-loss-pct` | number | none | Stop loss percentage (0-100] |
| `:take-profit-pct` | number | none | Take profit percentage (0-1000] |
| `:trailing-stop-pct` | number | none | Trailing stop percentage (0-50] |
| `:max-positions` | number | none | Maximum concurrent positions |

### Technical Indicators

20+ indicators organized by category:

#### Trend Indicators

| Indicator | Syntax | Parameters | Outputs |
|-----------|--------|------------|---------|
| SMA | `(sma source period)` | period: int | value |
| EMA | `(ema source period)` | period: int | value |
| MACD | `(macd source fast slow signal :output)` | fast, slow, signal: int | `:line`, `:signal`, `:histogram` |
| ADX | `(adx source period :output)` | period: int | `:value`, `:plus_di`, `:minus_di` |

#### Momentum Indicators

| Indicator | Syntax | Parameters | Outputs |
|-----------|--------|------------|---------|
| RSI | `(rsi source period)` | period: int | value |
| Stochastic | `(stoch source k d smooth :output)` | k, d, smooth: int | `:k`, `:d` |
| CCI | `(cci source period)` | period: int | value |
| Williams %R | `(williams-r source period)` | period: int | value |
| MFI | `(mfi source period)` | period: int | value |

#### Volatility Indicators

| Indicator | Syntax | Parameters | Outputs |
|-----------|--------|------------|---------|
| Bollinger Bands | `(bbands source period std :output)` | period, std: number | `:upper`, `:middle`, `:lower` |
| ATR | `(atr source period)` | period: int | value |
| Keltner Channel | `(keltner source ema_period atr_mult :output)` | ema_period, atr_mult: number | `:upper`, `:middle`, `:lower` |
| Standard Deviation | `(stddev source period)` | period: int | value |

#### Volume Indicators

| Indicator | Syntax | Parameters | Outputs |
|-----------|--------|------------|---------|
| OBV | `(obv)` | none | value |
| VWAP | `(vwap)` | none | value |
| Donchian | `(donchian source period :output)` | period: int | `:upper`, `:lower` |

### Operators

#### Comparison Operators

```scheme
(> (rsi close 14) 70)     ; RSI greater than 70
(< close 100)             ; Close less than 100
(>= volume 1000000)       ; Volume at least 1M
(<= (atr close 14) 2.5)   ; ATR at most 2.5
(= (position-side) "long") ; Position is long
(!= status "closed")      ; Status not closed
```

#### Logical Operators

```scheme
(and (> rsi 70) (< volume 1000000))   ; Both conditions
(or (> close 100) (< close 50))       ; Either condition
(not (has-position))                   ; Negation
```

#### Crossover Operators

```scheme
(cross-above (ema close 12) (ema close 26))  ; Fast EMA crosses above slow
(cross-below (sma close 20) 100)             ; SMA crosses below threshold
```

#### Arithmetic Operators

```scheme
(+ close open)                    ; Addition
(- close (sma close 20))          ; Subtraction
(* (atr close 14) 2)              ; Multiplication
(/ (- close open) open)           ; Division (percent change)
(abs (- close open))              ; Absolute value
(min close open)                  ; Minimum
(max high low)                    ; Maximum
```

### Special Functions

```scheme
; Historical lookback
(prev close 1)              ; Previous bar's close
(prev (rsi close 14) 5)     ; RSI from 5 bars ago

; Position queries
(has-position)              ; Boolean: holding a position?
(position-side)             ; Returns "long" or "short"
(position-pnl-pct)          ; Percent gain/loss on position

; Time filters
(time-between "09:30" "16:00")  ; Current time in range?
(day-of-week 0 1 2 3 4)         ; Weekday? (0=Monday)
(market-hours)                   ; During market hours?
```

### Example Strategies

#### Mean Reversion with Bollinger Bands

```scheme
(strategy
  :name "Bollinger Mean Reversion"
  :type mean_reversion
  :symbols ["AAPL"]
  :timeframe "1D"
  :entry (and
           (< close (bbands close 20 2 :lower))
           (< (rsi close 14) 30))
  :exit (or
          (> close (bbands close 20 2 :middle))
          (> (rsi close 14) 50))
  :risk {:stop-loss-pct 3 :take-profit-pct 6})
```

#### Trend Following with ADX Filter

```scheme
(strategy
  :name "Trend Following"
  :type trend_following
  :symbols ["SPY"]
  :timeframe "1D"
  :entry (and
           (> close (sma close 50))
           (> (sma close 20) (sma close 50))
           (> (adx close 14) 25))
  :exit (or
          (< close (- (sma close 20) (* (atr close 14) 2)))
          (< (adx close 14) 20)))
```

#### Z-Score Mean Reversion

```scheme
(strategy
  :name "Z-Score Mean Reversion"
  :symbols ["SPY"]
  :timeframe "1D"
  :entry (< (/ (- close (sma close 20)) (stddev close 20)) -2)
  :exit (> (/ (- close (sma close 20)) (stddev close 20)) 0))
```

---

## DSL Parsing Pipeline

The DSL is processed through a multi-stage pipeline:

```
Source S-expression string
    ↓
[Tokenizer] → Token stream with line/column info
    ↓
[Parser] → AST (Literal, Symbol, Keyword, FunctionCall, Strategy)
    ↓
[Validator] → ValidationResult (errors with paths)
    ↓
[to_json] → JSON dict for database storage
    ↓
PostgreSQL storage
    ↓
[from_json] → Reconstructed AST
    ↓
[serialize] → S-expression string (for UI display)
```

### AST Node Types

```python
# Five immutable AST node types (frozen dataclasses)

Literal(value)
  # value: int | float | str | bool | list
  # Represents literals and collections

Symbol(name)
  # name: str (e.g., "close", "$price", "sma")
  # References price data or variables

Keyword(name)
  # name: str (e.g., "name", "entry", "line")
  # Marker for keyword arguments

FunctionCall(name, args)
  # name: str (function/operator name)
  # args: tuple[ASTNode, ...] (arguments)
  # All operators and indicators are function calls

Strategy
  # name: str
  # symbols: list[str]
  # timeframe: str
  # entry: ASTNode (boolean condition)
  # exit: ASTNode (boolean condition)
  # description: str | None
  # strategy_type: str
  # sizing: SizingConfig
  # risk: RiskConfig
```

### JSON Storage Format

AST nodes are stored as type-tagged JSON:

```json
{
  "type": "strategy",
  "name": "EMA Crossover",
  "symbols": ["AAPL"],
  "timeframe": "1D",
  "entry": {
    "type": "function",
    "name": "cross-above",
    "args": [
      {
        "type": "function",
        "name": "ema",
        "args": [
          {"type": "symbol", "name": "close"},
          {"type": "literal", "value": 12}
        ]
      },
      {
        "type": "function",
        "name": "ema",
        "args": [
          {"type": "symbol", "name": "close"},
          {"type": "literal", "value": 26}
        ]
      }
    ]
  },
  "exit": { ... },
  "sizing": {"type": "percent-equity", "value": 10},
  "risk": {"stop_loss_pct": 2.0, "take_profit_pct": 6.0}
}
```

### Validation Rules

| Check | Requirement |
|-------|-------------|
| Name | Required, non-empty string |
| Symbols | Required, non-empty list |
| Timeframe | Must be one of: `1m`, `5m`, `15m`, `30m`, `1H`, `4H`, `1D`, `1W`, `1M` |
| Entry/Exit | Must be valid boolean expressions |
| Indicator args | Correct parameter counts for each indicator |
| Output selectors | Valid for the indicator (e.g., `:line` for MACD) |
| `stop_loss_pct` | Range (0, 100] |
| `take_profit_pct` | Range (0, 1000] |
| `trailing_stop_pct` | Range (0, 50] |
| `max_positions` | >= 1 |

---

## Compilation & Runtime Evaluation

### Phase 1: Compilation (One-Time)

When a strategy is loaded for execution:

```python
compiled = CompiledStrategy.compile(strategy_ast)
```

This performs:

1. **Indicator Extraction**: Walk entry/exit AST to find all indicator calls
2. **Lookback Calculation**: Determine minimum bars needed for warmup
3. **Cache Key Generation**: Create unique keys for each indicator (e.g., `sma_close_20`)

```python
@dataclass(frozen=True)
class IndicatorSpec:
    indicator_type: str          # "sma", "ema", "rsi", etc.
    source: str                  # "close", "high", "low", "open", "volume"
    params: tuple[int|float, ...]  # (period,) or (fast, slow, signal)
    output_key: str              # Cache key: "sma_close_20"
    output_field: str | None     # For multi-output: "line", "signal", "upper"
    required_bars: int           # Minimum historical bars needed
```

### Phase 2: Bar-by-Bar Evaluation

For each new bar:

```python
def evaluate(self, bar: Bar) -> list[Signal]:
    # 1. Add bar to history
    self.add_bar(bar)

    # 2. Check warmup period
    if not self.has_enough_history():
        return []  # Not enough data yet

    # 3. Build evaluation state (compute ALL indicators)
    state = self._build_state()

    # 4. Evaluate conditions based on position
    if not state.has_position():
        if evaluate_entry(state, self.strategy.entry):
            return [create_entry_signal(bar)]
    else:
        if evaluate_exit(state, self.strategy.exit):
            return [create_exit_signal(bar)]
        # Also check risk-based exits
        risk_signal = self._check_risk_exits(state, bar)
        if risk_signal:
            return [risk_signal]

    return []
```

### Indicator Computation

Indicators are computed from full bar history using NumPy:

```python
def _compute_indicators(self) -> dict[str, np.ndarray]:
    prices = PriceData(
        open=np.array([b.open for b in self._bar_history]),
        high=np.array([b.high for b in self._bar_history]),
        low=np.array([b.low for b in self._bar_history]),
        close=np.array([b.close for b in self._bar_history]),
        volume=np.array([b.volume for b in self._bar_history]),
    )
    return compute_all_indicators(self.indicators, prices)
```

Result format:

```python
{
    "sma_close_20": np.array([NaN, NaN, ..., 105.2, 105.8, 106.1]),
    "rsi_close_14": np.array([NaN, NaN, ..., 55.2, 58.1, 62.3]),
    "macd_close_12_26_9_line": np.array([NaN, ..., 1.2, 1.5, 1.8]),
}
```

### Evaluation State

The state object provides access to all data needed for condition evaluation:

```python
@dataclass
class EvaluationState:
    current_bar: Bar              # Latest OHLCV bar
    prev_bar: Bar                 # Previous bar (for crossovers)
    indicators: dict[str, np.ndarray]  # All computed indicators
    position: Position | None     # Current position info
    bar_history: list[Bar]        # Full history for lookbacks
```

Key methods:

| Method | Returns | Purpose |
|--------|---------|---------|
| `get_value("close")` | `float` | Current bar's close price |
| `get_prev_value("close")` | `float` | Previous bar's close price |
| `get_indicator("sma_close_20")` | `float` | Current SMA value (last element) |
| `get_indicator_array("sma_close_20")` | `np.ndarray` | Full array for crossover detection |
| `has_position()` | `bool` | Entry vs exit gating |
| `position_pnl_pct()` | `float` | For risk-based exits |

### Crossover Detection

Crossovers compare **current** and **previous** values:

```python
def _evaluate_crossover(name: str, left: ASTNode, right: ASTNode, state: EvaluationState) -> bool:
    # Current values (indicator[-1] or current_bar)
    left_curr = resolve_value(left, state)
    right_curr = resolve_value(right, state)

    # Previous values (indicator[-2] or prev_bar)
    left_prev = get_prev_value(left, state)
    right_prev = get_prev_value(right, state)

    if name == "cross-above":
        return left_prev <= right_prev and left_curr > right_curr

    if name == "cross-below":
        return left_prev >= right_prev and left_curr < right_curr
```

Example:

```
Bar 100: SMA(20)=105.2, SMA(50)=106.0  → 105.2 <= 106.0 ✓
Bar 101: SMA(20)=106.5, SMA(50)=106.1  → 106.5 > 106.1 ✓

cross-above triggered! (was below, now above)
```

### Signal Generation

When conditions evaluate to `True`:

```python
Signal(
    type=SignalType.BUY,
    symbol="AAPL",
    price=116.50,                    # Bar close
    timestamp=datetime(...),
    quantity_percent=10.0,           # From strategy sizing
    stop_loss=114.20,                # If risk.stop_loss_pct=2.0
    take_profit=123.50,              # If risk.take_profit_pct=6.0
    metadata={
        "strategy_name": "EMA Crossover",
        "exit_reason": "condition"   # or "stop_loss", "take_profit"
    }
)
```

### Risk-Based Exits

Checked every bar when in a position:

```python
def _check_risk_exits(self, state: EvaluationState, bar: Bar) -> Signal | None:
    pnl_pct = state.position_pnl_pct()

    # Stop loss
    if stop_loss_pct and pnl_pct <= -stop_loss_pct:
        return Signal(type=CLOSE_LONG, metadata={"exit_reason": "stop_loss"})

    # Take profit
    if take_profit_pct and pnl_pct >= take_profit_pct:
        return Signal(type=CLOSE_LONG, metadata={"exit_reason": "take_profit"})
```

---

## Technical Indicator Implementations

All indicators are implemented using NumPy for vectorized computation.

### Trend Indicators (`indicators/trend.py`)

#### Simple Moving Average (SMA)

```python
def _sma(values: np.ndarray, period: int) -> np.ndarray:
    result = np.full(len(values), np.nan)
    for i in range(period - 1, len(values)):
        result[i] = np.mean(values[i - period + 1:i + 1])
    return result
```

#### Exponential Moving Average (EMA)

```python
def _ema(values: np.ndarray, period: int) -> np.ndarray:
    result = np.full(len(values), np.nan)
    multiplier = 2 / (period + 1)

    # Initialize with SMA
    result[period - 1] = np.mean(values[:period])

    # Calculate EMA
    for i in range(period, len(values)):
        result[i] = (values[i] - result[i-1]) * multiplier + result[i-1]

    return result
```

#### MACD

Returns three arrays: line, signal, histogram

```python
def _macd(values: np.ndarray, fast: int, slow: int, signal: int) -> tuple:
    fast_ema = _ema(values, fast)
    slow_ema = _ema(values, slow)
    macd_line = fast_ema - slow_ema
    signal_line = _ema(macd_line, signal)
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram
```

### Momentum Indicators (`indicators/momentum.py`)

#### RSI (Relative Strength Index)

```python
def _rsi(values: np.ndarray, period: int) -> np.ndarray:
    deltas = np.diff(values)
    gains = np.where(deltas > 0, deltas, 0)
    losses = np.where(deltas < 0, -deltas, 0)

    avg_gain = _ema(gains, period)
    avg_loss = _ema(losses, period)

    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi
```

#### Stochastic Oscillator

```python
def _stochastic(high: np.ndarray, low: np.ndarray, close: np.ndarray,
                k_period: int, d_period: int, smooth: int) -> tuple:
    lowest_low = rolling_min(low, k_period)
    highest_high = rolling_max(high, k_period)

    raw_k = 100 * (close - lowest_low) / (highest_high - lowest_low)
    k = _sma(raw_k, smooth)  # Smoothed %K
    d = _sma(k, d_period)    # %D (signal line)

    return k, d
```

### Volatility Indicators (`indicators/volatility.py`)

#### Bollinger Bands

```python
def _bollinger_bands(values: np.ndarray, period: int, std_mult: float) -> tuple:
    middle = _sma(values, period)
    std = rolling_std(values, period)
    upper = middle + (std * std_mult)
    lower = middle - (std * std_mult)
    return upper, middle, lower
```

#### ATR (Average True Range)

```python
def _atr(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int) -> np.ndarray:
    tr1 = high - low
    tr2 = np.abs(high - np.roll(close, 1))
    tr3 = np.abs(low - np.roll(close, 1))
    true_range = np.maximum(tr1, np.maximum(tr2, tr3))
    return _ema(true_range, period)
```

### Volume Indicators (`indicators/volume.py`)

#### OBV (On-Balance Volume)

```python
def _obv(close: np.ndarray, volume: np.ndarray) -> np.ndarray:
    direction = np.sign(np.diff(close))
    direction = np.insert(direction, 0, 0)
    return np.cumsum(direction * volume)
```

#### VWAP (Volume-Weighted Average Price)

```python
def _vwap(high: np.ndarray, low: np.ndarray, close: np.ndarray,
          volume: np.ndarray) -> np.ndarray:
    typical_price = (high + low + close) / 3
    return np.cumsum(typical_price * volume) / np.cumsum(volume)
```

---

## Strategy Templates

The template service provides 10 pre-built strategies:

| Template | Type | Difficulty | Description |
|----------|------|------------|-------------|
| `ma_crossover` | Trend Following | Beginner | EMA 12/26 crossover |
| `rsi_mean_reversion` | Mean Reversion | Intermediate | RSI < 30 buy / > 70 sell |
| `macd_strategy` | Momentum | Intermediate | MACD line crosses signal |
| `bollinger_bounce` | Mean Reversion | Intermediate | Price bounces off bands |
| `atr_breakout` | Breakout | Intermediate | Volatility-based breakout |
| `triple_ema` | Trend Following | Advanced | Three EMA alignment |
| `donchian_breakout` | Breakout | Advanced | Turtle Trading style |
| `dual_momentum` | Momentum | Advanced | Relative + absolute momentum |
| `mean_reversion_zscore` | Mean Reversion | Advanced | Statistical mean reversion |
| `adx_trend` | Trend Following | Intermediate | ADX strength filter |

---

## Data Models

### Pydantic Schemas (`models.py`)

#### Enumerations

```python
class StrategyType(StrEnum):
    TREND_FOLLOWING = "trend_following"
    MEAN_REVERSION = "mean_reversion"
    MOMENTUM = "momentum"
    BREAKOUT = "breakout"
    CUSTOM = "custom"

class StrategyStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    PAUSED = "paused"
    ARCHIVED = "archived"

class DeploymentStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPED = "stopped"
    ERROR = "error"

class DeploymentEnvironment(StrEnum):
    PAPER = "paper"
    LIVE = "live"
```

#### Request Schemas

```python
class StrategyCreate(BaseModel):
    name: str
    description: str | None = None
    strategy_type: StrategyType = StrategyType.CUSTOM
    config_sexpr: str  # S-expression DSL code

class StrategyUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    status: StrategyStatus | None = None
    config_sexpr: str | None = None  # Creates new version if changed

class DeploymentCreate(BaseModel):
    strategy_id: UUID
    version: int
    environment: DeploymentEnvironment
    config_overrides: dict | None = None
```

#### Response Schemas

```python
class StrategyResponse(BaseModel):
    id: UUID
    name: str
    description: str | None
    strategy_type: StrategyType
    status: StrategyStatus
    current_version: int
    created_at: datetime
    updated_at: datetime

class StrategyDetailResponse(StrategyResponse):
    config: dict           # Parsed JSON from S-expression
    symbols: list[str]
    timeframe: str
    entry_conditions: dict
    exit_conditions: dict

class StrategyVersionResponse(BaseModel):
    version: int
    config: dict
    changelog: str | None
    created_at: datetime
    created_by: UUID | None

class ValidationResult(BaseModel):
    valid: bool
    errors: list[str]
    warnings: list[str]
```

### Database Models (`libs/db`)

```python
class Strategy(Base):
    """Trading strategy definition."""
    __tablename__ = "strategies"

    id: UUID
    tenant_id: UUID
    name: str
    description: str | None
    strategy_type: str
    status: str                    # draft, active, paused, archived
    current_version: int
    created_at: datetime
    updated_at: datetime
    created_by: UUID | None

class StrategyVersion(Base):
    """Version history for strategies."""
    __tablename__ = "strategy_versions"

    id: UUID
    strategy_id: UUID              # FK to Strategy
    version: int                   # 1, 2, 3, ...
    config: dict                   # JSONB - parsed S-expression
    config_sexpr: str              # Original S-expression text
    changelog: str | None
    created_at: datetime
    created_by: UUID | None

class StrategyDeployment(Base):
    """Deployment of strategy version to paper/live."""
    __tablename__ = "strategy_deployments"

    id: UUID
    tenant_id: UUID
    strategy_id: UUID
    strategy_version: int
    environment: str               # paper, live
    status: str                    # pending, running, paused, stopped, error
    config_overrides: dict | None  # JSONB
    started_at: datetime | None
    stopped_at: datetime | None
    error_message: str | None
```

---

## Multi-Tenancy

All operations are tenant-scoped:

1. **JWT Token**: Contains `tenant_id` in payload
2. **Context Propagation**: All gRPC calls include `TenantContext`
3. **Database Queries**: Every query filters by `tenant_id`
4. **Validation**: `_validate_tenant_context()` rejects nil UUIDs

Example:

```python
async def _get_strategy_by_id(self, tenant_id: UUID, strategy_id: UUID) -> Strategy | None:
    stmt = (
        select(Strategy)
        .where(Strategy.id == strategy_id)
        .where(Strategy.tenant_id == tenant_id)  # Tenant isolation
    )
    result = await self.db.execute(stmt)
    return result.scalar_one_or_none()
```

---

## Internal Service Connections

### Services That Call Strategy

| Service | Use Case | Method |
|---------|----------|--------|
| **Frontend** | Strategy builder, management | All RPCs |
| **Backtest** | Load strategy for simulation | `GetStrategy`, `CompileStrategy` |
| **Trading** | Load strategy for live execution | `GetStrategy` |

### Shared Libraries Used

| Library | Import | Purpose |
|---------|--------|---------|
| `llamatrade_dsl` | `from llamatrade_dsl import parse_strategy, validate_strategy` | DSL parsing & validation |
| `llamatrade_compiler` | `from llamatrade_compiler import CompiledStrategy` | Runtime execution |
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

## Complete Data Flow Example

**Scenario: User creates and backtests a strategy**

### 1. Strategy Creation

```
Frontend: CreateStrategy({
  name: "My EMA Strategy",
  config_sexpr: "(strategy :name \"My EMA\" :symbols [\"AAPL\"] ...)"
})
    ↓
StrategyServicer.create_strategy()
    ↓
StrategyService.create_strategy()
    ├→ parse_strategy(config_sexpr) → Strategy AST
    ├→ validate_strategy(ast) → ValidationResult
    ├→ to_json(ast) → JSON dict
    ├→ INSERT Strategy (status=draft, version=1)
    └→ INSERT StrategyVersion (version=1, config=JSON)
    ↓
Return StrategyDetailResponse
```

### 2. Strategy Compilation (Backtest Service)

```
Backtest: GetStrategy(strategy_id)
    ↓
StrategyServicer.get_strategy()
    ↓
Return strategy with config JSON
    ↓
Backtest: from_json(config) → Strategy AST
    ↓
CompiledStrategy.compile(strategy)
    ├→ extract_indicators(strategy) → [IndicatorSpec, ...]
    ├→ get_max_lookback(indicators) → 51 bars
    └→ CompiledStrategy ready
```

### 3. Runtime Evaluation (Backtest Loop)

```
for bar in historical_bars:
    ↓
    compiled.add_bar(bar)
    ↓
    if len(bar_history) < 51:
        continue  # Warmup period
    ↓
    _compute_indicators()
        ├→ prices = PriceData(open, high, low, close, volume)
        └→ for spec in indicators:
            └→ compute_indicator(spec, prices)
    ↓
    state = EvaluationState(current_bar, prev_bar, indicators, position)
    ↓
    if not has_position():
        if evaluate_condition(entry_ast, state):
            signals.append(BUY signal)
    else:
        if evaluate_condition(exit_ast, state):
            signals.append(CLOSE signal)
        elif check_risk_exits(state):
            signals.append(CLOSE signal)
    ↓
    Execute signals, update position
```

---

## Key Design Patterns

| Pattern | Where | Purpose |
|---------|-------|---------|
| **Dependency Injection** | FastAPI `Depends()` | Clean service instantiation |
| **Service Layer** | `services/*` | Separation of concerns |
| **Repository Pattern** | `StrategyService._get_strategy_by_id()` | DB abstraction |
| **Strategy Pattern** | `BaseStrategy` subclasses | Pluggable implementations |
| **Immutable AST** | Frozen dataclasses | Prevent accidental mutation |
| **Type-Tagged JSON** | `to_json()`/`from_json()` | Preserve node types in storage |
| **Vectorization** | `pipeline.py` | High-performance NumPy computation |
| **Proto Mapping** | `servicer.py` helpers | Protobuf ↔ Python conversion |

---

## Performance Considerations

### Current Implementation

- **Indicator Caching**: None — indicators are recomputed from scratch every bar
- **Bar History**: Unbounded list, grows every evaluation
- **Position Tracking**: Single position per strategy

### Optimization Opportunities

1. **Incremental Indicator Updates**: Only compute delta for new bar
2. **Rolling Windows**: Limit bar history to `max_lookback + buffer`
3. **Vectorized Backtesting**: Compute all signals at once using boolean arrays

---

## Summary

The strategy service provides a complete strategy management system with:

1. **DSL-Driven Strategies**: Readable S-expression syntax for non-programmers
2. **Comprehensive Validation**: Parse-time and semantic validation with clear errors
3. **Version Control**: Full version history for audit and rollback
4. **20+ Technical Indicators**: NumPy-based computation for performance
5. **Runtime Evaluation**: Bar-by-bar signal generation with crossover detection
6. **Risk Management**: Stop loss, take profit, trailing stops
7. **Multi-Tenancy**: Complete tenant isolation via context propagation
8. **Template Library**: 10 pre-built strategies for quick start
9. **Clean API**: gRPC/Connect protocol for type-safe communication

Architecture separates concerns: Servicer (gRPC) → Service (business logic) → DSL (parsing/validation) → Compiler (execution) → Database (persistence).

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

Validation errors are returned in `ValidationResult`:

```python
ValidationResult(
    valid=False,
    errors=[
        "Missing required field: :symbols",
        "Invalid timeframe '1X', must be one of: 1m, 5m, 15m, 30m, 1H, 4H, 1D, 1W, 1M",
        "Indicator 'sma' requires 2 arguments, got 1",
    ],
    warnings=[
        "Position size 50% may be too aggressive",
    ],
)
```

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
├── conftest.py                 # Shared fixtures (~5300 lines)
├── test_base_strategy.py       # Base strategy class tests
├── test_grpc_servicer.py       # gRPC endpoint tests (~42k lines)
├── test_health.py              # Health check tests
├── test_indicator_service.py   # Indicator metadata tests
├── test_strategy_service.py    # Strategy CRUD tests (~40k lines)
└── test_template_service.py    # Template library tests
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

---

## Current Implementation Status

> **Project Stage:** Early Development

### What's Real (Implemented) ✓

- [x] **gRPC/Connect Endpoints**: CreateStrategy, GetStrategy, ListStrategies, UpdateStrategy, DeleteStrategy, CompileStrategy, ValidateStrategy, ListStrategyVersions, UpdateStrategyStatus
- [x] **Strategy Service**: Full CRUD with version management
- [x] **DSL Parser**: Complete S-expression parsing (`llamatrade_dsl`)
- [x] **DSL Validator**: Semantic validation with error messages
- [x] **Indicator Library**: 20+ indicators (SMA, EMA, RSI, MACD, etc.)
- [x] **Template Service**: 10 pre-built strategy templates
- [x] **Indicator Service**: Indicator metadata (params, outputs)
- [x] **Compiler Pipeline**: Indicator extraction, lookback calculation
- [x] **Health Check**: Standard `/health` endpoint

### What's Stubbed or Partial (TODO) ✗

- [ ] **Deployment Management**: Create/track deployments to paper/live
- [ ] **Live Strategy Execution**: Connecting to trading service
- [ ] **Strategy Performance Tracking**: Historical execution metrics
- [ ] **Strategy Marketplace**: Share/discover strategies
- [ ] **Code-Based Strategies**: Python class strategies (vs DSL only)

### Known Limitations

- **Execution**: Strategies can be created and backtested but not yet live-traded
- **Indicators**: No custom indicator creation (fixed library)
- **Deployments**: Deployment tracking exists in schema but not fully implemented
