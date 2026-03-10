# Strategy DSL Reference

Complete reference for the S-expression Domain Specific Language (DSL) used in LlamaTrade for defining trading strategies and portfolio allocations.

---

## Table of Contents

1. [Overview](#overview)
2. [Why S-Expressions?](#why-s-expressions)
3. [Architecture](#architecture)
4. [Language Basics](#language-basics)
5. [Symphony DSL (Portfolio Allocation)](#symphony-dsl-portfolio-allocation)
6. [Strategy DSL (Active Trading)](#strategy-dsl-active-trading)
7. [Condition Expressions](#condition-expressions)
8. [Technical Indicators](#technical-indicators)
9. [Complete Examples](#complete-examples)
10. [Grammar Specification](#grammar-specification)
11. [Abstract Syntax Tree](#abstract-syntax-tree)
12. [Parser Implementation](#parser-implementation)
13. [Serialization](#serialization)
14. [Execution Engine](#execution-engine)
15. [AI Generation](#ai-generation)
16. [Validation Rules](#validation-rules)
17. [Tips for Writing Strategies](#tips-for-writing-strategies)

---

## Overview

LlamaTrade uses a Lisp-inspired S-expression DSL for defining trading logic. The DSL supports two primary constructs:

**Symphonies** define portfolio allocation strategies. They specify what assets to hold and in what proportions, with optional conditional logic for regime-based rotation. Symphonies are evaluated periodically (daily, weekly, monthly) to determine target allocations.

**Strategies** define active trading rules with entry and exit conditions. They specify when to buy or sell based on technical indicators, price action, and other market conditions. Strategies are evaluated on every bar (candle) to generate trading signals.

### Key Capabilities

- **Declarative syntax** for complex allocation and trading logic
- **Technical indicator integration** with 20+ built-in indicators (RSI, SMA, MACD, etc.)
- **Conditional branching** with `if/else` and multi-branch `cond` expressions
- **Universe filtering** to select top/bottom N assets by any metric
- **Risk management** with stop-loss, take-profit, and trailing stop parameters
- **Crossover detection** for moving average and indicator crossover signals
- **1:1 mapping to UI blocks** - Every UI block type has a DSL equivalent

### Design Principles

1. **S-expression syntax** - Lisp-like, easy to parse, supports nesting
2. **Declarative** - Describes *what* allocations should be, not *how* to execute
3. **Composable** - Blocks can be nested arbitrarily deep
4. **Bidirectional** - Lossless round-tripping between text, AST, JSON, and visual blocks

---

## Why S-Expressions?

S-expressions (symbolic expressions) are a notation for nested list data originating from Lisp. We chose this syntax for several reasons:

**Unambiguous parsing.** The parenthesized prefix notation eliminates operator precedence ambiguity. There's exactly one way to parse any valid expression, making the parser simpler and error messages clearer.

**Homoiconicity.** Code and data share the same structure. A strategy definition is just a nested data structure, making it easy to manipulate programmatically, serialize to JSON, or generate from other representations (like the visual builder).

**Extensibility.** Adding new constructs (indicators, weight methods, conditions) requires no grammar changes. New functions are just new symbols in the same syntactic framework.

**AI-friendly.** Large language models excel at generating well-formed S-expressions because the syntax is regular and unambiguous. The closing parentheses provide clear structural cues.

**Bidirectional conversion.** The simple structure enables lossless round-tripping between text, AST, JSON, and visual block representations.

---

## Architecture

The DSL processing pipeline transforms user input through several stages:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              INPUT LAYER                                    │
├─────────────────┬─────────────────┬─────────────────────────────────────────┤
│   Visual        │   Natural       │   S-Expression                          │
│   Builder       │   Language      │   Text Editor                           │
│   (React)       │   (Chat)        │   (Monaco)                              │
└────────┬────────┴────────┬────────┴────────┬────────────────────────────────┘
         │                 │                 │
         │                 │                 ▼
         │                 │        ┌────────────────────────────────────┐
         │                 │        │         PARSER (Lark)              │
         │                 │        │   S-Expression → AST               │
         │                 │        └───────────────┬────────────────────┘
         │                 │                        │
         │                 ▼                        ▼
         │        ┌────────────────────────────────────────────────────┐
         │        │              UNIFIED AST (Abstract Syntax Tree)    │
         │        │   SymphonyNode / StrategyNode                      │
         │        │   ├── MetadataNode                                 │
         │        │   ├── AllocationNode / RulesNode                   │
         │        │   │   ├── ConditionalNode                          │
         │        │   │   ├── WeightNode                               │
         │        │   │   └── AssetNode                                │
         │        │   └── ConditionNode                                │
         │        │       ├── ComparisonNode                           │
         │        │       ├── LogicalNode (AND/OR/NOT)                 │
         │        │       └── IndicatorNode                            │
         └────────┼────────────────────────────────────────────────────┘
                  │                        │
    ┌─────────────┴─────────────┐          │
    │     BIDIRECTIONAL         │          │
    │     SERIALIZATION         │          │
    │   AST ←→ S-Expr Text      │          │
    │   AST ←→ Visual Blocks    │          │
    │   AST ←→ JSON (storage)   │          │
    └───────────────────────────┘          │
                                           ▼
              ┌────────────────────────────────────────────────────┐
              │              SEMANTIC LAYER                        │
              │   • Type checking                                  │
              │   • Symbol resolution (indicators, universes)      │
              │   • Validation (required fields, ranges)           │
              └────────────────────────────────────────────────────┘
                                           │
                                           ▼
              ┌────────────────────────────────────────────────────┐
              │        IR (Intermediate Representation)            │
              │   Normalized, validated, ready for execution       │
              │   Stored in PostgreSQL as JSONB                    │
              └────────────────────────────────────────────────────┘
                                           │
                     ┌─────────────────────┼─────────────────────┐
                     ▼                     ▼                     ▼
              ┌────────────┐       ┌────────────┐       ┌────────────┐
              │ Backtester │       │   Paper    │       │   Live     │
              │            │       │  Trading   │       │  Trading   │
              └────────────┘       └────────────┘       └────────────┘
```

**Input Layer:** Users can create strategies through three interfaces. The visual builder provides a drag-and-drop block-based interface. Natural language chat lets users describe strategies in plain English (converted via AI). The text editor provides direct S-expression editing with syntax highlighting.

**Parser:** The Lark parser converts S-expression text into an Abstract Syntax Tree (AST). The grammar defines valid syntax; the transformer converts parse trees to typed Python dataclasses.

**Unified AST:** All input methods produce the same AST structure. This enables the visual builder to generate DSL code, and DSL code to render in the visual builder. The AST is the single source of truth.

**Semantic Layer:** Validates the AST for correctness. Checks that referenced indicators exist, symbol variables are bound, weight methods are valid, and required metadata is present.

**IR (Intermediate Representation):** The validated AST is normalized and stored as JSONB in PostgreSQL. This representation is version-controlled and can be executed by any runner.

**Execution:** The backtester, paper trading, and live trading services all consume the same IR, ensuring consistent behavior across modes.

---

## Language Basics

### Expressions and Lists

Everything in S-expressions is either an atom (number, string, symbol) or a list. Lists are enclosed in parentheses with elements separated by whitespace:

```clojure
;; A list with three elements
(a b c)

;; Nested lists
(a (b c) d)

;; Function call syntax: first element is the function, rest are arguments
(+ 1 2)        ;; Adds 1 and 2
(rsi "AAPL" 14) ;; RSI of AAPL with period 14
```

### Data Types

| Type | Syntax | Examples |
|------|--------|----------|
| Number | Digits with optional decimal | `14`, `0.5`, `-2.5` |
| Percentage | Number followed by `%` | `5%`, `0.5%`, `-2%` |
| String | Double-quoted text | `"AAPL"`, `"My Strategy"` |
| Keyword | Colon followed by name | `:weekly`, `:stop-loss`, `:market` |
| Symbol | Dollar sign followed by name | `$symbol`, `$price` |

### Keywords vs Symbols

**Keywords** (`:keyword`) are used for named parameters and options:

```clojure
(buy $symbol :size 5% :stop-loss -2%)
```

**Symbols** (`$symbol`) are variables that get bound at runtime. In a strategy, `$symbol` refers to the current symbol being evaluated:

```clojure
(rsi $symbol 14)  ;; RSI of whatever symbol we're currently processing
```

### Comments

Single-line comments start with a semicolon:

```clojure
;; This is a comment
(defsymphony "Test"  ; inline comment
  {:rebalance :weekly}
  ...)
```

---

## Symphony DSL (Portfolio Allocation)

Symphonies define **target portfolio weights**. Unlike signal-based systems that generate buy/sell signals, symphonies describe allocations. The system then rebalances the portfolio to match these target allocations.

### Structure

```lisp
(strategy "Strategy Name"
  [:rebalance <frequency>]
  [:benchmark <symbol>]
  <allocation-blocks>...)
```

### Parameters

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

### Block Types

#### 1. `strategy` (Root Block)

The top-level container for all strategy definitions.

```lisp
(strategy "60/40 Portfolio"
  :rebalance quarterly
  :benchmark SPY
  (weight :method specified
    (asset VTI :weight 60)
    (asset BND :weight 40)))
```

#### 2. `asset` (Ticker Block)

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

#### 3. `weight` (Allocation Block)

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

#### 4. `group` (Organization Block)

Groups related allocations together with an optional name. Groups don't affect allocation math - they're purely organizational.

```lisp
(group "Group Name"
  <child-blocks>...)
```

**Example:**
```lisp
(group "US Equities"
  (weight :method specified
    (asset VTI :weight 70)
    (asset VXF :weight 30)))
```

#### 5. `if` / `else` (Conditional Blocks)

Conditional allocation based on market conditions.

```lisp
(if <condition>
  <then-block>
  [(else <else-block>)])
```

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

#### 6. `filter` (Selection Block)

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

## Strategy DSL (Active Trading)

Strategies define entry and exit rules that generate trading signals. Unlike symphonies that define allocations, strategies specify when to buy and sell.

### Structure

```clojure
(defstrategy "Strategy Name"
  {:timeframe <timeframe>
   :symbols [<symbols>...]}

  (entry
    (when <condition>
      <action>...))

  (exit
    (when <condition>
      <action>...)))
```

### Metadata

| Field | Description |
|-------|-------------|
| `:timeframe` | Bar timeframe (`:1m`, `:5m`, `:15m`, `:1h`, `:4h`, `:1d`) |
| `:symbols` | List of symbols to trade |

### Entry/Exit Rules

```clojure
(entry
  (when (and (< (rsi $symbol 14) 30)
             (> (volume $symbol) (* 1.5 (sma-volume $symbol 20))))
    (buy $symbol
      :size 5%
      :order-type :market
      :stop-loss -2%
      :take-profit 4%
      :trailing-stop 1%)))

(exit
  (when (or (> (rsi $symbol 14) 70)
            (crosses-below (close $symbol) (sma $symbol 50)))
    (close $symbol)))
```

### Actions

| Action | Description |
|--------|-------------|
| `buy` | Open long position |
| `sell` | Open short position |
| `close` | Close current position |
| `close-long` | Close only long positions |
| `close-short` | Close only short positions |

### Action Parameters

| Parameter | Description |
|-----------|-------------|
| `:size` | Position size (percent or fixed) |
| `:order-type` | `:market` or `:limit` |
| `:stop-loss` | Stop loss percentage (negative) |
| `:take-profit` | Take profit percentage (positive) |
| `:trailing-stop` | Trailing stop percentage |

---

## Condition Expressions

Conditions are used in `if` blocks (symphonies) and `when` clauses (strategies).

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

## Complete Examples

### Symphony: Classic 60/40

Simple fixed allocation between stocks and bonds.

```lisp
(strategy "Classic 60/40"
  :rebalance quarterly
  :benchmark SPY
  (weight :method specified
    (asset VTI :weight 60)
    (asset BND :weight 40)))
```

### Symphony: RSI Mean Reversion

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

### Symphony: Sector Momentum Rotation

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

### Symphony: Risk Parity

Equal risk contribution across asset classes.

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

### Strategy: RSI Mean Reversion (Active Trading)

```clojure
(defstrategy "RSI Mean Reversion"
  {:timeframe :1h
   :symbols ["AAPL" "MSFT" "GOOGL" "AMZN"]}

  (entry
    (when (and (< (rsi $symbol 14) 30)
               (> (volume $symbol) (* 1.5 (sma-volume $symbol 20))))
      (buy $symbol
        :size 5%
        :order-type :market
        :stop-loss -2%
        :take-profit 4%
        :trailing-stop 1%)))

  (exit
    (when (or (> (rsi $symbol 14) 70)
              (crosses-below (close $symbol) (sma $symbol 50)))
      (close $symbol))))
```

### Symphony: Conditional Rotation with Cond

```clojure
(defsymphony "Regime Adaptive"
  {:rebalance :weekly}

  (cond
    ;; Bear market: 50-day MA below 200-day MA
    [(< (sma "SPY" 50) (sma "SPY" 200))
     (weight-equal [(asset "TLT") (asset "GLD")])]

    ;; High volatility: VIX above 30
    [(> (vix) 30)
     (weight-risk-parity
       [(asset "SPY" :max-weight 0.3)
        (asset "TLT")
        (asset "GLD")])]

    ;; Default: bull market
    [:else
     (weight-momentum
       [(universe "FAANG")])]))
```

---

## Grammar Specification

The formal grammar is specified in Lark/EBNF notation:

```ebnf
(* S-Expression Grammar - Lark syntax *)

start: definition+

definition: symphony_def | strategy_def | indicator_def

(* Top-level definitions *)
symphony_def: "(" "defsymphony" STRING metadata? allocation_expr ")"
strategy_def: "(" "defstrategy" STRING metadata? rule+ ")"
indicator_def: "(" "defindicator" STRING param_list expr ")"

(* Metadata block *)
metadata: "{" metadata_pair* "}"
metadata_pair: KEYWORD value

(* Allocation expressions - what to hold *)
allocation_expr: asset_expr
              | weight_expr
              | conditional_expr
              | filter_expr
              | universe_expr

asset_expr: "(" "asset" STRING asset_opts? ")"
asset_opts: KEYWORD value

weight_expr: "(" weight_method "[" allocation_expr+ "]" ")"
weight_method: "weight-equal" | "weight-fixed" | "weight-inverse-volatility"
            | "weight-risk-parity" | "weight-momentum"

conditional_expr: "(" "if" condition allocation_expr allocation_expr? ")"
               | "(" "cond" cond_branch+ ")"
cond_branch: "[" condition allocation_expr "]"

filter_expr: "(" "filter-top" NUMBER KEYWORD expr ")"
          | "(" "filter-bottom" NUMBER KEYWORD expr ")"

universe_expr: "(" "universe" STRING ")"

(* Strategy rules - when to trade *)
rule: entry_rule | exit_rule
entry_rule: "(" "entry" "(" "when" condition action+ ")" ")"
exit_rule: "(" "exit" "(" "when" condition action+ ")" ")"

action: "(" action_type action_opts* ")"
action_type: "buy" | "sell" | "close" | "close-long" | "close-short"
action_opts: KEYWORD value

(* Conditions - boolean expressions *)
condition: comparison | logical_expr | crossover_expr

comparison: "(" COMPARATOR expr expr ")"
COMPARATOR: ">" | "<" | ">=" | "<=" | "=" | "!="

logical_expr: "(" "and" condition+ ")"
           | "(" "or" condition+ ")"
           | "(" "not" condition ")"

crossover_expr: "(" "crosses-above" expr expr ")"
             | "(" "crosses-below" expr expr ")"

(* Value expressions *)
expr: NUMBER | STRING | SYMBOL | indicator_call | arithmetic_expr

indicator_call: "(" INDICATOR_NAME expr* ")"
INDICATOR_NAME: "rsi" | "sma" | "ema" | "macd" | "bbands" | "atr"
             | "volume" | "price" | "high" | "low" | "open" | "close"
             | "sma-volume" | "vix" | "momentum"

arithmetic_expr: "(" OPERATOR expr expr ")"
OPERATOR: "+" | "-" | "*" | "/"

(* Terminals *)
STRING: "\"" /[^"]*/ "\""
NUMBER: /-?[0-9]+(\.[0-9]+)?%?/
SYMBOL: "$" NAME
KEYWORD: ":" NAME
NAME: /[a-zA-Z_][a-zA-Z0-9_-]*/

%import common.WS
%ignore WS
%ignore COMMENT
COMMENT: ";" /[^\n]/*
```

---

## Abstract Syntax Tree

The parser transforms S-expression text into a tree of typed Python dataclasses.

### Core Node Types

```python
# libs/dsl/llamatrade_dsl/ast.py

from dataclasses import dataclass, field
from typing import Any, List, Optional, Union
from enum import Enum


class WeightMethod(str, Enum):
    """Available portfolio weighting methods."""
    EQUAL = "equal"
    FIXED = "fixed"
    INVERSE_VOLATILITY = "inverse_volatility"
    RISK_PARITY = "risk_parity"
    MOMENTUM = "momentum"


@dataclass
class MetadataNode:
    """Strategy/symphony metadata."""
    rebalance: Optional[str] = None
    benchmark: Optional[str] = None
    description: Optional[str] = None
    timeframe: Optional[str] = None
    symbols: List[str] = field(default_factory=list)


@dataclass
class AssetNode:
    """Single asset with optional weight constraints."""
    symbol: str
    weight: Optional[float] = None
    max_weight: Optional[float] = None


@dataclass
class WeightNode:
    """Apply a weighting method to a list of allocations."""
    method: str
    children: List[Union["AssetNode", "FilterNode", "UniverseNode", "WeightNode"]]


@dataclass
class IndicatorNode:
    """Technical indicator function call."""
    name: str
    args: List[Any] = field(default_factory=list)
    symbol: Optional[str] = None
    accessor: Optional[str] = None


@dataclass
class ComparisonNode:
    """Comparison expression (>, <, >=, <=, =, !=)."""
    operator: str
    left: Any
    right: Any


@dataclass
class CrossoverNode:
    """Crossover detection."""
    direction: str  # "above" or "below"
    fast: Any
    slow: Any


@dataclass
class LogicalNode:
    """Logical combination of conditions (AND, OR, NOT)."""
    type: str
    conditions: List[Union["ComparisonNode", "CrossoverNode", "LogicalNode"]]


@dataclass
class ConditionalNode:
    """Conditional branching in allocation (if/else, cond)."""
    condition: Union[ComparisonNode, CrossoverNode, LogicalNode]
    then_branch: Union[WeightNode, "ConditionalNode"]
    else_branch: Optional[Union[WeightNode, "ConditionalNode"]] = None


@dataclass
class ActionNode:
    """Trading action (buy, sell, close) with parameters."""
    type: str
    symbol: Optional[str] = None
    size_value: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    trailing_stop: Optional[float] = None
    order_type: str = "market"


@dataclass
class RuleNode:
    """Entry or exit rule with condition and actions."""
    type: str  # "entry" or "exit"
    condition: Union[ComparisonNode, CrossoverNode, LogicalNode]
    actions: List[ActionNode]


@dataclass
class SymphonyNode:
    """Top-level symphony (portfolio allocation) definition."""
    name: str
    metadata: MetadataNode
    allocation: Union[AssetNode, WeightNode, ConditionalNode]
    version: int = 1


@dataclass
class StrategyNode:
    """Top-level strategy (active trading) definition."""
    name: str
    metadata: MetadataNode
    rules: List[RuleNode]
    version: int = 1
```

---

## Parser Implementation

The parser uses [Lark](https://github.com/lark-parser/lark), a modern parsing library for Python.

### Parsing Pipeline

1. **Lexing:** Input text is tokenized into NUMBER, STRING, KEYWORD, etc.
2. **Parsing:** Tokens are matched against grammar rules to build a parse tree
3. **Transformation:** Parse tree nodes are converted to typed AST dataclasses

### Parser Code

```python
# libs/dsl/llamatrade_dsl/sexpr/parser.py

from lark import Lark, Transformer
from typing import List, Union

from ..ast import (
    SymphonyNode, StrategyNode, MetadataNode,
    AssetNode, WeightNode, ConditionalNode,
    ComparisonNode, LogicalNode, CrossoverNode,
    IndicatorNode, ActionNode, RuleNode
)


class SExprTransformer(Transformer):
    """Transform parse tree into AST nodes."""

    def start(self, items) -> List[Union[SymphonyNode, StrategyNode]]:
        return list(items)

    def symphony_def(self, items) -> SymphonyNode:
        name = self._unquote(items[0])
        metadata = {}
        allocation = None

        for item in items[1:]:
            if isinstance(item, dict):
                metadata = item
            else:
                allocation = item

        return SymphonyNode(
            name=name,
            metadata=MetadataNode(**metadata),
            allocation=allocation
        )

    def weight_expr(self, items) -> WeightNode:
        method = str(items[0]).replace("weight-", "").replace("-", "_")
        children = list(items[1:])
        return WeightNode(method=method, children=children)

    def comparison(self, items) -> ComparisonNode:
        return ComparisonNode(
            operator=str(items[0]),
            left=items[1],
            right=items[2]
        )

    def _unquote(self, s) -> str:
        return str(s).strip('"')


class SExprParser:
    """S-Expression parser for LlamaTrade DSL."""

    def __init__(self):
        self.parser = Lark(
            SEXPR_GRAMMAR,
            parser='lalr',
            transformer=SExprTransformer()
        )

    def parse(self, source: str) -> List[Union[SymphonyNode, StrategyNode]]:
        return self.parser.parse(source)
```

---

## Serialization

The AST can be serialized to multiple formats for bidirectional conversion.

### JSON Serialization

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

### S-Expression Serializer

Converts AST back to readable S-expression text:

```python
class SExprSerializer:
    """Serialize AST back to S-expression format."""

    def serialize(self, node: Union[SymphonyNode, StrategyNode]) -> str:
        if isinstance(node, SymphonyNode):
            return self._symphony(node)
        return self._strategy(node)

    def _symphony(self, node: SymphonyNode) -> str:
        lines = [f'(defsymphony "{node.name}"']
        lines.append(self._metadata(node.metadata))
        lines.append(self._indent(self._allocation(node.allocation), 2))
        lines.append(")")
        return "\n".join(lines)
```

---

## Execution Engine

The compiler transforms AST nodes into executable Python functions.

### Compilation Process

1. **AST traversal:** Walk the tree, compiling each node type
2. **Closure generation:** Build nested Python functions that capture context
3. **Indicator registration:** Register required indicators for pre-computation
4. **Output:** Callable functions that evaluate allocations or generate signals

### Compiled Types

```python
@dataclass
class CompiledSymphony:
    """Compiled symphony ready for execution."""
    name: str
    rebalance_frequency: str
    benchmark: Optional[str]
    evaluate: callable  # (market_data) -> Dict[str, float]


@dataclass
class CompiledStrategy:
    """Compiled strategy ready for execution."""
    name: str
    timeframe: str
    symbols: List[str]
    on_bar: callable  # (symbol, bar, portfolio) -> List[Signal]
```

---

## AI Generation

Users can describe strategies in natural language, and Claude generates valid S-expression code.

### How It Works

1. User describes strategy in plain English
2. System prompt instructs Claude on S-expression syntax
3. Few-shot examples demonstrate correct format
4. Claude generates DSL code
5. Parser validates the output
6. If invalid, optionally retry with error feedback

### Generator Code

```python
from anthropic import Anthropic

SYSTEM_PROMPT = """You are an expert trading strategy designer for LlamaTrade.
Convert natural language descriptions into S-expression trading strategies.

## S-Expression Format
- Use (defsymphony "name" {...} allocation) for portfolio allocations
- Use (defstrategy "name" {...} rules) for active trading
- Conditions: (and ...), (or ...), (> x y), (< x y), (crosses-above x y)
- Indicators: (rsi symbol period), (sma symbol period), (macd symbol fast slow signal)

Always output ONLY the DSL code, no explanations."""


class AIStrategyGenerator:
    """Generate strategies from natural language using Claude."""

    def __init__(self, api_key: str = None):
        self.client = Anthropic(api_key=api_key)

    def generate(self, description: str) -> str:
        response = self.client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=2000,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": description}]
        )
        return response.content[0].text.strip()
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

## Related Documentation

- [Strategy Execution](strategy-execution.md) - How strategies compile, evaluate, and generate orders
- [Strategy Service](services/strategy.md) - Strategy service implementation
- [Trading Strategies](trading-strategies.md) - Algorithmic trading concepts
