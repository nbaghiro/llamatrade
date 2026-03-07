# LlamaTrade Strategy DSL Guide

This guide covers the S-expression Domain Specific Language (DSL) used to define allocation-based trading strategies in LlamaTrade.

## Table of Contents

- [Overview](#overview)
- [Strategy Structure](#strategy-structure)
- [Block Types](#block-types)
  - [strategy (Root Block)](#1-strategy-root-block)
  - [asset (Ticker Block)](#2-asset-ticker-block)
  - [weight (Allocation Block)](#3-weight-allocation-block)
  - [group (Organization Block)](#4-group-organization-block)
  - [if / else (Conditional Blocks)](#5-if--else-conditional-blocks)
  - [filter (Selection Block)](#6-filter-selection-block)
- [Condition Expressions](#condition-expressions)
  - [Comparison Operators](#comparison-operators)
  - [Crossover Operators](#crossover-operators)
  - [Logical Operators](#logical-operators)
  - [Value Expressions](#value-expressions)
- [Technical Indicators](#technical-indicators)
- [Complete Strategy Examples](#complete-strategy-examples)
- [JSON Serialization](#json-serialization)
- [Validation Rules](#validation-rules)
- [Tips for Writing Strategies](#tips-for-writing-strategies)

---

## Overview

LlamaTrade uses an **allocation-based** strategy DSL. Unlike signal-based systems that generate buy/sell signals, this DSL describes **target portfolio weights**. The system then rebalances the portfolio to match these target allocations.

### Design Principles

1. **S-expression syntax** - Lisp-like, easy to parse, supports nesting
2. **1:1 mapping to UI blocks** - Every UI block type has a DSL equivalent
3. **Declarative** - Describes *what* allocations should be, not *how* to execute
4. **Composable** - Blocks can be nested arbitrarily deep

### Key Concepts

- **Allocation, not signals**: Define target weights (0-100%) instead of buy/sell triggers
- **Rebalancing**: The engine computes trades needed to reach target allocations
- **Conditional allocation**: Dynamically change allocations based on market conditions
- **Weighting methods**: Equal weight, momentum, inverse volatility, and more

---

## Strategy Structure

Every strategy follows this structure:

```lisp
(strategy "Strategy Name"
  [:rebalance <frequency>]
  [:benchmark <symbol>]
  <allocation-blocks>...)
```

### Example

```lisp
(strategy "My Portfolio"
  :rebalance monthly
  :benchmark SPY
  (weight :method equal
    (asset VTI)
    (asset BND)))
```

### Strategy Parameters

| Parameter | Required | Description |
|-----------|----------|-------------|
| `name` | Yes | Human-readable strategy name (string) |
| `:rebalance` | No | Rebalancing frequency |
| `:benchmark` | No | Benchmark symbol for comparison |

### Rebalance Frequencies

| Value | Description |
|-------|-------------|
| `daily` | Rebalance every trading day |
| `weekly` | Rebalance once per week |
| `monthly` | Rebalance once per month |
| `quarterly` | Rebalance once per quarter |
| `annually` | Rebalance once per year |

---

## Block Types

### 1. `strategy` (Root Block)

The top-level container for all strategy definitions.

```lisp
(strategy "Strategy Name"
  [:rebalance <frequency>]
  [:benchmark <symbol>]
  <child-blocks>...)
```

**Example:**
```lisp
(strategy "60/40 Portfolio"
  :rebalance quarterly
  :benchmark SPY
  (weight :method specified
    (asset VTI :weight 60)
    (asset BND :weight 40)))
```

---

### 2. `asset` (Ticker Block)

Represents a specific tradeable asset.

```lisp
(asset <symbol> [:weight <percent>])
```

**Parameters:**
- `symbol` (required) - Ticker symbol (e.g., `VTI`, `AAPL`, `BTC-USD`)
- `:weight` (optional) - Weight percentage (only used with `:method specified`)

**Examples:**
```lisp
(asset VTI)
(asset AAPL :weight 25)
(asset BTC-USD :weight 5)
```

---

### 3. `weight` (Allocation Block)

Defines how child assets/groups should be weighted. This is the core allocation mechanism.

```lisp
(weight :method <method> [:lookback <days>] [:top <n>]
  <child-blocks>...)
```

**Parameters:**
- `:method` (required) - Allocation method (see below)
- `:lookback` (optional) - Lookback period in days for dynamic methods
- `:top` (optional) - Select top N assets (for momentum/filter strategies)

**Weight Methods:**

| Method | Description | Requires |
|--------|-------------|----------|
| `specified` | Manual percentage weights | `:weight` on each child |
| `equal` | Equal weight across children | Nothing |
| `momentum` | Weight by momentum score | `:lookback` |
| `inverse-volatility` | Weight inversely to volatility | `:lookback` |
| `min-variance` | Minimum variance optimization | `:lookback` |
| `market-cap` | Weight by market capitalization | Nothing |
| `risk-parity` | Equal risk contribution | `:lookback` |

**Examples:**

```lisp
;; Specified weights (must sum to 100 within the weight block)
(weight :method specified
  (asset VTI :weight 60)
  (asset BND :weight 40))

;; Equal weight
(weight :method equal
  (asset VTI)
  (asset VXUS)
  (asset BND))

;; Momentum with top 3 selection
(weight :method momentum :lookback 90 :top 3
  (asset XLK)
  (asset XLF)
  (asset XLE)
  (asset XLV)
  (asset XLI))

;; Inverse volatility
(weight :method inverse-volatility :lookback 60
  (asset VTI)
  (asset BND)
  (asset GLD))
```

---

### 4. `group` (Organization Block)

Groups related allocations together with an optional name. Groups don't affect allocation math - they're purely organizational.

```lisp
(group "Group Name"
  <child-blocks>...)
```

**Parameters:**
- `name` (required) - Group display name

**Example:**
```lisp
(group "US Equities"
  (weight :method specified
    (asset VTI :weight 70)
    (asset VXF :weight 30)))
```

---

### 5. `if` / `else` (Conditional Blocks)

Conditional allocation based on market conditions.

```lisp
(if <condition>
  <then-block>
  [(else <else-block>)])
```

**Parameters:**
- `condition` (required) - Boolean condition expression
- `then-block` (required) - Allocation when condition is true
- `else-block` (optional) - Allocation when condition is false (must be wrapped in `else`)

**Important:** The else clause must be wrapped in `(else ...)`.

**Examples:**

```lisp
;; Simple conditional
(if (> (sma SPY 50) (sma SPY 200))
  (asset SPY :weight 100)
  (else (asset TLT :weight 100)))

;; Conditional with weight blocks
(if (> (rsi SPY 14) 70)
  (weight :method specified
    (asset TLT :weight 60)
    (asset GLD :weight 40))
  (else
    (weight :method equal
      (asset SPY)
      (asset QQQ))))

;; Nested conditionals
(if (> (rsi SPY 14) 70)
  (asset TLT :weight 100)
  (else
    (if (< (rsi SPY 14) 30)
      (asset SPY :weight 100)
      (else
        (weight :method equal
          (asset SPY)
          (asset TLT))))))
```

---

### 6. `filter` (Selection Block)

Filters assets based on criteria before applying weights.

```lisp
(filter :by <criteria> :select <selection> [:lookback <days>]
  <child-blocks>...)
```

**Parameters:**
- `:by` (required) - Filter criteria: `momentum`, `volatility`, `volume`
- `:select` (required) - Selection: `(top N)` or `(bottom N)`
- `:lookback` (optional) - Lookback period for the filter metric

**Example:**
```lisp
;; Select top 3 by momentum, then equal weight them
(filter :by momentum :select (top 3) :lookback 90
  (weight :method equal
    (asset XLK)
    (asset XLF)
    (asset XLE)
    (asset XLV)
    (asset XLI)))
```

---

## Condition Expressions

Conditions are used in `if` blocks to make dynamic allocation decisions.

### Comparison Operators

```lisp
(> left right)   ;; greater than
(< left right)   ;; less than
(>= left right)  ;; greater or equal
(<= left right)  ;; less or equal
(= left right)   ;; equal
(!= left right)  ;; not equal
```

**Examples:**
```lisp
(> (price SPY) 100)           ;; Price above $100
(< (rsi SPY 14) 30)           ;; RSI below 30
(>= (sma SPY 50) (sma SPY 200)) ;; 50 SMA >= 200 SMA
```

### Crossover Operators

Detect when one value crosses another:

```lisp
(crosses-above fast slow)  ;; fast crosses above slow (bullish)
(crosses-below fast slow)  ;; fast crosses below slow (bearish)
```

**Examples:**
```lisp
;; Golden cross: 50 SMA crosses above 200 SMA
(crosses-above (sma SPY 50) (sma SPY 200))

;; RSI crosses above 30 (leaving oversold)
(crosses-above (rsi SPY 14) 30)

;; EMA crosses below price
(crosses-below (ema SPY 20) (price SPY))
```

### Logical Operators

Combine multiple conditions:

```lisp
(and expr1 expr2 ...)  ;; all must be true
(or expr1 expr2 ...)   ;; any must be true
(not expr)             ;; negation
```

**Examples:**
```lisp
;; Multiple conditions must be true
(and
  (> (sma SPY 50) (sma SPY 200))
  (< (rsi SPY 14) 70))

;; Either condition triggers
(or
  (> (rsi SPY 14) 70)
  (< (price SPY) (sma SPY 200)))

;; Negation
(not (> (rsi SPY 14) 70))
```

### Value Expressions

Values that can be compared:

```lisp
;; Price data
(price SPY)              ;; current close price
(price SPY :field close) ;; explicit close
(price SPY :field high)  ;; high price
(price SPY :field low)   ;; low price
(price SPY :field open)  ;; open price

;; Indicators (see Technical Indicators section)
(sma SPY 50)             ;; 50-day simple moving average
(ema SPY 20)             ;; 20-day exponential moving average
(rsi SPY 14)             ;; 14-day RSI

;; Relative values
(drawdown SPY)           ;; current drawdown from peak
(return SPY 30)          ;; 30-day return
(momentum SPY 90)        ;; 90-day momentum

;; Literals
50                       ;; number
0.05                     ;; decimal
```

---

## Technical Indicators

All technical indicators available in the DSL:

### Moving Averages

| Indicator | Syntax | Description |
|-----------|--------|-------------|
| SMA | `(sma SYMBOL period)` | Simple Moving Average |
| EMA | `(ema SYMBOL period)` | Exponential Moving Average |

```lisp
(sma SPY 20)    ;; 20-period SMA
(ema SPY 12)    ;; 12-period EMA
```

### Momentum Oscillators

| Indicator | Syntax | Outputs |
|-----------|--------|---------|
| RSI | `(rsi SYMBOL period)` | value (0-100) |
| MACD | `(macd SYMBOL fast slow signal [:output])` | `:line`, `:signal`, `:histogram` |
| Stochastic | `(stoch SYMBOL period [:output])` | `:k`, `:d` |
| Momentum | `(momentum SYMBOL period)` | value |

```lisp
(rsi SPY 14)                          ;; RSI
(macd SPY 12 26 9)                    ;; MACD line (default)
(macd SPY 12 26 9 :signal)            ;; MACD signal
(macd SPY 12 26 9 :histogram)         ;; MACD histogram
```

### Volatility Indicators

| Indicator | Syntax | Outputs |
|-----------|--------|---------|
| Bollinger Bands | `(bbands SYMBOL period stddev [:output])` | `:upper`, `:middle`, `:lower` |
| ATR | `(atr SYMBOL period)` | value |
| Standard Deviation | `(stddev SYMBOL period)` | value |

```lisp
(bbands SPY 20 2 :upper)   ;; Upper Bollinger Band
(bbands SPY 20 2 :lower)   ;; Lower Bollinger Band
(atr SPY 14)               ;; Average True Range
(stddev SPY 20)            ;; 20-period standard deviation
```

### Trend Indicators

| Indicator | Syntax | Outputs |
|-----------|--------|---------|
| ADX | `(adx SYMBOL period [:output])` | `:value`, `:plus_di`, `:minus_di` |

```lisp
(adx SPY 14)             ;; ADX value (trend strength)
(adx SPY 14 :plus_di)    ;; +DI (bullish direction)
(adx SPY 14 :minus_di)   ;; -DI (bearish direction)
```

---

## Complete Strategy Examples

### Example 1: Classic 60/40

Simple fixed allocation between stocks and bonds.

```lisp
(strategy "Classic 60/40"
  :rebalance quarterly
  :benchmark SPY
  (weight :method specified
    (asset VTI :weight 60)
    (asset BND :weight 40)))
```

### Example 2: Three-Fund Portfolio

```lisp
(strategy "Three-Fund Portfolio"
  :rebalance annually
  :benchmark SPY
  (weight :method specified
    (asset VTI :weight 50)
    (asset VXUS :weight 30)
    (asset BND :weight 20)))
```

### Example 3: RSI Mean Reversion

Allocate based on RSI levels - defensive when overbought, aggressive when oversold.

```lisp
(strategy "RSI Mean Reversion"
  :rebalance daily
  :benchmark SPY
  (if (< (rsi SPY 14) 30)
    (asset SPY :weight 100)
    (else
      (if (> (rsi SPY 14) 70)
        (asset TLT :weight 100)
        (else
          (weight :method equal
            (asset SPY)
            (asset TLT)))))))
```

### Example 4: Golden Cross Tactical

Switch between stocks and bonds based on moving average trend.

```lisp
(strategy "Golden Cross"
  :rebalance daily
  :benchmark SPY
  (if (> (sma SPY 50) (sma SPY 200))
    (asset SPY :weight 100)
    (else (asset AGG :weight 100))))
```

### Example 5: Risk Parity

Equal risk contribution across asset classes using inverse volatility.

```lisp
(strategy "Risk Parity"
  :rebalance monthly
  :benchmark SPY
  (weight :method inverse-volatility :lookback 60
    (asset VTI)
    (asset TLT)
    (asset GLD)
    (asset DBC)))
```

### Example 6: Dual Moving Average (Tactical)

```lisp
(strategy "Dual Moving Average"
  :rebalance daily
  :benchmark SPY
  (if (> (sma SPY 50) (sma SPY 200))
    (group "Risk On"
      (weight :method specified
        (asset VTI :weight 60)
        (asset VXUS :weight 40)))
    (else
      (group "Risk Off"
        (weight :method equal
          (asset BND)
          (asset SHY))))))
```

### Example 7: Sector Momentum Rotation

Select top momentum sectors and weight by momentum.

```lisp
(strategy "Sector Rotation"
  :rebalance monthly
  :benchmark SPY
  (if (> (sma SPY 200) (price SPY))
    ;; Bear market: go defensive
    (weight :method equal
      (asset BND)
      (asset GLD))
    (else
      ;; Bull market: momentum sectors
      (filter :by momentum :select (top 3) :lookback 90
        (weight :method momentum :lookback 90
          (asset XLK)
          (asset XLF)
          (asset XLE)
          (asset XLV)
          (asset XLI)
          (asset XLC)
          (asset XLY)
          (asset XLP)
          (asset XLRE)
          (asset XLU)
          (asset XLB))))))
```

### Example 8: All-Weather Portfolio

Ray Dalio inspired diversified allocation across economic regimes.

```lisp
(strategy "All-Weather"
  :rebalance quarterly
  :benchmark SPY
  (weight :method specified
    (asset VTI :weight 30)
    (asset TLT :weight 40)
    (asset IEF :weight 15)
    (asset GLD :weight 7.5)
    (asset DBC :weight 7.5)))
```

### Example 9: Dual Momentum

Combine absolute and relative momentum.

```lisp
(strategy "Dual Momentum"
  :rebalance monthly
  :benchmark SPY
  (if (and
        (> (price SPY) (sma SPY 200))
        (> (momentum SPY 252) 0))
    (asset SPY :weight 100)
    (else (asset TLT :weight 100))))
```

### Example 10: Volatility Targeting

Reduce equity allocation when VIX is high.

```lisp
(strategy "Volatility Targeting"
  :rebalance daily
  :benchmark SPY
  (if (> (price VIX) 30)
    (weight :method specified
      (asset SPY :weight 25)
      (asset TLT :weight 75))
    (else
      (if (> (price VIX) 20)
        (weight :method specified
          (asset SPY :weight 50)
          (asset TLT :weight 50))
        (else
          (weight :method specified
            (asset SPY :weight 75)
            (asset TLT :weight 25)))))))
```

### Example 11: Trend Following Multi-Asset

Apply trend filter to each asset class independently.

```lisp
(strategy "Trend Following"
  :rebalance monthly
  :benchmark SPY
  (group "Equities"
    (if (> (price VTI) (sma VTI 200))
      (asset VTI :weight 25)
      (else (asset SHY :weight 25))))
  (group "International"
    (if (> (price VXUS) (sma VXUS 200))
      (asset VXUS :weight 25)
      (else (asset SHY :weight 25))))
  (group "Bonds"
    (if (> (price TLT) (sma TLT 200))
      (asset TLT :weight 25)
      (else (asset SHY :weight 25))))
  (group "Commodities"
    (if (> (price GLD) (sma GLD 200))
      (asset GLD :weight 25)
      (else (asset SHY :weight 25)))))
```

---

## JSON Serialization

Strategies serialize to JSON for storage and API transport:

```json
{
  "type": "strategy",
  "name": "Dual Moving Average",
  "rebalance": "daily",
  "benchmark": "SPY",
  "children": [
    {
      "type": "if",
      "condition": {
        "type": "comparison",
        "operator": ">",
        "left": {
          "type": "indicator",
          "name": "sma",
          "symbol": "SPY",
          "params": [50]
        },
        "right": {
          "type": "indicator",
          "name": "sma",
          "symbol": "SPY",
          "params": [200]
        }
      },
      "then": {
        "type": "weight",
        "method": "specified",
        "children": [
          {"type": "asset", "symbol": "VTI", "weight": 60},
          {"type": "asset", "symbol": "VXUS", "weight": 40}
        ]
      },
      "else": {
        "type": "weight",
        "method": "equal",
        "children": [
          {"type": "asset", "symbol": "BND"},
          {"type": "asset", "symbol": "SHY"}
        ]
      }
    }
  ]
}
```

---

## Validation Rules

1. **Strategy must have at least one child block**
2. **Weight blocks with `method: specified` must have children that sum to 100%**
3. **Asset `:weight` is required when parent is `method: specified`, forbidden otherwise**
4. **Filter must contain exactly one weight block as child**
5. **Condition symbols must be valid tickers**
6. **Indicator parameters must be positive integers**
7. **Lookback periods must be positive integers**
8. **Nested if/else depth should be limited (recommend max 3 levels)**
9. **The else clause must be wrapped in `(else ...)`**

---

## Tips for Writing Strategies

1. **Start simple** - Begin with a fixed allocation, then add conditional logic
2. **Use meaningful names** - Strategy names should describe the approach
3. **Test with backtesting** - Validate strategies before live trading
4. **Consider rebalance frequency** - More frequent = more responsive but higher turnover
5. **Use groups for organization** - Group related assets for clarity
6. **Limit nesting depth** - Deeply nested conditionals are hard to maintain
7. **Set benchmarks** - Always include a benchmark for performance comparison
8. **Balance diversification** - Spread allocations across uncorrelated assets

---

## AST Node Types

The parser produces these AST node types:

```python
from dataclasses import dataclass
from typing import Literal as TypingLiteral

@dataclass
class Strategy:
    """Root strategy node."""
    name: str
    rebalance: str | None  # daily, weekly, monthly, quarterly, annually
    benchmark: str | None
    children: list["Block"]

@dataclass
class Group:
    """Organizational grouping."""
    name: str
    children: list["Block"]

@dataclass
class Weight:
    """Allocation weight block."""
    method: TypingLiteral["specified", "equal", "momentum",
                          "inverse-volatility", "min-variance",
                          "market-cap", "risk-parity"]
    lookback: int | None
    top: int | None
    children: list["Block"]

@dataclass
class Asset:
    """Single asset/ticker."""
    symbol: str
    weight: float | None  # Only for method=specified

@dataclass
class If:
    """Conditional block."""
    condition: "Condition"
    then_block: "Block"
    else_block: "Block | None"

@dataclass
class Filter:
    """Asset filter/selector."""
    by: TypingLiteral["momentum", "volatility", "volume"]
    select: tuple[TypingLiteral["top", "bottom"], int]
    lookback: int | None
    children: list["Block"]

# Union type for all blocks
Block = Strategy | Group | Weight | Asset | If | Filter

# Condition types
@dataclass
class Comparison:
    """Comparison condition."""
    operator: TypingLiteral[">", "<", ">=", "<=", "=", "!="]
    left: "Value"
    right: "Value"

@dataclass
class Crossover:
    """Crossover condition."""
    direction: TypingLiteral["above", "below"]
    fast: "Value"
    slow: "Value"

@dataclass
class LogicalOp:
    """Logical combination."""
    operator: TypingLiteral["and", "or", "not"]
    operands: list["Condition"]

Condition = Comparison | Crossover | LogicalOp

# Value types
@dataclass
class Price:
    """Price reference."""
    symbol: str
    field: TypingLiteral["close", "open", "high", "low"] = "close"

@dataclass
class Indicator:
    """Technical indicator."""
    name: str  # sma, ema, rsi, macd, etc.
    symbol: str
    params: list[int | float]
    output: str | None  # For multi-output indicators

@dataclass
class Literal:
    """Numeric literal."""
    value: float

Value = Price | Indicator | Literal
```
