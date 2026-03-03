# Strategy DSL Reference

This document details the S-Expression DSL for defining trading strategies and portfolio allocations in LlamaTrade. It covers the language syntax, parsing pipeline, and execution model.

---

## Table of Contents

1. [Overview](#overview)
2. [Why S-Expressions?](#why-s-expressions)
3. [Architecture](#architecture)
4. [Language Basics](#language-basics)
5. [Grammar Specification](#grammar-specification)
6. [Example Strategies](#example-strategies)
7. [Abstract Syntax Tree](#abstract-syntax-tree)
8. [Parser Implementation](#parser-implementation)
9. [Serialization](#serialization)
10. [Execution Engine](#execution-engine)
11. [AI Generation](#ai-generation)

---

## Overview

LlamaTrade uses a Lisp-inspired S-expression DSL for defining trading logic. The DSL supports two primary constructs:

**Symphonies** define portfolio allocation strategies. They specify what assets to hold and in what proportions, with optional conditional logic for regime-based rotation. Symphonies are evaluated periodically (daily, weekly, monthly) to determine target allocations.

**Strategies** define active trading rules with entry and exit conditions. They specify when to buy or sell based on technical indicators, price action, and other market conditions. Strategies are evaluated on every bar (candle) to generate trading signals.

The DSL provides:
- **Declarative syntax** for complex allocation and trading logic
- **Technical indicator integration** with 20+ built-in indicators (RSI, SMA, MACD, etc.)
- **Conditional branching** with `if/else` and multi-branch `cond` expressions
- **Universe filtering** to select top/bottom N assets by any metric
- **Risk management** with stop-loss, take-profit, and trailing stop parameters
- **Crossover detection** for moving average and indicator crossover signals

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

Before diving into the formal grammar, here's an introduction to the syntax:

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

**Keywords** (`:keyword`) are used for named parameters and options. They're like named arguments in Python:

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

### Metadata

Metadata is specified in curly braces with keyword-value pairs:

```clojure
{:rebalance :weekly
 :benchmark "SPY"
 :description "My strategy description"}
```

---

## Grammar Specification

The formal grammar is specified in Lark/EBNF notation. This section is primarily for developers implementing parsers or extending the language.

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

## Example Strategies

### Simple Equal-Weight Portfolio

This symphony creates a static portfolio with four GPU-related stocks, each receiving 25% allocation. It rebalances weekly to maintain equal weights as prices change.

```clojure
(defsymphony "GPU Sector"
  {:rebalance :weekly
   :benchmark "SPY"
   :description "Equal weight GPU manufacturers"}

  (weight-equal
    [(asset "NVDA")
     (asset "AMD")
     (asset "INTC")
     (asset "TSM")]))
```

**How it works:**
1. `defsymphony` declares a portfolio allocation strategy named "GPU Sector"
2. Metadata specifies weekly rebalancing and SPY as the benchmark
3. `weight-equal` distributes capital equally among all children
4. Each `asset` specifies a ticker symbol to include

### Conditional Rotation Strategy

This symphony rotates between risk-on (stocks) and risk-off (bonds) based on RSI. When SPY's RSI exceeds 70 (overbought), it shifts to bonds. Otherwise, it selects the top 10 momentum stocks from the S&P 500.

```clojure
(defsymphony "Risk-On Risk-Off"
  {:rebalance :daily}

  (if (> (rsi "SPY" 14) 70)
    ;; Risk-off: rotate to bonds
    (weight-equal
      [(asset "TLT")
       (asset "IEF")
       (asset "SHY")])
    ;; Risk-on: momentum stocks
    (filter-top 10 :by (momentum 252)
      (universe "SP500"))))
```

**How it works:**
1. The `if` expression checks if SPY's 14-period RSI is above 70
2. If true (overbought market), allocate equally to three bond ETFs
3. If false, use `filter-top` to select the 10 highest momentum stocks
4. `(momentum 252)` calculates 252-day (1 year) momentum
5. `(universe "SP500")` provides the pool of stocks to filter

### Multi-Condition with Cond

The `cond` expression handles multiple conditions with a default fallback. This enables regime-based allocation that adapts to different market conditions.

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

**How it works:**
1. `cond` evaluates conditions in order, using the first that matches
2. First check: death cross (50 MA < 200 MA) triggers defensive positioning
3. Second check: high VIX triggers risk-parity allocation with SPY capped at 30%
4. `:else` is the default branch when no conditions match
5. `weight-momentum` allocates more to assets with stronger momentum

### Active Trading Strategy with Entry/Exit

Strategies define entry and exit rules that generate trading signals. This RSI mean reversion strategy buys oversold conditions and sells when overbought.

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

**How it works:**
1. `defstrategy` declares an active trading strategy
2. Metadata specifies 1-hour timeframe and which symbols to trade
3. `$symbol` is a runtime variable bound to each symbol being evaluated
4. Entry condition: RSI below 30 AND volume 50% above 20-period average
5. Entry action: buy 5% of portfolio with stop-loss, take-profit, and trailing stop
6. Exit condition: RSI above 70 OR price crosses below 50-period SMA
7. Exit action: close the position

### Custom Indicator Definition

You can define custom indicators that combine multiple calculations:

```clojure
(defindicator "squeeze-momentum"
  [length bb-mult kc-mult]
  (let [bb (bbands $symbol length bb-mult)
        kc (keltner $symbol length kc-mult)
        squeeze-on (and (> (:lower bb) (:lower kc))
                        (< (:upper bb) (:upper kc)))
        mom (- (close $symbol) (sma (/ (+ (highest length) (lowest length)) 2) length))]
    {:squeeze squeeze-on
     :momentum mom}))
```

**How it works:**
1. `defindicator` creates a reusable indicator function
2. Parameters: `length`, `bb-mult`, `kc-mult` (Bollinger/Keltner multipliers)
3. `let` binds intermediate calculations to names
4. `squeeze-on` is true when Bollinger Bands are inside Keltner Channels
5. Returns a map with `:squeeze` and `:momentum` values

---

## Abstract Syntax Tree

The parser transforms S-expression text into a tree of typed Python dataclasses. This AST is the canonical representation that all tools manipulate.

### Why Use an AST?

**Type safety.** Each node type has defined fields, making invalid states unrepresentable.

**Tool interoperability.** The visual builder, text editor, and AI generator all produce and consume the same AST.

**Validation.** The AST structure enables validation passes (type checking, symbol resolution) before execution.

**Transformation.** AST nodes can be transformed, optimized, and serialized without parsing again.

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
    """Strategy/symphony metadata like rebalance frequency and benchmark."""
    rebalance: Optional[str] = None
    benchmark: Optional[str] = None
    description: Optional[str] = None
    timeframe: Optional[str] = None
    symbols: List[str] = field(default_factory=list)


@dataclass
class AssetNode:
    """Single asset with optional weight constraints."""
    symbol: str
    weight: Optional[float] = None      # Fixed weight (for weight-fixed)
    max_weight: Optional[float] = None  # Maximum allocation cap


@dataclass
class UniverseNode:
    """Reference to a predefined universe of assets (SP500, FAANG, etc.)."""
    name: str


@dataclass
class FilterNode:
    """Filter a universe to top/bottom N by some metric."""
    type: str  # "top" or "bottom"
    count: int
    by: str  # metric name (momentum, volatility, etc.)
    source: Union["UniverseNode", "WeightNode"]


@dataclass
class WeightNode:
    """Apply a weighting method to a list of allocations."""
    method: str
    children: List[Union[AssetNode, FilterNode, UniverseNode, "WeightNode"]]


@dataclass
class IndicatorNode:
    """Technical indicator function call."""
    name: str
    args: List[Any] = field(default_factory=list)
    symbol: Optional[str] = None
    accessor: Optional[str] = None  # For multi-output indicators (MACD.histogram)


@dataclass
class ComparisonNode:
    """Comparison expression (>, <, >=, <=, =, !=)."""
    operator: str
    left: Any
    right: Any


@dataclass
class CrossoverNode:
    """Crossover detection (fast line crosses above/below slow line)."""
    direction: str  # "above" or "below"
    fast: Any
    slow: Any


@dataclass
class LogicalNode:
    """Logical combination of conditions (AND, OR, NOT)."""
    type: str
    conditions: List[Union["ComparisonNode", "CrossoverNode", "LogicalNode"]]


# Type alias for any condition
ConditionNode = Union[ComparisonNode, CrossoverNode, LogicalNode]


@dataclass
class ConditionalNode:
    """Conditional branching in allocation (if/else, cond)."""
    condition: ConditionNode
    then_branch: Union[WeightNode, "ConditionalNode"]
    else_branch: Optional[Union[WeightNode, "ConditionalNode"]] = None


@dataclass
class ActionNode:
    """Trading action (buy, sell, close) with parameters."""
    type: str
    symbol: Optional[str] = None
    size_type: Optional[str] = None      # "percent_portfolio", "fixed_shares", etc.
    size_value: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    trailing_stop: Optional[float] = None
    order_type: str = "market"


@dataclass
class RuleNode:
    """Entry or exit rule with condition and actions."""
    type: str  # "entry" or "exit"
    condition: ConditionNode
    actions: List[ActionNode]


# Type alias for any allocation expression
AllocationNode = Union[AssetNode, WeightNode, ConditionalNode, FilterNode, UniverseNode]


@dataclass
class SymphonyNode:
    """Top-level symphony (portfolio allocation) definition."""
    name: str
    metadata: MetadataNode
    allocation: AllocationNode
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

The parser uses [Lark](https://github.com/lark-parser/lark), a modern parsing library for Python. Lark generates an LALR parser from the grammar, then a Transformer converts the parse tree to AST nodes.

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
    AssetNode, WeightNode, ConditionalNode, FilterNode, UniverseNode,
    ComparisonNode, LogicalNode, CrossoverNode,
    IndicatorNode, ActionNode, RuleNode
)

# Grammar string (abbreviated - see full grammar above)
SEXPR_GRAMMAR = r"""..."""


class SExprTransformer(Transformer):
    """Transform parse tree into AST nodes.

    Each method corresponds to a grammar rule. Lark calls these methods
    bottom-up, passing child results as arguments.
    """

    def start(self, items) -> List[Union[SymphonyNode, StrategyNode]]:
        """Entry point - returns list of all definitions."""
        return list(items)

    def symphony_def(self, items) -> SymphonyNode:
        """Transform symphony definition."""
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
        """Transform weight expression."""
        method = str(items[0]).replace("weight-", "").replace("-", "_")
        children = list(items[1:])
        return WeightNode(method=method, children=children)

    def comparison(self, items) -> ComparisonNode:
        """Transform comparison expression."""
        return ComparisonNode(
            operator=str(items[0]),
            left=items[1],
            right=items[2]
        )

    def crossover(self, items) -> CrossoverNode:
        """Transform crossover expression."""
        cross_type = str(items[0])
        return CrossoverNode(
            direction="above" if "above" in cross_type else "below",
            fast=items[1],
            slow=items[2]
        )

    def indicator_call(self, items) -> IndicatorNode:
        """Transform indicator function call."""
        name = str(items[0])
        args = list(items[1:])
        return IndicatorNode(name=name, args=args)

    def _unquote(self, s) -> str:
        """Remove surrounding quotes from string."""
        return str(s).strip('"')


class SExprParser:
    """S-Expression parser for LlamaTrade DSL.

    Usage:
        parser = SExprParser()
        ast = parser.parse('(defsymphony "Test" ...)')
    """

    def __init__(self):
        self.parser = Lark(
            SEXPR_GRAMMAR,
            parser='lalr',  # LALR(1) parser - fast and memory-efficient
            transformer=SExprTransformer()
        )

    def parse(self, source: str) -> List[Union[SymphonyNode, StrategyNode]]:
        """Parse S-expression source into AST nodes."""
        return self.parser.parse(source)

    def parse_file(self, path: str) -> List[Union[SymphonyNode, StrategyNode]]:
        """Parse S-expression file into AST nodes."""
        with open(path) as f:
            return self.parse(f.read())
```

---

## Serialization

The AST can be serialized to multiple formats. This enables bidirectional conversion between text, JSON, and the visual builder.

### S-Expression Serializer

Converts AST back to readable S-expression text:

```python
# libs/dsl/llamatrade_dsl/serializers.py

class SExprSerializer:
    """Serialize AST back to S-expression format.

    This enables round-tripping: parse text to AST, modify AST,
    serialize back to text.
    """

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

    def _allocation(self, node) -> str:
        if isinstance(node, AssetNode):
            opts = f" :weight {node.weight}" if node.weight else ""
            return f'(asset "{node.symbol}"{opts})'
        if isinstance(node, WeightNode):
            method = f"weight-{node.method.replace('_', '-')}"
            children = "\n     ".join(self._allocation(c) for c in node.children)
            return f"({method}\n    [{children}])"
        # ... handle other node types
```

### Visual Block Serializer

Converts AST to/from the JSON format used by the frontend visual builder:

```python
class VisualBlockSerializer:
    """Serialize AST to/from visual builder JSON format.

    The visual builder represents strategies as a tree of blocks.
    This serializer enables the text editor and visual builder
    to stay in sync.
    """

    def to_blocks(self, node: Union[SymphonyNode, StrategyNode]) -> dict:
        """Convert AST to visual block format for frontend."""
        return {
            "id": self._generate_id(),
            "type": "symphony" if isinstance(node, SymphonyNode) else "strategy",
            "name": node.name,
            "metadata": node.metadata.to_dict(),
            "children": self._node_to_blocks(
                node.allocation if isinstance(node, SymphonyNode) else node.rules
            )
        }

    def from_blocks(self, blocks: dict) -> Union[SymphonyNode, StrategyNode]:
        """Convert visual block format back to AST.

        Called when user modifies blocks in the visual builder.
        """
        if blocks["type"] == "symphony":
            return SymphonyNode(
                name=blocks["name"],
                metadata=MetadataNode(**blocks.get("metadata", {})),
                allocation=self._blocks_to_allocation(blocks["children"])
            )
        else:
            return StrategyNode(
                name=blocks["name"],
                metadata=MetadataNode(**blocks.get("metadata", {})),
                rules=self._blocks_to_rules(blocks["children"])
            )
```

---

## Execution Engine

The compiler transforms AST nodes into executable Python functions. This enables the same strategy definition to run in backtesting, paper trading, and live trading.

### Compilation Process

1. **AST traversal:** Walk the tree, compiling each node type
2. **Closure generation:** Build nested Python functions that capture context
3. **Indicator registration:** Register required indicators for pre-computation
4. **Output:** Callable functions that evaluate allocations or generate signals

### Compiler Code

```python
# libs/dsl/llamatrade_dsl/execution/compiler.py

@dataclass
class CompiledSymphony:
    """Compiled symphony ready for execution.

    The evaluate function takes market data and returns target allocations.
    """
    name: str
    rebalance_frequency: str
    benchmark: Optional[str]
    evaluate: callable  # (market_data) -> Dict[str, float]


@dataclass
class CompiledStrategy:
    """Compiled strategy ready for execution.

    The on_bar function is called for each bar and returns trading signals.
    """
    name: str
    timeframe: str
    symbols: List[str]
    on_bar: callable  # (symbol, bar, portfolio) -> List[Signal]


class StrategyCompiler:
    """Compile AST to executable functions.

    The compiler generates closures that capture indicator registries
    and universe definitions, then evaluate conditions and produce
    allocations or signals.
    """

    def __init__(self, indicator_registry, universe_registry):
        self.indicators = indicator_registry
        self.universes = universe_registry

    def compile_symphony(self, node: SymphonyNode) -> CompiledSymphony:
        """Compile symphony AST to executable allocation function."""
        allocation_fn = self._compile_allocation(node.allocation)

        return CompiledSymphony(
            name=node.name,
            rebalance_frequency=node.metadata.rebalance or "monthly",
            benchmark=node.metadata.benchmark,
            evaluate=allocation_fn
        )

    def compile_strategy(self, node: StrategyNode) -> CompiledStrategy:
        """Compile strategy AST to executable signal generator."""
        entry_rules = [r for r in node.rules if r.type == "entry"]
        exit_rules = [r for r in node.rules if r.type == "exit"]

        compiled_entries = [self._compile_rule(r) for r in entry_rules]
        compiled_exits = [self._compile_rule(r) for r in exit_rules]

        def on_bar(symbol: str, bar: dict, portfolio: dict) -> list:
            """Called for each bar. Returns list of signals."""
            signals = []
            context = {"symbol": symbol, "bar": bar, "portfolio": portfolio}

            # Check exit rules first (close positions before opening new)
            for check_exit, get_actions in compiled_exits:
                if check_exit(context):
                    signals.extend(get_actions(context))

            # Then entry rules
            for check_entry, get_actions in compiled_entries:
                if check_entry(context):
                    signals.extend(get_actions(context))

            return signals

        return CompiledStrategy(
            name=node.name,
            timeframe=node.metadata.timeframe or "1d",
            symbols=node.metadata.symbols or [],
            on_bar=on_bar
        )

    def _compile_allocation(self, node) -> callable:
        """Compile allocation node to function returning weights."""

        if isinstance(node, AssetNode):
            # Simple asset - return fixed weight
            return lambda ctx: {node.symbol: node.weight or 1.0}

        if isinstance(node, WeightNode):
            # Weighted combination - compile children, apply method
            child_fns = [self._compile_allocation(c) for c in node.children]
            method = node.method

            def allocate(ctx):
                # Collect assets from all children
                assets = {}
                for fn in child_fns:
                    assets.update(fn(ctx))

                # Apply weighting method
                if method == "equal":
                    weight = 1.0 / len(assets)
                    return {s: weight for s in assets}
                elif method == "inverse_volatility":
                    return self._inverse_vol_weights(assets, ctx)
                elif method == "risk_parity":
                    return self._risk_parity_weights(assets, ctx)
                return assets

            return allocate

        if isinstance(node, ConditionalNode):
            # Conditional - compile condition and both branches
            cond_fn = self._compile_condition(node.condition)
            then_fn = self._compile_allocation(node.then_branch)
            else_fn = (self._compile_allocation(node.else_branch)
                      if node.else_branch else lambda ctx: {})

            return lambda ctx: then_fn(ctx) if cond_fn(ctx) else else_fn(ctx)

    def _compile_condition(self, node) -> callable:
        """Compile condition to boolean function."""

        if isinstance(node, ComparisonNode):
            left_fn = self._compile_expr(node.left)
            right_fn = self._compile_expr(node.right)
            op = node.operator

            def check(ctx):
                left, right = left_fn(ctx), right_fn(ctx)
                if op == ">": return left > right
                if op == "<": return left < right
                if op == ">=": return left >= right
                if op == "<=": return left <= right
                if op in ("==", "="): return left == right
                if op == "!=": return left != right
                return False
            return check

        if isinstance(node, CrossoverNode):
            # Crossover requires comparing current and previous values
            fast_fn = self._compile_expr(node.fast)
            slow_fn = self._compile_expr(node.slow)

            def check(ctx):
                fast_curr, slow_curr = fast_fn(ctx), slow_fn(ctx)
                # Get previous bar values
                fast_prev = fast_fn({**ctx, "offset": 1})
                slow_prev = slow_fn({**ctx, "offset": 1})

                if node.direction == "above":
                    # Was below or equal, now above
                    return fast_prev <= slow_prev and fast_curr > slow_curr
                else:
                    # Was above or equal, now below
                    return fast_prev >= slow_prev and fast_curr < slow_curr
            return check

    def _compile_expr(self, node) -> callable:
        """Compile expression to value function."""
        if isinstance(node, IndicatorNode):
            name, args = node.name.lower(), node.args
            return lambda ctx: self.indicators.calculate(name, ctx.get("symbol"), *args)
        if isinstance(node, (int, float)):
            return lambda ctx: node
        if isinstance(node, str) and node.startswith("$"):
            # Symbol variable - look up in context
            return lambda ctx: ctx.get(node[1:])
        return lambda ctx: node
```

---

## AI Generation

Users can describe strategies in natural language, and Claude generates valid S-expression code. The AI generator includes examples to guide output format.

### How It Works

1. User describes strategy in plain English
2. System prompt instructs Claude on S-expression syntax
3. Few-shot examples demonstrate correct format
4. Claude generates DSL code
5. Parser validates the output
6. If invalid, optionally retry with error feedback

### Generator Code

```python
# libs/dsl/llamatrade_dsl/ai/generator.py

from anthropic import Anthropic

SYSTEM_PROMPT = """You are an expert trading strategy designer for LlamaTrade.
Convert natural language descriptions into S-expression trading strategies.

## S-Expression Format
- Use (defsymphony "name" {...} allocation) for portfolio allocations
- Use (defstrategy "name" {...} rules) for active trading
- Conditions: (and ...), (or ...), (> x y), (< x y), (crosses-above x y)
- Indicators: (rsi symbol period), (sma symbol period), (macd symbol fast slow signal)
- Weights: (weight-equal [...]), (weight-inverse-volatility [...])

Always output ONLY the DSL code, no explanations."""

EXAMPLES = '''
Example 1 - Simple portfolio:
User: "Create a tech-focused portfolio with equal weights in AAPL, MSFT, GOOGL"
Output:
(defsymphony "Tech Focus"
  {:rebalance :monthly}
  (weight-equal
    [(asset "AAPL")
     (asset "MSFT")
     (asset "GOOGL")]))

Example 2 - Conditional rotation:
User: "Buy bonds when RSI of SPY is overbought, otherwise stay in stocks"
Output:
(defsymphony "Risk Rotation"
  {:rebalance :daily}
  (if (> (rsi "SPY" 14) 70)
    (weight-equal [(asset "TLT") (asset "IEF")])
    (weight-equal [(asset "SPY") (asset "QQQ")])))

Example 3 - Mean reversion strategy:
User: "Buy when RSI drops below 30 with high volume, sell when RSI goes above 70"
Output:
(defstrategy "RSI Mean Reversion"
  {:timeframe :1h :symbols ["SPY"]}
  (entry
    (when (and (< (rsi 14) 30)
               (> volume (* 1.5 (sma-volume 20))))
      (buy :size 5% :stop-loss -2% :take-profit 4%)))
  (exit
    (when (> (rsi 14) 70)
      (close))))
'''


class AIStrategyGenerator:
    """Generate strategies from natural language using Claude.

    This enables users to describe strategies conversationally and
    receive valid, parseable DSL code.
    """

    def __init__(self, api_key: str = None):
        self.client = Anthropic(api_key=api_key)

    def generate(self, description: str, model: str = "claude-sonnet-4-20250514") -> str:
        """Generate DSL code from natural language description."""
        response = self.client.messages.create(
            model=model,
            max_tokens=2000,
            system=SYSTEM_PROMPT + "\n\n" + EXAMPLES,
            messages=[{"role": "user", "content": description}]
        )
        return response.content[0].text.strip()

    def generate_with_validation(self, description: str) -> tuple[str, bool, str | None]:
        """Generate and validate DSL code.

        Returns (code, is_valid, error_message).
        If is_valid is False, error_message contains the parse error.
        """
        from ..sexpr.parser import SExprParser

        code = self.generate(description)
        parser = SExprParser()

        try:
            parser.parse(code)
            return code, True, None
        except Exception as e:
            return code, False, str(e)

    def refine(self, code: str, feedback: str) -> str:
        """Refine existing DSL code based on user feedback.

        Useful when the initial generation needs adjustments.
        """
        response = self.client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=2000,
            system=SYSTEM_PROMPT,
            messages=[{
                "role": "user",
                "content": f"Current code:\n```\n{code}\n```\n\nFeedback: {feedback}\n\nPlease update the code."
            }]
        )
        return response.content[0].text.strip()
```

---

## Related Documentation

- [Strategy Service](services/strategy.md) - Full strategy service implementation details
- [Strategy Templates](strategy-templates.md) - Visual Strategy Builder block-based templates
- [Trading Strategies](trading-strategies.md) - Algorithmic trading concepts and approaches
