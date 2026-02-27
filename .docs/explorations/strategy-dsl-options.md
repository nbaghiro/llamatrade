# Strategy/Symphony DSL Options Analysis

This document explores multiple approaches for representing trading strategies (symphonies) in LlamaTrade, comparing syntax, usability, and implementation considerations.

## Goals

1. **User-friendly** - Non-programmers can understand and modify
2. **AI-friendly** - Easy for LLMs to generate from natural language
3. **Composable** - Complex strategies from simple building blocks
4. **Backtestable** - Direct translation to execution engine
5. **Versionable** - Clean diffs for version control
6. **Extensible** - Easy to add new indicators/conditions

---

## Option 1: Lisp-like S-Expression DSL (Composer-style)

Inspired by Composer.trade, uses S-expressions for a functional, composable syntax.

### Syntax

```clojure
(defsymphony "GPU Demand Play"
  {:rebalance-frequency :weekly
   :benchmark "SPY"}

  (weight-equal
    [(asset "NVDA")
     (asset "AMD")
     (asset "INTC")
     (asset "TSM")]))

;; More complex example with conditions
(defsymphony "Momentum + Safety"
  {:rebalance-frequency :daily}

  (if (> (rsi "SPY" 14) 70)
    ;; Overbought - rotate to safety
    (weight-equal
      [(asset "TLT" :weight 0.6)
       (asset "GLD" :weight 0.4)])
    ;; Normal - momentum play
    (weight-inverse-volatility
      [(filter-top 5 :by :momentum-12m
         (universe "SP500"))])))

;; Conditional logic with multiple branches
(defsymphony "All-Weather Adaptive"
  {:rebalance-frequency :monthly}

  (cond
    ;; Bear market
    [(< (sma "SPY" 200) (price "SPY"))
     (weight-equal [(asset "TLT") (asset "GLD") (asset "SHY")])]

    ;; High volatility
    [(> (vix) 30)
     (weight-risk-parity
       [(asset "SPY" :max-weight 0.3)
        (asset "TLT")
        (asset "GLD")])]

    ;; Default bull market
    [:else
     (weight-momentum
       [(universe "FAANG")])])))

;; Entry/exit signals for active trading
(defstrategy "RSI Mean Reversion"
  {:timeframe :1h
   :symbols ["AAPL" "MSFT" "GOOGL"]}

  (on-each-bar
    (when (and (< (rsi $symbol 14) 30)
               (> (volume $symbol) (sma-volume $symbol 20)))
      (buy $symbol
        :size (percent-of-portfolio 5)
        :stop-loss (percent -2)
        :take-profit (percent 4)))

    (when (or (> (rsi $symbol 14) 70)
              (crosses-below (price $symbol) (sma $symbol 50)))
      (close-position $symbol))))
```

### Pros

- **Extremely composable** - functions nest naturally
- **AI-friendly** - clear structure for generation
- **Minimal syntax** - just parentheses, symbols, keywords
- **Homoiconic** - code is data, easy to transform
- **Familiar** - Clojure/Lisp users, and Composer users

### Cons

- **Parentheses overwhelming** - can be hard to read for non-programmers
- **Learning curve** - prefix notation is unfamiliar
- **Limited IDE support** - unless we build tooling

### Implementation

- Parser: Use a Lisp parser (e.g., `hy`, custom PEG grammar)
- Evaluator: Tree-walking interpreter or compile to Python AST
- Complexity: Medium-high

---

## Option 2: YAML-based Declarative DSL

Leverages YAML's readability with a structured schema.

### Syntax

