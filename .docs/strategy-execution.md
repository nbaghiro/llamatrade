# Strategy Execution Pipeline

How strategies compile, evaluate, and generate orders in LlamaTrade.

---

## Table of Contents

1. [Overview](#overview)
2. [Allocation vs Signal Model](#allocation-vs-signal-model)
3. [Compilation Pipeline](#compilation-pipeline)
4. [Branching Logic Evaluation](#branching-logic-evaluation)
5. [Rebalancing Mechanism](#rebalancing-mechanism)
6. [Weight Methods](#weight-methods)
7. [Allocation to Quantity Conversion](#allocation-to-quantity-conversion)
8. [Complete Execution Flow](#complete-execution-flow)
9. [Indicator Computation](#indicator-computation)
10. [Position Reconciliation](#position-reconciliation)
11. [Key Files Reference](#key-files-reference)

---

## Overview

LlamaTrade uses an **allocation-based model** for portfolio strategies. Instead of generating discrete buy/sell signals, strategies define target portfolio weights. The system then:

1. Compiles the DSL into an executable form
2. Evaluates conditions using current market data
3. Computes target allocations (percentage weights)
4. Converts percentages to share quantities
5. Generates orders to reach target positions

This approach is fundamentally different from traditional signal-based systems and is better suited for portfolio management strategies.

---

## Allocation vs Signal Model

### Traditional Signal Model

```
"Buy 100 shares of AAPL when RSI > 70"
     │
     ▼
  Fixed quantity order
```

- Generates discrete buy/sell signals with fixed quantities
- Doesn't consider current portfolio state
- Requires manual position sizing

### LlamaTrade Allocation Model

```
"Allocate 60% to AAPL when RSI > 70"
     │
     ▼
  System calculates:
  • Current portfolio equity
  • Target position value (equity × 60%)
  • Required shares (target value / price)
  • Delta from current position
     │
     ▼
  Order to reach target
```

- Defines target portfolio weights
- Automatically handles position sizing
- Rebalances to maintain targets
- Multi-asset aware

---

## Compilation Pipeline

### DSL to Executable Function

```
┌─────────────────────────────────────────────────────────────────────────┐
│  STRATEGY DEFINITION (S-expression DSL)                                 │
│                                                                         │
│  (strategy "Tactical 60/40"                                             │
│    :rebalance monthly                                                   │
│    (if (> (sma SPY 50) (sma SPY 200))                                   │
│      (weight :method specified                                          │
│        (asset VTI :weight 60)                                           │
│        (asset BND :weight 40))                                          │
│      (else                                                              │
│        (weight :method specified                                        │
│          (asset VTI :weight 20)                                         │
│          (asset BND :weight 80)))))                                     │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼ Parse (libs/dsl)
┌─────────────────────────────────────────────────────────────────────────┐
│  ABSTRACT SYNTAX TREE                                                   │
│                                                                         │
│  StrategyNode                                                           │
│  ├── name: "Tactical 60/40"                                             │
│  ├── metadata: { rebalance: "monthly" }                                 │
│  └── root: ConditionalNode                                              │
│           ├── condition: ComparisonNode(">", SMA(SPY,50), SMA(SPY,200)) │
│           ├── then_block: WeightNode(specified, [VTI:60, BND:40])       │
│           └── else_block: WeightNode(specified, [VTI:20, BND:80])       │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼ Compile (libs/compiler)
┌─────────────────────────────────────────────────────────────────────────┐
│  COMPILED STRATEGY                                                      │
│                                                                         │
│  CompiledStrategy                                                       │
│  ├── symbols: [VTI, BND, SPY]                                           │
│  ├── rebalance_frequency: MONTHLY                                       │
│  ├── indicators: [SMA(SPY,50), SMA(SPY,200)]                            │
│  ├── min_bars: 200  (warmup period)                                     │
│  └── evaluate: callable(state) → {VTI: 60, BND: 40}                     │
└─────────────────────────────────────────────────────────────────────────┘
```

### Compilation Steps

1. **Parse**: Lark parser converts S-expression text to AST nodes
2. **Validate**: Check required fields, weight sums, symbol validity
3. **Extract Indicators**: Identify all technical indicators needed
4. **Calculate Min Bars**: Determine warmup period from indicator lookbacks
5. **Build Evaluator**: Create callable function for runtime evaluation

---

## Branching Logic Evaluation

### Condition Types

```python
# Comparisons
(> value1 value2)      # Greater than
(< value1 value2)      # Less than
(>= value1 value2)     # Greater or equal
(<= value1 value2)     # Less or equal
(= value1 value2)      # Equal
(!= value1 value2)     # Not equal

# Crossovers (detect when lines cross)
(crosses-above fast slow)   # Fast line crosses above slow
(crosses-below fast slow)   # Fast line crosses below slow

# Logical operators
(and cond1 cond2 ...)  # All must be true
(or cond1 cond2 ...)   # Any must be true
(not cond)             # Negation
```

### Value Types

| Type | Example | Description |
|------|---------|-------------|
| Price | `(close SPY)` | Current bar OHLCV field |
| Indicator | `(rsi SPY 14)` | Technical indicator value |
| Metric | `(drawdown)` | Portfolio metric |
| Literal | `70` | Numeric constant |

### Evaluation Example

```lisp
(if (and (> (rsi SPY 14) 70)
         (crosses-below (sma SPY 10) (sma SPY 50)))
  ;; Overbought + death cross = go defensive
  (weight :method equal (asset TLT) (asset GLD))
  (else
    ;; Normal conditions = stay in equities
    (weight :method equal (asset SPY) (asset QQQ))))
```

**Evaluation steps:**

```
Step 1: Compute RSI(SPY, 14) → 72.5
Step 2: Compare 72.5 > 70 → TRUE

Step 3: Compute SMA(SPY, 10) → 445.20
Step 4: Compute SMA(SPY, 50) → 448.30
Step 5: Check crossover:
        Previous: fast=446.10, slow=447.90 → fast < slow
        Current:  fast=445.20, slow=448.30 → fast < slow
        No crossover (both periods have fast < slow)
        → FALSE

Step 6: AND(TRUE, FALSE) → FALSE
Step 7: Select else_block → {SPY: 50%, QQQ: 50%}
```

### Crossover Detection

Crossovers require comparing current AND previous bar values:

```python
def crosses_above(fast_curr, fast_prev, slow_curr, slow_prev) -> bool:
    """Fast line crosses above slow line."""
    was_below = fast_prev <= slow_prev
    is_above = fast_curr > slow_curr
    return was_below and is_above

def crosses_below(fast_curr, fast_prev, slow_curr, slow_prev) -> bool:
    """Fast line crosses below slow line."""
    was_above = fast_prev >= slow_prev
    is_below = fast_curr < slow_curr
    return was_above and is_below
```

---

## Rebalancing Mechanism

### Frequency Options

Rebalancing is **periodic**, not event-driven. Strategies only generate orders on rebalance days.

| Frequency | Trigger |
|-----------|---------|
| `daily` | Every trading day |
| `weekly` | Every Monday |
| `monthly` | First trading day of month |
| `quarterly` | First trading day of quarter |
| `annually` | First trading day of year |

### Rebalance Check Logic

```python
def should_rebalance(current_date: date, last_rebalance: date, frequency: str) -> bool:
    # Never rebalance twice on same day
    if last_rebalance == current_date:
        return False

    match frequency:
        case "daily":
            return True
        case "weekly":
            return current_date.weekday() == 0  # Monday
        case "monthly":
            return current_date.month != last_rebalance.month
        case "quarterly":
            curr_quarter = (current_date.month - 1) // 3
            last_quarter = (last_rebalance.month - 1) // 3
            return curr_quarter != last_quarter
        case "annually":
            return current_date.year != last_rebalance.year
```

### Non-Rebalance Days

On non-rebalance days, the strategy evaluation returns `None` (no signal). The existing positions are held unchanged.

```
Monday (rebalance day):    Evaluate strategy → Generate orders
Tuesday:                   Skip evaluation → Hold positions
Wednesday:                 Skip evaluation → Hold positions
...
Next Monday:               Evaluate strategy → Rebalance if needed
```

---

## Weight Methods

The `weight` block determines how allocations are distributed among child assets.

### Method: `specified`

Use explicit weights on each asset. Weights must sum to 100%.

```lisp
(weight :method specified
  (asset AAPL :weight 40)
  (asset MSFT :weight 35)
  (asset TSLA :weight 25))
```

### Method: `equal`

Divide equally among all children.

```lisp
(weight :method equal
  (asset AAPL)    ;; 33.3%
  (asset MSFT)    ;; 33.3%
  (asset TSLA))   ;; 33.3%
```

### Method: `momentum`

Weight by recent price performance. Higher momentum = higher weight.

```lisp
(weight :method momentum :lookback 90 :top 3
  (asset XLK)
  (asset XLF)
  (asset XLE)
  (asset XLV)
  (asset XLI))
```

**Parameters:**
- `:lookback` - Period for calculating returns (default: 90 days)
- `:top` - Select only top N performers (optional)

**Implementation:**

```python
def compute_momentum_weights(symbols, state, lookback=90, top=None):
    scores = {}
    for symbol in symbols:
        bars = state.bar_history[symbol]
        if len(bars) >= lookback:
            start_price = bars[-lookback].close
            end_price = bars[-1].close
            scores[symbol] = (end_price - start_price) / start_price

    # Rank by momentum, select top K if specified
    ranked = sorted(symbols, key=lambda s: scores.get(s, 0), reverse=True)
    selected = ranked[:top] if top else ranked

    # Equal weight among selected
    weight = 100.0 / len(selected) if selected else 0
    return {s: weight for s in selected}
```

### Method: `inverse-volatility`

Weight inversely by volatility. Lower volatility = higher weight.

```lisp
(weight :method inverse-volatility :lookback 60
  (asset VTI)
  (asset TLT)
  (asset GLD))
```

**Implementation:**

```python
def compute_inverse_vol_weights(symbols, state, lookback=60):
    volatilities = {}
    for symbol in symbols:
        bars = state.bar_history[symbol]
        returns = [bars[i].close / bars[i-1].close - 1
                   for i in range(1, min(len(bars), lookback))]
        volatilities[symbol] = np.std(returns) if returns else 1.0

    # Inverse volatility
    inv_vols = {s: 1/v for s, v in volatilities.items()}
    total = sum(inv_vols.values())

    return {s: (iv / total) * 100 for s, iv in inv_vols.items()}
```

### Method: `risk-parity`

Equal risk contribution from each asset. Currently implemented as inverse-volatility.

```lisp
(weight :method risk-parity :lookback 60
  (asset SPY)
  (asset TLT)
  (asset GLD)
  (asset DBC))
```

---

## Allocation to Quantity Conversion

### The Core Formula

```python
# For each symbol in target allocation
target_weight = allocation["weights"].get(symbol, 0.0)  # e.g., 60.0
current_price = latest_bar.close                         # e.g., $220
portfolio_equity = account_equity                        # e.g., $100,000

# Calculate target position value
target_value = portfolio_equity * (target_weight / 100)  # $100k × 0.60 = $60k

# Convert to share count
target_shares = target_value / current_price             # $60k / $220 = 272.7
```

### Signal Generation Logic

```python
def generate_signals(allocation, positions, equity, prices):
    signals = []

    for symbol, target_weight in allocation["weights"].items():
        current_price = prices[symbol]
        current_position = positions.get(symbol)
        has_position = current_position is not None and current_position.quantity > 0

        if target_weight > 0 and not has_position:
            # NEW POSITION: Buy to reach target
            target_value = equity * (target_weight / 100)
            quantity = target_value / current_price
            signals.append(Signal(
                type="buy",
                symbol=symbol,
                quantity=quantity,
                price=current_price
            ))

        elif target_weight == 0 and has_position:
            # EXIT POSITION: Sell entire holding
            signals.append(Signal(
                type="sell",
                symbol=symbol,
                quantity=current_position.quantity,
                price=current_price
            ))

        elif target_weight > 0 and has_position:
            # REBALANCE: Adjust to target
            current_value = current_position.quantity * current_price
            target_value = equity * (target_weight / 100)
            delta_value = target_value - current_value
            delta_shares = delta_value / current_price

            # Only rebalance if drift exceeds threshold (e.g., 5%)
            drift_pct = abs(delta_value) / target_value * 100
            if drift_pct > 5:
                signal_type = "buy" if delta_shares > 0 else "sell"
                signals.append(Signal(
                    type=signal_type,
                    symbol=symbol,
                    quantity=abs(delta_shares),
                    price=current_price
                ))

    return signals
```

### Concrete Example: Monthly Rebalancing

**Strategy:** 60/40 VTI/BND, monthly rebalance

**Month 1 (Initial):**

```
Portfolio equity: $100,000
VTI price: $220
BND price: $75

Target allocations:
  VTI: 60% = $60,000 → $60,000 / $220 = 272 shares
  BND: 40% = $40,000 → $40,000 / $75 = 533 shares

Orders generated:
  BUY 272 VTI @ $220
  BUY 533 BND @ $75
```

**Month 2 (Prices changed, need rebalance):**

```
VTI: $240 (+9%)
BND: $72 (-4%)

Current positions:
  VTI: 272 shares × $240 = $65,280 (61.8% of portfolio)
  BND: 533 shares × $72 = $38,376 (36.3% of portfolio)
  Cash: ~$2,000
  Total equity: $105,656

New target allocations:
  VTI: 60% = $63,394 → need 264 shares (have 272, sell 8)
  BND: 40% = $42,262 → need 587 shares (have 533, buy 54)

Orders generated:
  SELL 8 VTI @ $240  (reduce overweight equity)
  BUY 54 BND @ $72   (add to underweight bonds)
```

---

## Complete Execution Flow

### Live Trading Pipeline

```
┌─────────────────────────────────────────────────────────────────────────┐
│  1. BAR RECEIVED (from Alpaca WebSocket)                                │
│     BarData { symbol: "SPY", close: 445.20, volume: 1234567, ... }      │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  2. CHECK REBALANCE SCHEDULE                                            │
│     Is today a rebalance day? (based on frequency setting)              │
│     If NO → return None (hold existing positions)                       │
└─────────────────────────────────────────────────────────────────────────┘
                                    │ YES
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  3. BUILD EVALUATION STATE                                              │
│     • bar_history[symbol] → deque of recent bars                        │
│     • indicators[SMA_SPY_50] → pre-computed values                      │
│     • current_prices[symbol] → latest close                             │
│     • positions[symbol] → current holdings                              │
│     • equity → account value                                            │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  4. EVALUATE STRATEGY CONDITIONS                                        │
│     Walk AST, resolve indicator values, evaluate comparisons            │
│     Returns: selected allocation block (then or else branch)            │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  5. COMPUTE TARGET WEIGHTS                                              │
│     Apply weight method (specified, equal, momentum, etc.)              │
│     Returns: { "VTI": 60.0, "BND": 40.0 }                               │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  6. CONVERT TO QUANTITIES                                               │
│     For each symbol:                                                    │
│       target_value = equity × (weight / 100)                            │
│       target_shares = target_value / current_price                      │
│       delta = target_shares - current_shares                            │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  7. GENERATE SIGNALS                                                    │
│     Signal(type="buy", symbol="BND", quantity=54, price=72.00)          │
│     Signal(type="sell", symbol="VTI", quantity=8, price=240.00)         │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  8. RISK CHECK                                                          │
│     RiskManager.check_order() validates:                                │
│     • Max order value                                                   │
│     • Position size limits                                              │
│     • Daily loss limits                                                 │
│     • Order rate limits                                                 │
└─────────────────────────────────────────────────────────────────────────┘
                                    │ PASSED
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  9. SUBMIT ORDERS                                                       │
│     OrderExecutor.submit_order() → Alpaca Trading API                   │
│     Track in _pending_orders                                            │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  10. PROCESS FILLS (async, via trade stream)                            │
│      Update positions when fills arrive                                 │
│      Record P&L for circuit breaker                                     │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Indicator Computation

### Supported Indicators

| Category | Indicators |
|----------|------------|
| **Trend** | SMA, EMA |
| **Momentum** | RSI, MACD, Stochastic, Momentum |
| **Volatility** | Bollinger Bands, ATR, Keltner, Standard Deviation |
| **Volume** | OBV, MFI, VWAP |
| **Directional** | ADX, Williams %R, CCI |
| **Channel** | Donchian |

### Indicator Extraction

During compilation, all indicators are extracted from the strategy AST:

```python
def extract_indicators(node) -> list[IndicatorSpec]:
    """Recursively extract all indicator references from AST."""
    indicators = []

    if isinstance(node, IndicatorNode):
        indicators.append(IndicatorSpec(
            name=node.name,
            symbol=node.symbol,
            period=node.args[0] if node.args else 14,
            params=node.args[1:] if len(node.args) > 1 else []
        ))

    # Recurse into children
    for child in get_children(node):
        indicators.extend(extract_indicators(child))

    return indicators
```

### Warmup Period

The minimum bars needed before strategy can evaluate:

```python
def calculate_min_bars(indicators: list[IndicatorSpec]) -> int:
    """Determine warmup period from indicator lookbacks."""
    max_lookback = 0

    for ind in indicators:
        if ind.name in ("sma", "ema", "rsi"):
            max_lookback = max(max_lookback, ind.period)
        elif ind.name == "macd":
            # MACD needs slow period + signal period
            max_lookback = max(max_lookback, ind.params[1] + ind.params[2])
        elif ind.name == "bbands":
            max_lookback = max(max_lookback, ind.period)

    # Add buffer for crossover detection (need previous values)
    return max_lookback + 10
```

### Caching

Indicator values are cached to avoid recomputation:

**Layer 1: Market Data Service (Redis)**
- Raw OHLCV bars
- 24-hour TTL for historical data

**Layer 2: Backtest Service (Redis)**
- Computed indicator arrays
- Compressed numpy arrays with zlib
- Key format: `bt:ind:{symbol}:{indicator}:{params_hash}:{start}:{end}`

---

## Position Reconciliation

### Periodic Sync

Every 5 minutes (configurable), the runner reconciles local positions with broker:

```python
async def reconcile_positions(self):
    """Sync local position state with broker."""
    broker_positions = await self.alpaca.get_positions()

    for symbol, local_pos in self._positions.items():
        broker_pos = broker_positions.get(symbol)

        if broker_pos is None:
            # Position exists locally but not at broker
            self._alert("Ghost position detected", symbol)
            continue

        drift = abs(local_pos.quantity - broker_pos.quantity) / local_pos.quantity

        if drift < 0.05:
            # Small drift: auto-correct
            local_pos.quantity = broker_pos.quantity
        elif drift < 0.10:
            # Medium drift: log only
            self._log("Position drift detected", symbol, drift)
        else:
            # Large drift: alert
            self._alert("Large position drift", symbol, drift)
```

### Fill-Driven Updates

Positions are primarily updated via the trade stream (fill events):

```
Alpaca WebSocket (trade stream)
        │
        ▼ FILL event
StrategyRunner._handle_fill_event()
        │
        ├─→ Update local position quantity
        ├─→ Record realized P&L (if closing)
        ├─→ Update circuit breaker metrics
        └─→ Emit alerts if needed
```

This ensures positions reflect actual broker state, not just intended orders.

---

## Key Files Reference

### Strategy Compilation

| File | Purpose |
|------|---------|
| `libs/dsl/llamatrade_dsl/parser.py` | Parse S-expression to AST |
| `libs/dsl/llamatrade_dsl/ast.py` | AST node definitions |
| `libs/compiler/llamatrade_compiler/compiled.py` | CompiledStrategy, weight methods |
| `libs/compiler/llamatrade_compiler/evaluator.py` | Evaluate conditions recursively |
| `libs/compiler/llamatrade_compiler/extractor.py` | Extract indicators from AST |
| `libs/compiler/llamatrade_compiler/pipeline.py` | Compute indicators (RSI, SMA, etc.) |

### Strategy Execution

| File | Purpose |
|------|---------|
| `services/trading/src/compiler_adapter.py` | Allocation → Signal conversion |
| `services/trading/src/runner/runner.py` | Live execution loop |
| `services/trading/src/runner/bar_stream.py` | Alpaca bar WebSocket |
| `services/trading/src/runner/trade_stream.py` | Alpaca fill WebSocket |
| `services/trading/src/risk/risk_manager.py` | Pre-trade risk checks |
| `services/trading/src/executor/order_executor.py` | Order submission |

### Data Flow Summary

```
libs/dsl (parse)
    ↓
libs/compiler (compile + evaluate)
    ↓
services/trading/compiler_adapter.py (allocation → signals)
    ↓
services/trading/runner.py (execute signals)
    ↓
services/trading/order_executor.py (submit to Alpaca)
```

---

## Related Documentation

- [Strategy DSL](strategy-dsl.md) - S-expression syntax and grammar
- [Trading Service](services/trading.md) - Order execution and risk management
- [Trading Strategies](trading-strategies.md) - Algorithmic trading concepts
- [Market Data Service](services/market-data.md) - Historical and real-time data