```yaml
symphony: GPU Demand Play
version: 1
rebalance: weekly
benchmark: SPY

allocation:
  method: equal-weight
  assets:
    - NVDA
    - AMD
    - INTC
    - TSM
---
symphony: Momentum + Safety
version: 1
rebalance: daily

rules:
  - name: overbought-rotation
    when:
      indicator: rsi
      symbol: SPY
      period: 14
      operator: ">"
      value: 70
    then:
      allocation:
        method: fixed-weight
        assets:
          - symbol: TLT
            weight: 0.6
          - symbol: GLD
            weight: 0.4

  - name: default-momentum
    when: default
    then:
      allocation:
        method: inverse-volatility
        universe: SP500
        filter:
          top: 5
          by: momentum-12m
---
strategy: RSI Mean Reversion
version: 1
timeframe: 1h
symbols: [AAPL, MSFT, GOOGL]

signals:
  entry:
    conditions:
      all:
        - indicator: rsi
          period: 14
          operator: "<"
          value: 30
        - indicator: volume
          operator: ">"
          compare: sma-volume
          period: 20
    action:
      type: buy
      size: 5%
      stop_loss: -2%
      take_profit: 4%

  exit:
    conditions:
      any:
        - indicator: rsi
          period: 14
          operator: ">"
          value: 70
        - crossover:
            fast: price
            slow: sma
            period: 50
            direction: below
    action:
      type: close
```

### Pros

- **Highly readable** - even non-programmers understand
- **Great tooling** - YAML editors, linters, schema validation
- **Familiar** - DevOps, config files, Kubernetes users
- **Self-documenting** - keys describe their purpose
- **Easy diffing** - clean version control diffs

### Cons

- **Verbose** - more lines than Lisp
- **Limited expressiveness** - complex logic gets awkward
- **Nesting depth** - deeply nested YAML is hard to read
- **String-based operators** - `">"` instead of `>`

### Implementation

- Parser: Standard YAML parser + JSON Schema validation
- Evaluator: Direct interpretation of structured config
- Complexity: Low-medium

---

## Option 3: Python Builder DSL

Use Python itself with a fluent builder pattern.

### Syntax

```python
from llamatrade import Symphony, Strategy, Asset, Indicator, Condition

# Simple equal-weight symphony
gpu_symphony = (
    Symphony("GPU Demand Play")
    .rebalance(weekly)
    .benchmark("SPY")
    .equal_weight([
        Asset("NVDA"),
        Asset("AMD"),
        Asset("INTC"),
        Asset("TSM"),
    ])
)

# Conditional symphony
momentum_safety = (
    Symphony("Momentum + Safety")
    .rebalance(daily)
    .when(RSI("SPY", 14) > 70)
    .then_(
        Weight.fixed([
            Asset("TLT", weight=0.6),
            Asset("GLD", weight=0.4),
        ])
    )
    .otherwise(
        Weight.inverse_volatility(
            Universe("SP500")
            .filter_top(5, by="momentum_12m")
        )
    )
)

# Active trading strategy
rsi_reversion = (
    Strategy("RSI Mean Reversion")
    .timeframe("1h")
    .symbols(["AAPL", "MSFT", "GOOGL"])
    .entry(
        Condition.all(
            RSI() < 30,
            Volume() > SMA_Volume(20)
        ),
        Action.buy(
            size=Percent(5),
            stop_loss=Percent(-2),
            take_profit=Percent(4)
        )
    )
    .exit(
        Condition.any(
            RSI() > 70,
            Price().crosses_below(SMA(50))
        ),
        Action.close()
    )
)

# Using decorators for custom logic
@strategy("Custom Alpha")
def custom_strategy(ctx):
    if ctx.indicator("rsi", 14) < 30:
        ctx.buy(size="5%")
    elif ctx.indicator("rsi", 14) > 70:
        ctx.sell()
```

### Pros

- **Full Python power** - loops, functions, imports
- **Excellent IDE support** - autocomplete, type hints, refactoring
- **No new parser** - Python handles parsing
- **Type safety** - can use Pydantic models
- **Debugging** - standard Python debugger works
- **Familiar** - most developers know Python

### Cons

- **Requires Python knowledge** - not for non-programmers
- **Serialization challenge** - harder to store/version as text
- **Security concerns** - executing user code requires sandboxing
- **AI generation complexity** - harder to constrain output

### Implementation

- Parser: Python itself
- Evaluator: Direct execution in sandbox (RestrictedPython)
- Complexity: Medium (sandboxing is the hard part)

---

## Option 4: SQL-like Query DSL

Familiar syntax for data-oriented users.

### Syntax

```sql
CREATE SYMPHONY "GPU Demand Play"
  REBALANCE WEEKLY
  BENCHMARK 'SPY'
AS
  SELECT symbol, 1.0/COUNT(*) as weight
  FROM ASSETS('NVDA', 'AMD', 'INTC', 'TSM');

-- Conditional allocation
CREATE SYMPHONY "Momentum + Safety"
  REBALANCE DAILY
AS
  CASE
    WHEN RSI('SPY', 14) > 70 THEN
      SELECT symbol, weight FROM (
        VALUES ('TLT', 0.6), ('GLD', 0.4)
      ) AS safety(symbol, weight)
    ELSE
      SELECT symbol, INVERSE_VOL_WEIGHT(symbol) as weight
      FROM UNIVERSE('SP500')
      ORDER BY MOMENTUM(symbol, 252) DESC
      LIMIT 5
  END;

-- Active trading strategy
CREATE STRATEGY "RSI Mean Reversion"
  TIMEFRAME '1h'
  SYMBOLS ('AAPL', 'MSFT', 'GOOGL')
AS
  ON BAR:
    -- Entry signal
    INSERT INTO SIGNALS (type, symbol, size, stop_loss, take_profit)
    SELECT 'BUY', symbol, 0.05, -0.02, 0.04
    FROM CURRENT_BAR
    WHERE RSI(symbol, 14) < 30
      AND VOLUME(symbol) > SMA_VOLUME(symbol, 20);

    -- Exit signal
    INSERT INTO SIGNALS (type, symbol)
    SELECT 'CLOSE', symbol
    FROM CURRENT_BAR
    WHERE RSI(symbol, 14) > 70
       OR CROSSES_BELOW(PRICE(symbol), SMA(symbol, 50));
```

### Pros

- **Very familiar** - SQL is widely known
- **Data-oriented** - natural for portfolio selection
- **Declarative** - describes what, not how
- **Powerful filtering** - WHERE, ORDER BY, LIMIT

### Cons

- **Awkward for logic** - CASE statements get messy
- **Not great for events** - entry/exit signals feel forced
- **Verbose** - simple things take many keywords
- **Limited composability** - hard to nest queries cleanly

### Implementation

- Parser: SQL parser (sqlparse) with extensions
- Evaluator: Custom query engine or compile to pandas
- Complexity: High (SQL is complex)

---

## Option 5: Natural Language with Structured Output

Let AI interpret natural language and output structured config.

### Syntax (User Input)

```
Create a symphony that:
- Invests equally in GPU companies: NVIDIA, AMD, Intel, and TSMC
- Rebalances weekly
- Uses SPY as benchmark

---

Build a strategy that:
- Buys when RSI drops below 30 and volume is above average
- Sells when RSI goes above 70 or price crosses below 50-day moving average
- Risk: 2% stop loss, 4% take profit
- Trade AAPL, MSFT, and GOOGL on the 1-hour timeframe
```

### Structured Output (AI-generated)

```json
{
  "type": "symphony",
  "name": "GPU Demand Play",
  "rebalance": "weekly",
  "benchmark": "SPY",
  "allocation": {
    "method": "equal_weight",
    "assets": ["NVDA", "AMD", "INTC", "TSM"]
  }
}
```

### Pros

- **Most accessible** - anyone can write English
- **Flexible** - handles ambiguity gracefully
- **Future-proof** - LLMs keep improving
- **Low learning curve** - no syntax to memorize

### Cons

- **Non-deterministic** - same input may produce different output
- **Requires AI** - can't parse without LLM
- **Ambiguity** - "buy a lot" means what?
- **Editing difficulty** - can't tweak structured output directly

### Implementation

- Parser: LLM with structured output (function calling)
- Evaluator: Interpret the structured output
- Complexity: Low (leverage existing LLM)

---

## Option 6: Block/Visual DSL (Compiled to Text)

Like Scratch, Blockly, or Node-RED - visual but compiles to text.

### Visual Representation

```
┌─────────────────────────────────────────────────┐
│ Symphony: GPU Demand Play                        │
├─────────────────────────────────────────────────┤
│ ⚙️ Rebalance: [Weekly ▾]  Benchmark: [SPY    ]  │
├─────────────────────────────────────────────────┤
│                                                  │
│  ┌──────────────┐  ┌──────────────┐             │
│  │ 📊 Asset     │  │ 📊 Asset     │             │
│  │ NVDA         │  │ AMD          │             │
│  │ Weight: 25%  │  │ Weight: 25%  │             │
│  └──────────────┘  └──────────────┘             │
│                                                  │
│  ┌──────────────┐  ┌──────────────┐             │
│  │ 📊 Asset     │  │ 📊 Asset     │             │
│  │ INTC         │  │ TSM          │             │
│  │ Weight: 25%  │  │ Weight: 25%  │             │
│  └──────────────┘  └──────────────┘             │
│                                                  │
└─────────────────────────────────────────────────┘
```

### Compiled Text (any of the above DSLs)

```yaml
symphony: GPU Demand Play
rebalance: weekly
benchmark: SPY
allocation:
  method: equal-weight
  assets: [NVDA, AMD, INTC, TSM]
```

### Pros

- **Most accessible** - drag and drop
- **No syntax errors** - valid by construction
- **Visual feedback** - see the structure
- **Best for beginners** - gradual learning

### Cons

- **Web-only** - requires frontend
- **Limited expressiveness** - hard to show complex logic
- **Slower for experts** - typing is faster
- **Mobile challenges** - small screens

### Implementation

- Parser: Block editor exports to chosen DSL
- Evaluator: Use the underlying DSL's evaluator
- Complexity: High (frontend development)

---

## Option 7: Hybrid Infix Expression DSL

Custom DSL with familiar math-like infix operators.

### Syntax

```
symphony "GPU Demand Play" {
  rebalance: weekly
  benchmark: SPY

  allocate equal_weight [NVDA, AMD, INTC, TSM]
}

symphony "Momentum + Safety" {
  rebalance: daily

  if RSI(SPY, 14) > 70 {
    allocate fixed [TLT @ 60%, GLD @ 40%]
  } else {
    allocate inverse_volatility {
      top 5 from SP500 by momentum_12m
    }
  }
}

strategy "RSI Mean Reversion" {
  timeframe: 1h
  symbols: [AAPL, MSFT, GOOGL]

  entry when {
    RSI(14) < 30 AND Volume > SMA_Volume(20)
  } do {
    buy 5% of portfolio
    set stop_loss -2%
    set take_profit 4%
  }

  exit when {
    RSI(14) > 70 OR Price crosses below SMA(50)
  } do {
    close position
  }
}

-- Advanced: Define custom indicators
indicator "Squeeze" {
  bb = BollingerBands(20, 2)
  kc = KeltnerChannel(20, 1.5)

  squeeze_on = bb.lower > kc.lower AND bb.upper < kc.upper
  momentum = MACD(12, 26, 9).histogram

  return { squeeze_on, momentum }
}

strategy "TTM Squeeze" {
  timeframe: 4h

  entry when {
    Squeeze.squeeze_on becomes false AND Squeeze.momentum > 0
  } do {
    buy 10% of portfolio
  }
}
```

### Pros

- **Readable** - natural English-like flow
- **Familiar operators** - `>`, `<`, `AND`, `OR`
- **Balanced** - between power and simplicity
- **Extensible** - custom indicators fit naturally
- **AI-friendly** - clear structure for generation

### Cons

- **New syntax to learn** - not existing language
- **Custom parser needed** - more work
- **Editor support** - need to build highlighting, etc.

### Implementation

- Parser: PEG grammar (Lark, pest, nom)
- Evaluator: Compile to Python or interpret AST
- Complexity: Medium

---

## Comparison Matrix

| Aspect              | S-Expr     | YAML       | Python     | SQL      | Natural    | Visual     | Infix    |
| ------------------- | ---------- | ---------- | ---------- | -------- | ---------- | ---------- | -------- |
| **Readability**     | ⭐⭐       | ⭐⭐⭐⭐   | ⭐⭐⭐     | ⭐⭐⭐   | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ |
| **Composability**   | ⭐⭐⭐⭐⭐ | ⭐⭐       | ⭐⭐⭐⭐   | ⭐⭐     | ⭐         | ⭐⭐       | ⭐⭐⭐⭐ |
| **AI Generation**   | ⭐⭐⭐⭐   | ⭐⭐⭐⭐   | ⭐⭐⭐     | ⭐⭐⭐   | ⭐⭐⭐⭐⭐ | ⭐⭐       | ⭐⭐⭐⭐ |
| **Learning Curve**  | ⭐⭐       | ⭐⭐⭐⭐   | ⭐⭐       | ⭐⭐⭐   | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐   |
| **IDE Support**     | ⭐⭐       | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐         | ⭐⭐⭐⭐   | ⭐⭐     |
| **Expressiveness**  | ⭐⭐⭐⭐⭐ | ⭐⭐⭐     | ⭐⭐⭐⭐⭐ | ⭐⭐⭐   | ⭐⭐⭐⭐   | ⭐⭐       | ⭐⭐⭐⭐ |
| **Impl. Effort**    | Medium     | Low        | Medium     | High     | Low        | High       | Medium   |
| **Version Control** | ⭐⭐⭐⭐   | ⭐⭐⭐⭐⭐ | ⭐⭐⭐     | ⭐⭐⭐   | ⭐⭐       | ⭐⭐       | ⭐⭐⭐⭐ |

---

## Recommendation: Layered Approach

Rather than choosing one, implement a **layered architecture**:

```
┌────────────────────────────────────────────────────┐
│                   User Interfaces                  │
├──────────┬──────────┬──────────┬───────────────────┤
│  Visual  │ Natural  │  Infix   │   YAML/JSON       │
│  Editor  │ Language │   DSL    │   Direct Edit     │
│ (Blocks) │  (AI)    │ (Power)  │   (Devs)          │
└────┬─────┴────┬─────┴────┬─────┴─────────┬─────────┘
     │          │          │               │
     ▼          ▼          ▼               ▼
┌────────────────────────────────────────────────────┐
│          Canonical Internal Representation         │
│                  (Typed JSON/Protobuf)             │
│                                                    │
│  {                                                 │
│    "type": "symphony",                             │
│    "name": "...",                                  │
│    "rules": [...],                                 │
│    "allocation": {...}                             │
│  }                                                 │
└────────────────────────────────────────────────────┘
                         │
                         ▼
┌────────────────────────────────────────────────────┐
│               Execution Engine                     │
│  - Backtester                                      │
│  - Live Trading                                    │
│  - Paper Trading                                   │
└────────────────────────────────────────────────────┘
```

### Implementation Priority

1. **Phase 1: YAML DSL** (MVP)
   - Easiest to implement
   - Great tooling exists
   - Readable for most users

2. **Phase 2: Natural Language + AI**
   - Leverage LLM for generation
   - Output to YAML/JSON
   - Highest accessibility

3. **Phase 3: Infix DSL**
   - For power users
   - Better for complex logic
   - Good AI generation target

4. **Phase 4: Visual Editor**
   - Drag-and-drop frontend
   - Compiles to YAML/Infix
   - Best for onboarding

---

## Detailed Schema for Internal Representation

```typescript
// Core types
type SymphonyDef = {
  type: "symphony";
  name: string;
  version: number;
  description?: string;

  // Timing
  rebalance_frequency: "daily" | "weekly" | "monthly" | "quarterly";
  rebalance_day?: number; // 1-31 for monthly, 1-5 for weekly

  // Benchmarking
  benchmark?: string;

  // The actual logic - tree of nodes
  root: AllocationNode;
};

type StrategyDef = {
  type: "strategy";
  name: string;
  version: number;
  description?: string;

  // Universe
  symbols: string[];
  timeframe: Timeframe;

  // Signals
  entry_rules: Rule[];
  exit_rules: Rule[];

  // Risk management
  risk: RiskConfig;
};

// Allocation nodes (for symphonies)
type AllocationNode =
  | AssetNode
  | WeightNode
  | ConditionalNode
  | FilterNode
  | UniverseNode;

type AssetNode = {
  type: "asset";
  symbol: string;
  weight?: number; // 0-1, optional for equal weight
};

type WeightNode = {
  type: "weight";
  method: "equal" | "fixed" | "inverse_volatility" | "risk_parity" | "momentum";
  children: AllocationNode[];
  params?: Record<string, any>;
};

type ConditionalNode = {
  type: "conditional";
  condition: Condition;
  then_branch: AllocationNode;
  else_branch?: AllocationNode;
};

type FilterNode = {
  type: "filter";
  source: AllocationNode;
  top?: number;
  bottom?: number;
  by: string; // metric name
};

type UniverseNode = {
  type: "universe";
  name: string; // "SP500", "NASDAQ100", "custom"
  symbols?: string[]; // for custom
};

// Conditions
type Condition = {
  type: "comparison" | "and" | "or" | "not" | "crossover";
  // ... specific fields per type
};

type ComparisonCondition = {
  type: "comparison";
  left: Indicator | number;
  operator: ">" | "<" | ">=" | "<=" | "==" | "!=";
  right: Indicator | number;
};

// Indicators
type Indicator = {
  type: "indicator";
  name: string; // "rsi", "sma", "macd", etc.
  symbol?: string; // defaults to current context
  params: Record<string, number>;
  output?: string; // for multi-output indicators like MACD
};

// Rules (for strategies)
type Rule = {
  name?: string;
  condition: Condition;
  action: Action;
  priority?: number;
};

type Action = {
  type: "buy" | "sell" | "close" | "adjust";
  size?: SizeSpec;
  stop_loss?: number;
  take_profit?: number;
  trailing_stop?: number;
};

type SizeSpec = {
  type:
    | "percent_portfolio"
    | "percent_position"
    | "fixed_shares"
    | "fixed_dollars";
  value: number;
};
```

---

## Example: Same Strategy in All DSLs

### The Strategy

> Buy AAPL when RSI(14) drops below 30 and volume is above 20-day average.
> Sell when RSI goes above 70 or price crosses below 50-day SMA.
> Use 5% position size, 2% stop loss, 4% take profit.

### S-Expression

```clojure
(defstrategy "RSI Reversal"
  {:timeframe :1h :symbols ["AAPL"]}
  (entry
    (when (and (< (rsi 14) 30)
               (> volume (sma-volume 20)))
      (buy :size 5% :stop-loss -2% :take-profit 4%)))
  (exit
    (when (or (> (rsi 14) 70)
              (crosses-below price (sma 50)))
      (close))))
```

### YAML

```yaml
strategy: RSI Reversal
timeframe: 1h
symbols: [AAPL]

entry:
  conditions:
    all:
      - indicator: rsi
        period: 14
        compare: "<"
        value: 30
      - indicator: volume
        compare: ">"
        to_indicator: sma_volume
        period: 20
  action:
    type: buy
    size: 5%
    stop_loss: -2%
    take_profit: 4%

exit:
  conditions:
    any:
      - indicator: rsi
        period: 14
        compare: ">"
        value: 70
      - crossover:
          fast: price
          slow: sma
          period: 50
          direction: below
  action:
    type: close
```

### Python

```python
Strategy("RSI Reversal") \
    .timeframe("1h") \
    .symbols(["AAPL"]) \
    .entry(
        when=And(RSI(14) < 30, Volume() > SMA_Volume(20)),
        do=Buy(size="5%", stop_loss="-2%", take_profit="4%")
    ) \
    .exit(
        when=Or(RSI(14) > 70, Price().crosses_below(SMA(50))),
        do=Close()
    )
```

### Infix

```
strategy "RSI Reversal" {
  timeframe: 1h
  symbols: [AAPL]

  entry when RSI(14) < 30 AND Volume > SMA_Volume(20) {
    buy 5% of portfolio
    stop_loss -2%
    take_profit 4%
  }

  exit when RSI(14) > 70 OR Price crosses below SMA(50) {
    close position
  }
}
```

### Natural Language

```
Create a strategy called "RSI Reversal" for AAPL on 1-hour timeframe:
- Buy when RSI(14) is below 30 and volume is above its 20-day average
- Use 5% of portfolio per trade with 2% stop loss and 4% take profit
- Sell when RSI(14) goes above 70 or price crosses below 50-day moving average
```

---

## Next Steps

1. **Finalize internal schema** - Protobuf/JSON Schema for canonical representation
2. **Implement YAML parser** - with JSON Schema validation
3. **Build AI generation** - Natural language → YAML
4. **Design Infix grammar** - PEG grammar specification
5. **Frontend prototypes** - Visual editor exploration
