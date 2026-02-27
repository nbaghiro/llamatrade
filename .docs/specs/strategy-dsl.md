# Strategy DSL Implementation Specification

This document details the end-to-end implementation for both **S-Expression** and **Infix DSL** approaches, including parsing, AST representation, visual builder integration, AI generation, and execution.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              INPUT LAYER                                    │
├─────────────────┬─────────────────┬─────────────────┬───────────────────────┤
│   Visual        │   Natural       │   S-Expression  │    Infix DSL          │
│   Builder       │   Language      │   Text Editor   │    Text Editor        │
│   (React)       │   (Chat)        │   (Monaco)      │    (Monaco)           │
└────────┬────────┴────────┬────────┴────────┬────────┴──────────┬────────────┘
         │                 │                 │                   │
         │                 │                 ▼                   ▼
         │                 │        ┌────────────────────────────────────┐
         │                 │        │         PARSER LAYER               │
         │                 │        │  ┌──────────┐    ┌──────────┐      │
         │                 │        │  │ S-Expr   │    │ Infix    │      │
         │                 │        │  │ Parser   │    │ Parser   │      │
         │                 │        │  │ (Lark)   │    │ (Lark)   │      │
         │                 │        │  └────┬─────┘    └────┬─────┘      │
         │                 │        └───────┼───────────────┼────────────┘
         │                 │                │               │
         │                 ▼                ▼               ▼
         │        ┌────────────────────────────────────────────────────┐
         │        │              UNIFIED AST (Abstract Syntax Tree)    │
         │        │                                                    │
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
                  │                        │
    ┌─────────────┴─────────────┐          │
    │     BIDIRECTIONAL         │          │
    │     SERIALIZATION         │          │
    │                           │          │
    │  AST ←→ S-Expr Text       │          │
    │  AST ←→ Infix Text        │          │
    │  AST ←→ Visual Blocks     │          │
    │  AST ←→ JSON (storage)    │          │
    └───────────────────────────┘          │
                                           ▼
                  ┌────────────────────────────────────────────────────┐
                  │              SEMANTIC LAYER                        │
                  │                                                    │
                  │   • Type checking                                  │
                  │   • Symbol resolution (indicators, universes)      │
                  │   • Validation (required fields, ranges)           │
                  │   • Optimization (constant folding, CSE)           │
                  └────────────────────────────────────────────────────┘
                                           │
                                           ▼
                  ┌────────────────────────────────────────────────────┐
                  │        IR (Intermediate Representation)            │
                  │                                                    │
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

---

## Part 1: S-Expression DSL

### 1.1 Grammar Specification

```ebnf
(* S-Expression Grammar - Lark syntax *)

start: definition+

definition: symphony_def | strategy_def | indicator_def

symphony_def: "(" "defsymphony" STRING metadata? allocation_expr ")"
strategy_def: "(" "defstrategy" STRING metadata? rule+ ")"
indicator_def: "(" "defindicator" STRING param_list expr ")"

metadata: "{" metadata_pair* "}"
metadata_pair: KEYWORD value

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

(* Strategy rules *)
rule: entry_rule | exit_rule
entry_rule: "(" "entry" "(" "when" condition action+ ")" ")"
exit_rule: "(" "exit" "(" "when" condition action+ ")" ")"

action: "(" action_type action_opts* ")"
action_type: "buy" | "sell" | "close" | "close-long" | "close-short"
action_opts: KEYWORD value

(* Conditions *)
condition: comparison | logical_expr | crossover_expr

comparison: "(" COMPARATOR expr expr ")"
COMPARATOR: ">" | "<" | ">=" | "<=" | "=" | "!="

logical_expr: "(" "and" condition+ ")"
           | "(" "or" condition+ ")"
           | "(" "not" condition ")"

crossover_expr: "(" "crosses-above" expr expr ")"
             | "(" "crosses-below" expr expr ")"

(* Expressions *)
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

### 1.2 Example S-Expression Strategies

```clojure
;; Simple equal-weight symphony
(defsymphony "GPU Sector"
  {:rebalance :weekly
   :benchmark "SPY"
   :description "Equal weight GPU manufacturers"}

  (weight-equal
    [(asset "NVDA")
     (asset "AMD")
     (asset "INTC")
     (asset "TSM")]))


;; Conditional rotation strategy
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


;; Multi-condition cond expression
(defsymphony "Regime Adaptive"
  {:rebalance :weekly}

  (cond
    ;; Bear market
    [(< (sma "SPY" 50) (sma "SPY" 200))
     (weight-equal [(asset "TLT") (asset "GLD")])]

    ;; High volatility
    [(> (vix) 30)
     (weight-risk-parity
       [(asset "SPY" :max-weight 0.3)
        (asset "TLT")
        (asset "GLD")])]

    ;; Default: bull market
    [:else
     (weight-momentum
       [(universe "FAANG")])]))


;; Active trading strategy with entry/exit
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
              (crosses-below (close $symbol) (sma $symbol 50))
              (< (atr $symbol 14) (* 0.5 (sma (atr $symbol 14) 20))))
      (close $symbol))))


;; Custom indicator definition
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

### 1.3 Python Parser Implementation

```python
# libs/dsl/llamatrade_dsl/sexpr/parser.py

from lark import Lark, Transformer, v_args
from dataclasses import dataclass
from typing import Any, List, Optional, Union
from enum import Enum

# AST Node definitions (shared between both DSLs)
from ..ast import (
    SymphonyNode, StrategyNode, MetadataNode,
    AssetNode, WeightNode, ConditionalNode, FilterNode, UniverseNode,
    ConditionNode, ComparisonNode, LogicalNode, CrossoverNode,
    IndicatorNode, ActionNode, RuleNode, ExprNode
)

SEXPR_GRAMMAR = r"""
    start: definition+

    definition: symphony_def | strategy_def

    symphony_def: "(" "defsymphony" STRING metadata? allocation_expr ")"
    strategy_def: "(" "defstrategy" STRING metadata? rule+ ")"

    metadata: "{" metadata_pair* "}"
    metadata_pair: KEYWORD value -> meta_pair

    allocation_expr: asset_expr
                  | weight_expr
                  | conditional_expr
                  | filter_expr
                  | universe_expr

    asset_expr: "(" "asset" STRING asset_opt* ")"
    asset_opt: KEYWORD value

    weight_expr: "(" WEIGHT_METHOD "[" allocation_expr+ "]" ")"
    WEIGHT_METHOD: "weight-equal" | "weight-fixed" | "weight-inverse-volatility"
                | "weight-risk-parity" | "weight-momentum"

    conditional_expr: if_expr | cond_expr
    if_expr: "(" "if" condition allocation_expr allocation_expr? ")"
    cond_expr: "(" "cond" cond_branch+ ")"
    cond_branch: "[" condition allocation_expr "]"

    filter_expr: "(" FILTER_TYPE NUMBER KEYWORD expr ")"
    FILTER_TYPE: "filter-top" | "filter-bottom"

    universe_expr: "(" "universe" STRING ")"

    rule: entry_rule | exit_rule
    entry_rule: "(" "entry" when_clause ")"
    exit_rule: "(" "exit" when_clause ")"
    when_clause: "(" "when" condition action+ ")"

    action: "(" ACTION_TYPE SYMBOL? action_opt* ")"
    ACTION_TYPE: "buy" | "sell" | "close" | "close-long" | "close-short"
    action_opt: KEYWORD value

    condition: comparison | logical_and | logical_or | logical_not | crossover

    comparison: "(" COMPARATOR expr expr ")"
    COMPARATOR: ">" | "<" | ">=" | "<=" | "=" | "!="

    logical_and: "(" "and" condition+ ")"
    logical_or: "(" "or" condition+ ")"
    logical_not: "(" "not" condition ")"

    crossover: "(" CROSS_TYPE expr expr ")"
    CROSS_TYPE: "crosses-above" | "crosses-below"

    expr: NUMBER | STRING | SYMBOL | KEYWORD | indicator_call | arithmetic

    indicator_call: "(" INDICATOR expr* ")"
    INDICATOR: "rsi" | "sma" | "ema" | "macd" | "bbands" | "atr"
            | "volume" | "price" | "high" | "low" | "open" | "close"
            | "sma-volume" | "vix" | "momentum" | "keltner"
            | "highest" | "lowest"

    arithmetic: "(" OP expr expr ")"
    OP: "+" | "-" | "*" | "/"

    value: NUMBER | STRING | KEYWORD | SYMBOL | "[" value* "]"

    STRING: /"[^"]*"/
    NUMBER: /-?[0-9]+(\.[0-9]+)?%?/
    SYMBOL: /\$[a-zA-Z_][a-zA-Z0-9_-]*/
    KEYWORD: /:[a-zA-Z_][a-zA-Z0-9_-]*/
    NAME: /[a-zA-Z_][a-zA-Z0-9_-]*/

    COMMENT: /;[^\n]*/
    %import common.WS
    %ignore WS
    %ignore COMMENT
"""


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

    def strategy_def(self, items) -> StrategyNode:
        name = self._unquote(items[0])
        metadata = {}
        rules = []

        for item in items[1:]:
            if isinstance(item, dict):
                metadata = item
            elif isinstance(item, RuleNode):
                rules.append(item)

        return StrategyNode(
            name=name,
            metadata=MetadataNode(**metadata),
            rules=rules
        )

    def metadata(self, items) -> dict:
        return dict(items)

    def meta_pair(self, items):
        key = self._keyword_to_str(items[0])
        value = self._process_value(items[1])
        return (key, value)

    def asset_expr(self, items) -> AssetNode:
        symbol = self._unquote(items[0])
        opts = dict(items[1:]) if len(items) > 1 else {}
        return AssetNode(symbol=symbol, **opts)

    def asset_opt(self, items):
        return (self._keyword_to_str(items[0]), self._process_value(items[1]))

    def weight_expr(self, items) -> WeightNode:
        method = str(items[0]).replace("weight-", "").replace("-", "_")
        children = list(items[1:])
        return WeightNode(method=method, children=children)

    def if_expr(self, items) -> ConditionalNode:
        condition = items[0]
        then_branch = items[1]
        else_branch = items[2] if len(items) > 2 else None
        return ConditionalNode(
            condition=condition,
            then_branch=then_branch,
            else_branch=else_branch
        )

    def cond_expr(self, items) -> ConditionalNode:
        # Convert cond to nested if-else
        branches = list(items)
        return self._cond_to_if(branches)

    def _cond_to_if(self, branches) -> ConditionalNode:
        if len(branches) == 1:
            cond, alloc = branches[0]
            return ConditionalNode(condition=cond, then_branch=alloc)

        cond, alloc = branches[0]
        return ConditionalNode(
            condition=cond,
            then_branch=alloc,
            else_branch=self._cond_to_if(branches[1:])
        )

    def cond_branch(self, items):
        return (items[0], items[1])

    def filter_expr(self, items) -> FilterNode:
        filter_type = str(items[0])
        count = int(items[1])
        by_metric = self._keyword_to_str(items[2])
        source = items[3]

        return FilterNode(
            type="top" if "top" in filter_type else "bottom",
            count=count,
            by=by_metric,
            source=source
        )

    def universe_expr(self, items) -> UniverseNode:
        return UniverseNode(name=self._unquote(items[0]))

    def comparison(self, items) -> ComparisonNode:
        return ComparisonNode(
            operator=str(items[0]),
            left=items[1],
            right=items[2]
        )

    def logical_and(self, items) -> LogicalNode:
        return LogicalNode(type="and", conditions=list(items))

    def logical_or(self, items) -> LogicalNode:
        return LogicalNode(type="or", conditions=list(items))

    def logical_not(self, items) -> LogicalNode:
        return LogicalNode(type="not", conditions=[items[0]])

    def crossover(self, items) -> CrossoverNode:
        cross_type = str(items[0])
        return CrossoverNode(
            direction="above" if "above" in cross_type else "below",
            fast=items[1],
            slow=items[2]
        )

    def indicator_call(self, items) -> IndicatorNode:
        name = str(items[0])
        args = list(items[1:])
        return IndicatorNode(name=name, args=args)

    def entry_rule(self, items) -> RuleNode:
        when_clause = items[0]
        return RuleNode(type="entry", **when_clause)

    def exit_rule(self, items) -> RuleNode:
        when_clause = items[0]
        return RuleNode(type="exit", **when_clause)

    def when_clause(self, items) -> dict:
        return {
            "condition": items[0],
            "actions": list(items[1:])
        }

    def action(self, items) -> ActionNode:
        action_type = str(items[0]).replace("-", "_")
        symbol = None
        opts = {}

        for item in items[1:]:
            if isinstance(item, str) and item.startswith("$"):
                symbol = item
            elif isinstance(item, tuple):
                opts[item[0]] = item[1]

        return ActionNode(type=action_type, symbol=symbol, **opts)

    def action_opt(self, items):
        return (self._keyword_to_str(items[0]), self._process_value(items[1]))

    def arithmetic(self, items) -> ExprNode:
        return ExprNode(
            type="arithmetic",
            operator=str(items[0]),
            left=items[1],
            right=items[2]
        )

    def value(self, items):
        if len(items) == 1:
            return self._process_value(items[0])
        return [self._process_value(v) for v in items]

    def _unquote(self, s) -> str:
        return str(s).strip('"')

    def _keyword_to_str(self, k) -> str:
        return str(k).lstrip(':').replace('-', '_')

    def _process_value(self, v):
        s = str(v)
        if s.startswith('"'):
            return s.strip('"')
        if s.startswith(':'):
            return s.lstrip(':')
        if s.endswith('%'):
            return float(s.rstrip('%')) / 100
        try:
            return int(s)
        except ValueError:
            try:
                return float(s)
            except ValueError:
                return s


class SExprParser:
    """S-Expression parser for LlamaTrade DSL."""

    def __init__(self):
        self.parser = Lark(SEXPR_GRAMMAR, parser='lalr', transformer=SExprTransformer())

    def parse(self, source: str) -> List[Union[SymphonyNode, StrategyNode]]:
        """Parse S-expression source into AST nodes."""
        return self.parser.parse(source)

    def parse_file(self, path: str) -> List[Union[SymphonyNode, StrategyNode]]:
        """Parse S-expression file into AST nodes."""
        with open(path) as f:
            return self.parse(f.read())
```

---

## Part 2: Infix DSL

### 2.1 Grammar Specification

```ebnf
(* Infix DSL Grammar - Lark syntax *)

start: definition+

definition: symphony_def | strategy_def | indicator_def

(* Symphony definition *)
symphony_def: "symphony" STRING block
strategy_def: "strategy" STRING block
indicator_def: "indicator" STRING param_list block

block: "{" statement* "}"

statement: metadata_stmt
        | allocate_stmt
        | if_stmt
        | entry_stmt
        | exit_stmt
        | let_stmt
        | return_stmt

(* Metadata *)
metadata_stmt: IDENT ":" value

(* Allocation *)
allocate_stmt: "allocate" alloc_method alloc_target

alloc_method: "equal_weight" | "fixed_weight" | "inverse_volatility"
           | "risk_parity" | "momentum_weight"

alloc_target: asset_list | filter_expr | universe_ref

asset_list: "[" asset ("," asset)* "]"
asset: SYMBOL ("@" PERCENT)?

filter_expr: "top" NUMBER "from" universe_ref "by" IDENT
          | "bottom" NUMBER "from" universe_ref "by" IDENT

universe_ref: IDENT | STRING

(* Conditionals *)
if_stmt: "if" expr block ("else" "if" expr block)* ("else" block)?

(* Strategy rules *)
entry_stmt: "entry" "when" expr block
exit_stmt: "exit" "when" expr block

(* Actions inside entry/exit blocks *)
action_stmt: buy_action | sell_action | close_action | set_action
buy_action: "buy" size_expr
sell_action: "sell" size_expr
close_action: "close" "position"
set_action: "set" IDENT expr

size_expr: PERCENT "of" "portfolio"
        | NUMBER "shares"
        | "$" NUMBER

(* Expressions *)
expr: or_expr

or_expr: and_expr ("OR" and_expr)*
and_expr: not_expr ("AND" not_expr)*
not_expr: "NOT" not_expr | comparison_expr

comparison_expr: additive_expr (COMP_OP additive_expr)?
              | additive_expr "crosses" DIRECTION additive_expr
              | additive_expr "becomes" value

COMP_OP: ">" | "<" | ">=" | "<=" | "==" | "!="
DIRECTION: "above" | "below"

additive_expr: multiplicative_expr (("+"|"-") multiplicative_expr)*
multiplicative_expr: unary_expr (("*"|"/") unary_expr)*
unary_expr: "-" unary_expr | primary_expr

primary_expr: NUMBER
           | STRING
           | PERCENT
           | SYMBOL
           | IDENT
           | indicator_call
           | "(" expr ")"

indicator_call: INDICATOR "(" arg_list? ")"
INDICATOR: "RSI" | "SMA" | "EMA" | "MACD" | "BBands" | "ATR"
        | "Volume" | "Price" | "High" | "Low" | "Open" | "Close"
        | "SMA_Volume" | "VIX" | "Momentum" | "Keltner"

arg_list: expr ("," expr)*

(* Let binding for custom indicators *)
let_stmt: "let" IDENT "=" expr

return_stmt: "return" expr

(* Values *)
value: NUMBER | STRING | PERCENT | IDENT | "[" value ("," value)* "]"

param_list: "(" param ("," param)* ")"
param: IDENT (":" type_hint)?
type_hint: "number" | "period" | "percent"

(* Terminals *)
STRING: /"[^"]*"/
NUMBER: /-?[0-9]+(\.[0-9]+)?/
PERCENT: /-?[0-9]+(\.[0-9]+)?%/
SYMBOL: /[A-Z][A-Z0-9]*/
IDENT: /[a-z_][a-zA-Z0-9_]*/

COMMENT: /--[^\n]*/ | /\/\*(.|\n)*?\*\//
%import common.WS
%ignore WS
%ignore COMMENT
```

### 2.2 Example Infix Strategies

```
-- Simple equal-weight symphony
symphony "GPU Sector" {
  rebalance: weekly
  benchmark: SPY
  description: "Equal weight GPU manufacturers"

  allocate equal_weight [NVDA, AMD, INTC, TSM]
}


-- Conditional rotation with if/else
symphony "Risk-On Risk-Off" {
  rebalance: daily

  if RSI(SPY, 14) > 70 {
    -- Risk-off: rotate to bonds
    allocate equal_weight [TLT, IEF, SHY]
  } else {
    -- Risk-on: momentum stocks
    allocate inverse_volatility (top 10 from SP500 by momentum_12m)
  }
}


-- Multi-condition with else-if chains
symphony "Regime Adaptive" {
  rebalance: weekly

  if SMA(SPY, 50) < SMA(SPY, 200) {
    -- Bear market
    allocate equal_weight [TLT, GLD]
  } else if VIX() > 30 {
    -- High volatility
    allocate risk_parity [SPY @ 30%, TLT, GLD]
  } else {
    -- Bull market
    allocate momentum_weight [AAPL, MSFT, GOOGL, AMZN, META]
  }
}


-- Active trading strategy
strategy "RSI Mean Reversion" {
  timeframe: 1h
  symbols: [AAPL, MSFT, GOOGL, AMZN]

  entry when RSI(14) < 30 AND Volume > SMA_Volume(20) * 1.5 {
    buy 5% of portfolio
    set stop_loss -2%
    set take_profit 4%
    set trailing_stop 1%
  }

  exit when RSI(14) > 70 OR Price crosses below SMA(50) {
    close position
  }
}


-- Multiple entry/exit conditions
strategy "Breakout + Mean Reversion" {
  timeframe: 4h
  symbols: [SPY, QQQ, IWM]

  -- Breakout entry
  entry when Price > High(20) AND Volume > SMA_Volume(20) * 2 {
    buy 3% of portfolio
    set stop_loss -1.5%
    set take_profit 5%
  }

  -- Mean reversion entry
  entry when RSI(14) < 25 AND Price < BBands(20, 2).lower {
    buy 5% of portfolio
    set stop_loss -3%
    set take_profit 4%
  }

  -- Trailing stop exit
  exit when Price < High(5) * 0.97 {
    close position
  }

  -- Take profit on momentum exhaustion
  exit when RSI(14) > 80 AND MACD(12, 26, 9).histogram < 0 {
    close position
  }
}


-- Custom indicator definition
indicator "Squeeze" (length: period, bb_mult: number, kc_mult: number) {
  let bb = BBands(length, bb_mult)
  let kc = Keltner(length, kc_mult)

  let squeeze_on = bb.lower > kc.lower AND bb.upper < kc.upper
  let momentum = Close - SMA((High(length) + Low(length)) / 2, length)

  return { squeeze: squeeze_on, momentum: momentum }
}


-- Using custom indicator
strategy "TTM Squeeze" {
  timeframe: 4h
  symbols: [SPY]

  entry when Squeeze(20, 2, 1.5).squeeze becomes false AND Squeeze(20, 2, 1.5).momentum > 0 {
    buy 10% of portfolio
    set stop_loss -2%
  }

  exit when Squeeze(20, 2, 1.5).momentum crosses below 0 {
    close position
  }
}
```

### 2.3 Python Parser Implementation

```python
# libs/dsl/llamatrade_dsl/infix/parser.py

from lark import Lark, Transformer, v_args
from typing import Any, List, Optional, Union

from ..ast import (
    SymphonyNode, StrategyNode, MetadataNode,
    AssetNode, WeightNode, ConditionalNode, FilterNode, UniverseNode,
    ConditionNode, ComparisonNode, LogicalNode, CrossoverNode,
    IndicatorNode, ActionNode, RuleNode, ExprNode, LetNode
)

INFIX_GRAMMAR = r"""
    start: definition+

    definition: symphony_def | strategy_def | indicator_def

    symphony_def: "symphony" STRING block
    strategy_def: "strategy" STRING block
    indicator_def: "indicator" STRING param_list block

    block: "{" statement* "}"

    ?statement: metadata_stmt
             | allocate_stmt
             | if_stmt
             | entry_stmt
             | exit_stmt
             | action_stmt
             | let_stmt
             | return_stmt

    metadata_stmt: IDENT ":" value

    allocate_stmt: "allocate" ALLOC_METHOD alloc_target
    ALLOC_METHOD: "equal_weight" | "fixed_weight" | "inverse_volatility"
               | "risk_parity" | "momentum_weight"

    alloc_target: asset_list | filter_expr | "(" filter_expr ")"

    asset_list: "[" asset ("," asset)* ","? "]"
    asset: TICKER weight_spec?
    weight_spec: "@" PERCENT

    filter_expr: FILTER_DIR NUMBER "from" universe_name "by" IDENT
    FILTER_DIR: "top" | "bottom"
    universe_name: TICKER | STRING

    if_stmt: "if" expr block else_clause?
    else_clause: "else" "if" expr block else_clause?
              | "else" block

    entry_stmt: "entry" "when" expr block
    exit_stmt: "exit" "when" expr block

    action_stmt: buy_action | sell_action | close_action | set_action
    buy_action: "buy" size_expr
    sell_action: "sell" size_expr
    close_action: "close" "position"
    set_action: "set" IDENT expr

    size_expr: PERCENT "of" "portfolio" -> pct_portfolio
            | NUMBER "shares" -> fixed_shares
            | "$" NUMBER -> fixed_dollars

    let_stmt: "let" IDENT "=" expr
    return_stmt: "return" expr

    ?expr: or_expr
    ?or_expr: and_expr ("OR" and_expr)* -> logical_or
    ?and_expr: not_expr ("AND" not_expr)* -> logical_and
    ?not_expr: "NOT" not_expr -> logical_not
            | comp_expr

    ?comp_expr: additive (COMP_OP additive)? -> comparison
             | additive "crosses" DIRECTION additive -> crossover
             | additive "becomes" value -> becomes

    COMP_OP: ">" | "<" | ">=" | "<=" | "==" | "!="
    DIRECTION: "above" | "below"

    ?additive: multiplicative (("+"|"-") multiplicative)*
    ?multiplicative: unary (("*"|"/") unary)*
    ?unary: "-" unary -> neg
         | primary

    ?primary: NUMBER -> number
           | STRING -> string
           | PERCENT -> percent
           | TICKER -> ticker
           | IDENT -> ident
           | indicator_call
           | "(" expr ")"

    indicator_call: INDICATOR "(" arg_list? ")" accessor?
    INDICATOR: "RSI" | "SMA" | "EMA" | "MACD" | "BBands" | "ATR"
            | "Volume" | "Price" | "High" | "Low" | "Open" | "Close"
            | "SMA_Volume" | "VIX" | "Momentum" | "Keltner"
            | "Squeeze"

    accessor: "." IDENT

    arg_list: expr ("," expr)*

    value: NUMBER -> number
        | STRING -> string
        | PERCENT -> percent
        | IDENT -> ident
        | TICKER -> ticker
        | "[" value ("," value)* ","? "]" -> value_list

    param_list: "(" param ("," param)* ")"
    param: IDENT (":" TYPE)?
    TYPE: "number" | "period" | "percent"

    STRING: /"[^"]*"/
    NUMBER: /-?[0-9]+(\.[0-9]+)?/
    PERCENT: /-?[0-9]+(\.[0-9]+)?%/
    TICKER: /[A-Z][A-Z0-9]{0,5}/
    IDENT: /[a-z_][a-zA-Z0-9_]*/

    COMMENT: /--[^\n]*/ | /\/\*(.|\n)*?\*\//
    %import common.WS
    %ignore WS
    %ignore COMMENT
"""


class InfixTransformer(Transformer):
    """Transform infix parse tree into AST nodes."""

    def start(self, items):
        return list(items)

    def symphony_def(self, items) -> SymphonyNode:
        name = self._unquote(items[0])
        block = items[1]

        metadata = {}
        allocation = None

        for stmt in block:
            if isinstance(stmt, tuple) and stmt[0] == 'metadata':
                metadata[stmt[1]] = stmt[2]
            elif isinstance(stmt, (WeightNode, ConditionalNode)):
                allocation = stmt

        return SymphonyNode(
            name=name,
            metadata=MetadataNode(**metadata),
            allocation=allocation
        )

    def strategy_def(self, items) -> StrategyNode:
        name = self._unquote(items[0])
        block = items[1]

        metadata = {}
        rules = []

        for stmt in block:
            if isinstance(stmt, tuple) and stmt[0] == 'metadata':
                metadata[stmt[1]] = stmt[2]
            elif isinstance(stmt, RuleNode):
                rules.append(stmt)

        return StrategyNode(
            name=name,
            metadata=MetadataNode(**metadata),
            rules=rules
        )

    def block(self, items):
        return list(items)

    def metadata_stmt(self, items):
        return ('metadata', str(items[0]), self._process_value(items[1]))

    def allocate_stmt(self, items) -> WeightNode:
        method = str(items[0]).lower()
        target = items[1]

        if isinstance(target, list):
            # Asset list
            return WeightNode(method=method, children=target)
        else:
            # Filter or universe
            return WeightNode(method=method, children=[target])

    def asset_list(self, items):
        return list(items)

    def asset(self, items) -> AssetNode:
        symbol = str(items[0])
        weight = None
        if len(items) > 1:
            weight = items[1]
        return AssetNode(symbol=symbol, weight=weight)

    def weight_spec(self, items):
        return self._percent_to_float(items[0])

    def filter_expr(self, items) -> FilterNode:
        direction = str(items[0])
        count = int(items[1])
        universe = items[2]
        by_metric = str(items[3])

        return FilterNode(
            type=direction,
            count=count,
            source=UniverseNode(name=str(universe)),
            by=by_metric
        )

    def if_stmt(self, items) -> ConditionalNode:
        condition = items[0]
        then_block = items[1]
        else_clause = items[2] if len(items) > 2 else None

        then_branch = self._block_to_allocation(then_block)
        else_branch = else_clause

        return ConditionalNode(
            condition=condition,
            then_branch=then_branch,
            else_branch=else_branch
        )

    def else_clause(self, items):
        if len(items) == 1:
            # Simple else block
            return self._block_to_allocation(items[0])
        else:
            # else if chain
            return items[0]

    def _block_to_allocation(self, block):
        for stmt in block:
            if isinstance(stmt, (WeightNode, ConditionalNode)):
                return stmt
        return None

    def entry_stmt(self, items) -> RuleNode:
        condition = items[0]
        actions = [s for s in items[1] if isinstance(s, ActionNode)]
        return RuleNode(type="entry", condition=condition, actions=actions)

    def exit_stmt(self, items) -> RuleNode:
        condition = items[0]
        actions = [s for s in items[1] if isinstance(s, ActionNode)]
        return RuleNode(type="exit", condition=condition, actions=actions)

    def buy_action(self, items) -> ActionNode:
        size = items[0]
        return ActionNode(type="buy", **size)

    def sell_action(self, items) -> ActionNode:
        size = items[0]
        return ActionNode(type="sell", **size)

    def close_action(self, items) -> ActionNode:
        return ActionNode(type="close")

    def set_action(self, items) -> ActionNode:
        param = str(items[0])
        value = items[1]
        return ActionNode(type="set", param=param, value=value)

    def pct_portfolio(self, items):
        return {"size_type": "percent_portfolio", "size_value": self._percent_to_float(items[0])}

    def fixed_shares(self, items):
        return {"size_type": "fixed_shares", "size_value": int(items[0])}

    def fixed_dollars(self, items):
        return {"size_type": "fixed_dollars", "size_value": float(items[0])}

    def logical_or(self, items):
        if len(items) == 1:
            return items[0]
        return LogicalNode(type="or", conditions=list(items))

    def logical_and(self, items):
        if len(items) == 1:
            return items[0]
        return LogicalNode(type="and", conditions=list(items))

    def logical_not(self, items):
        return LogicalNode(type="not", conditions=[items[0]])

    def comparison(self, items):
        if len(items) == 1:
            return items[0]
        return ComparisonNode(
            operator=str(items[1]),
            left=items[0],
            right=items[2]
        )

    def crossover(self, items):
        return CrossoverNode(
            direction=str(items[1]),
            fast=items[0],
            slow=items[2]
        )

    def becomes(self, items):
        return ComparisonNode(
            operator="becomes",
            left=items[0],
            right=items[1]
        )

    def indicator_call(self, items) -> IndicatorNode:
        name = str(items[0])
        args = []
        accessor = None

        for item in items[1:]:
            if isinstance(item, list):
                args = item
            elif isinstance(item, str):
                accessor = item

        return IndicatorNode(name=name, args=args, accessor=accessor)

    def accessor(self, items):
        return str(items[0])

    def arg_list(self, items):
        return list(items)

    def additive(self, items):
        if len(items) == 1:
            return items[0]
        # Build left-associative expression tree
        result = items[0]
        for i in range(1, len(items), 2):
            op = str(items[i])
            right = items[i + 1]
            result = ExprNode(type="arithmetic", operator=op, left=result, right=right)
        return result

    def multiplicative(self, items):
        if len(items) == 1:
            return items[0]
        result = items[0]
        for i in range(1, len(items), 2):
            op = str(items[i])
            right = items[i + 1]
            result = ExprNode(type="arithmetic", operator=op, left=result, right=right)
        return result

    def neg(self, items):
        return ExprNode(type="negate", operand=items[0])

    def number(self, items):
        s = str(items[0])
        return int(s) if '.' not in s else float(s)

    def string(self, items):
        return self._unquote(items[0])

    def percent(self, items):
        return self._percent_to_float(items[0])

    def ticker(self, items):
        return str(items[0])

    def ident(self, items):
        return str(items[0])

    def value_list(self, items):
        return list(items)

    def let_stmt(self, items) -> LetNode:
        name = str(items[0])
        value = items[1]
        return LetNode(name=name, value=value)

    def return_stmt(self, items):
        return ("return", items[0])

    def _unquote(self, s) -> str:
        return str(s).strip('"')

    def _percent_to_float(self, s) -> float:
        return float(str(s).rstrip('%')) / 100

    def _process_value(self, v):
        if isinstance(v, (int, float, list)):
            return v
        s = str(v)
        if s.endswith('%'):
            return float(s.rstrip('%')) / 100
        try:
            return int(s)
        except ValueError:
            try:
                return float(s)
            except ValueError:
                return s


class InfixParser:
    """Infix DSL parser for LlamaTrade."""

    def __init__(self):
        self.parser = Lark(INFIX_GRAMMAR, parser='lalr', transformer=InfixTransformer())

    def parse(self, source: str) -> List[Union[SymphonyNode, StrategyNode]]:
        """Parse infix DSL source into AST nodes."""
        return self.parser.parse(source)

    def parse_file(self, path: str) -> List[Union[SymphonyNode, StrategyNode]]:
        """Parse infix DSL file into AST nodes."""
        with open(path) as f:
            return self.parse(f.read())
```

---

## Part 3: Unified AST (Abstract Syntax Tree)

Both DSLs parse into the same AST structure, enabling shared tooling.

```python
# libs/dsl/llamatrade_dsl/ast.py

from dataclasses import dataclass, field
from typing import Any, List, Optional, Union
from enum import Enum


class WeightMethod(str, Enum):
    EQUAL = "equal"
    FIXED = "fixed"
    INVERSE_VOLATILITY = "inverse_volatility"
    RISK_PARITY = "risk_parity"
    MOMENTUM = "momentum"


class LogicalOp(str, Enum):
    AND = "and"
    OR = "or"
    NOT = "not"


class ActionType(str, Enum):
    BUY = "buy"
    SELL = "sell"
    CLOSE = "close"
    CLOSE_LONG = "close_long"
    CLOSE_SHORT = "close_short"
    SET = "set"


@dataclass
class MetadataNode:
    """Strategy/symphony metadata."""
    rebalance: Optional[str] = None
    benchmark: Optional[str] = None
    description: Optional[str] = None
    timeframe: Optional[str] = None
    symbols: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if v is not None}


@dataclass
class AssetNode:
    """Single asset in allocation."""
    symbol: str
    weight: Optional[float] = None
    max_weight: Optional[float] = None
    min_weight: Optional[float] = None

    def to_dict(self) -> dict:
        result = {"type": "asset", "symbol": self.symbol}
        if self.weight is not None:
            result["weight"] = self.weight
        return result


@dataclass
class UniverseNode:
    """Reference to a universe of assets."""
    name: str
    symbols: Optional[List[str]] = None

    def to_dict(self) -> dict:
        result = {"type": "universe", "name": self.name}
        if self.symbols:
            result["symbols"] = self.symbols
        return result


@dataclass
class FilterNode:
    """Filter a universe by metric."""
    type: str  # "top" or "bottom"
    count: int
    by: str  # metric name
    source: Union["UniverseNode", "WeightNode"]

    def to_dict(self) -> dict:
        return {
            "type": "filter",
            "filter_type": self.type,
            "count": self.count,
            "by": self.by,
            "source": self.source.to_dict() if hasattr(self.source, 'to_dict') else self.source
        }


@dataclass
class WeightNode:
    """Weighted allocation of assets."""
    method: str
    children: List[Union[AssetNode, FilterNode, UniverseNode, "WeightNode"]]
    params: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "type": "weight",
            "method": self.method,
            "children": [c.to_dict() if hasattr(c, 'to_dict') else c for c in self.children],
            "params": self.params
        }


@dataclass
class IndicatorNode:
    """Indicator function call."""
    name: str
    args: List[Any] = field(default_factory=list)
    symbol: Optional[str] = None
    accessor: Optional[str] = None  # For multi-output like MACD.histogram

    def to_dict(self) -> dict:
        result = {"type": "indicator", "name": self.name, "args": self.args}
        if self.symbol:
            result["symbol"] = self.symbol
        if self.accessor:
            result["accessor"] = self.accessor
        return result


@dataclass
class ComparisonNode:
    """Comparison expression."""
    operator: str
    left: Any
    right: Any

    def to_dict(self) -> dict:
        return {
            "type": "comparison",
            "operator": self.operator,
            "left": self.left.to_dict() if hasattr(self.left, 'to_dict') else self.left,
            "right": self.right.to_dict() if hasattr(self.right, 'to_dict') else self.right
        }


@dataclass
class CrossoverNode:
    """Crossover condition."""
    direction: str  # "above" or "below"
    fast: Any
    slow: Any

    def to_dict(self) -> dict:
        return {
            "type": "crossover",
            "direction": self.direction,
            "fast": self.fast.to_dict() if hasattr(self.fast, 'to_dict') else self.fast,
            "slow": self.slow.to_dict() if hasattr(self.slow, 'to_dict') else self.slow
        }


@dataclass
class LogicalNode:
    """Logical expression (AND/OR/NOT)."""
    type: str
    conditions: List[Union["ComparisonNode", "CrossoverNode", "LogicalNode"]]

    def to_dict(self) -> dict:
        return {
            "type": "logical",
            "op": self.type,
            "conditions": [c.to_dict() if hasattr(c, 'to_dict') else c for c in self.conditions]
        }


ConditionNode = Union[ComparisonNode, CrossoverNode, LogicalNode]


@dataclass
class ConditionalNode:
    """Conditional branching in allocation."""
    condition: ConditionNode
    then_branch: Union[WeightNode, "ConditionalNode"]
    else_branch: Optional[Union[WeightNode, "ConditionalNode"]] = None

    def to_dict(self) -> dict:
        result = {
            "type": "conditional",
            "condition": self.condition.to_dict() if hasattr(self.condition, 'to_dict') else self.condition,
            "then": self.then_branch.to_dict() if hasattr(self.then_branch, 'to_dict') else self.then_branch
        }
        if self.else_branch:
            result["else"] = self.else_branch.to_dict() if hasattr(self.else_branch, 'to_dict') else self.else_branch
        return result


@dataclass
class ActionNode:
    """Trading action."""
    type: str
    symbol: Optional[str] = None
    size_type: Optional[str] = None
    size_value: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    trailing_stop: Optional[float] = None
    order_type: str = "market"
    param: Optional[str] = None  # For "set" actions
    value: Optional[Any] = None

    def to_dict(self) -> dict:
        result = {"type": self.type}
        for k, v in self.__dict__.items():
            if v is not None and k != 'type':
                result[k] = v
        return result


@dataclass
class RuleNode:
    """Entry or exit rule."""
    type: str  # "entry" or "exit"
    condition: ConditionNode
    actions: List[ActionNode]

    def to_dict(self) -> dict:
        return {
            "type": self.type,
            "condition": self.condition.to_dict() if hasattr(self.condition, 'to_dict') else self.condition,
            "actions": [a.to_dict() for a in self.actions]
        }


@dataclass
class ExprNode:
    """Arithmetic or other expression."""
    type: str
    operator: Optional[str] = None
    left: Optional[Any] = None
    right: Optional[Any] = None
    operand: Optional[Any] = None

    def to_dict(self) -> dict:
        result = {"type": self.type}
        if self.operator:
            result["operator"] = self.operator
        if self.left:
            result["left"] = self.left.to_dict() if hasattr(self.left, 'to_dict') else self.left
        if self.right:
            result["right"] = self.right.to_dict() if hasattr(self.right, 'to_dict') else self.right
        if self.operand:
            result["operand"] = self.operand.to_dict() if hasattr(self.operand, 'to_dict') else self.operand
        return result


@dataclass
class LetNode:
    """Let binding for custom indicators."""
    name: str
    value: Any

    def to_dict(self) -> dict:
        return {
            "type": "let",
            "name": self.name,
            "value": self.value.to_dict() if hasattr(self.value, 'to_dict') else self.value
        }


AllocationNode = Union[AssetNode, WeightNode, ConditionalNode, FilterNode, UniverseNode]


@dataclass
class SymphonyNode:
    """Top-level symphony definition."""
    name: str
    metadata: MetadataNode
    allocation: AllocationNode
    version: int = 1

    def to_dict(self) -> dict:
        return {
            "type": "symphony",
            "name": self.name,
            "version": self.version,
            "metadata": self.metadata.to_dict(),
            "allocation": self.allocation.to_dict() if hasattr(self.allocation, 'to_dict') else self.allocation
        }

    def to_json(self) -> str:
        import json
        return json.dumps(self.to_dict(), indent=2)


@dataclass
class StrategyNode:
    """Top-level strategy definition."""
    name: str
    metadata: MetadataNode
    rules: List[RuleNode]
    version: int = 1

    def to_dict(self) -> dict:
        return {
            "type": "strategy",
            "name": self.name,
            "version": self.version,
            "metadata": self.metadata.to_dict(),
            "rules": [r.to_dict() for r in self.rules]
        }

    def to_json(self) -> str:
        import json
        return json.dumps(self.to_dict(), indent=2)
```

---

## Part 4: Bidirectional Serialization

Convert between AST, DSL text, and visual builder format.

```python
# libs/dsl/llamatrade_dsl/serializers.py

from typing import Union
from .ast import *


class SExprSerializer:
    """Serialize AST back to S-expression format."""

    def serialize(self, node: Union[SymphonyNode, StrategyNode]) -> str:
        if isinstance(node, SymphonyNode):
            return self._symphony(node)
        return self._strategy(node)

    def _symphony(self, node: SymphonyNode) -> str:
        lines = [f'(defsymphony "{node.name}"']
        lines.append(self._metadata(node.metadata))
        lines.append("")
        lines.append(self._indent(self._allocation(node.allocation), 2))
        lines.append(")")
        return "\n".join(lines)

    def _strategy(self, node: StrategyNode) -> str:
        lines = [f'(defstrategy "{node.name}"']
        lines.append(self._metadata(node.metadata))
        for rule in node.rules:
            lines.append("")
            lines.append(self._indent(self._rule(rule), 2))
        lines.append(")")
        return "\n".join(lines)

    def _metadata(self, node: MetadataNode) -> str:
        pairs = []
        if node.rebalance:
            pairs.append(f":rebalance :{node.rebalance}")
        if node.benchmark:
            pairs.append(f':benchmark "{node.benchmark}"')
        if node.timeframe:
            pairs.append(f":timeframe :{node.timeframe}")
        if node.symbols:
            symbols = " ".join(f'"{s}"' for s in node.symbols)
            pairs.append(f":symbols [{symbols}]")
        if node.description:
            pairs.append(f':description "{node.description}"')

        if not pairs:
            return ""
        return "  {" + "\n   ".join(pairs) + "}"

    def _allocation(self, node: AllocationNode) -> str:
        if isinstance(node, AssetNode):
            return self._asset(node)
        if isinstance(node, WeightNode):
            return self._weight(node)
        if isinstance(node, ConditionalNode):
            return self._conditional(node)
        if isinstance(node, FilterNode):
            return self._filter(node)
        if isinstance(node, UniverseNode):
            return f'(universe "{node.name}")'
        return str(node)

    def _asset(self, node: AssetNode) -> str:
        opts = ""
        if node.weight is not None:
            opts += f" :weight {node.weight}"
        if node.max_weight is not None:
            opts += f" :max-weight {node.max_weight}"
        return f'(asset "{node.symbol}"{opts})'

    def _weight(self, node: WeightNode) -> str:
        method = f"weight-{node.method.replace('_', '-')}"
        children = "\n     ".join(self._allocation(c) for c in node.children)
        return f"({method}\n    [{children}])"

    def _conditional(self, node: ConditionalNode) -> str:
        cond = self._condition(node.condition)
        then_branch = self._allocation(node.then_branch)

        if node.else_branch is None:
            return f"(if {cond}\n    {then_branch})"

        else_branch = self._allocation(node.else_branch)
        return f"(if {cond}\n    {then_branch}\n    {else_branch})"

    def _filter(self, node: FilterNode) -> str:
        source = self._allocation(node.source)
        return f"(filter-{node.type} {node.count} :by {node.by}\n    {source})"

    def _condition(self, node: ConditionNode) -> str:
        if isinstance(node, ComparisonNode):
            left = self._expr(node.left)
            right = self._expr(node.right)
            return f"({node.operator} {left} {right})"
        if isinstance(node, CrossoverNode):
            fast = self._expr(node.fast)
            slow = self._expr(node.slow)
            return f"(crosses-{node.direction} {fast} {slow})"
        if isinstance(node, LogicalNode):
            if node.type == "not":
                return f"(not {self._condition(node.conditions[0])})"
            conds = " ".join(self._condition(c) for c in node.conditions)
            return f"({node.type} {conds})"
        return str(node)

    def _expr(self, node) -> str:
        if isinstance(node, IndicatorNode):
            args = " ".join(str(a) for a in node.args)
            symbol = f' "{node.symbol}"' if node.symbol else ""
            return f"({node.name}{symbol} {args})" if args else f"({node.name}{symbol})"
        if isinstance(node, ExprNode):
            if node.type == "arithmetic":
                return f"({node.operator} {self._expr(node.left)} {self._expr(node.right)})"
            if node.type == "negate":
                return f"(- {self._expr(node.operand)})"
        if isinstance(node, (int, float)):
            return str(node)
        if isinstance(node, str):
            return f'"{node}"' if not node.startswith("$") else node
        return str(node)

    def _rule(self, node: RuleNode) -> str:
        cond = self._condition(node.condition)
        actions = "\n      ".join(self._action(a) for a in node.actions)
        return f"({node.type}\n    (when {cond}\n      {actions}))"

    def _action(self, node: ActionNode) -> str:
        parts = [f"({node.type}"]
        if node.symbol:
            parts.append(node.symbol)
        if node.size_value is not None:
            if node.size_type == "percent_portfolio":
                parts.append(f":size {int(node.size_value * 100)}%")
            else:
                parts.append(f":size {node.size_value}")
        if node.stop_loss is not None:
            parts.append(f":stop-loss {int(node.stop_loss * 100)}%")
        if node.take_profit is not None:
            parts.append(f":take-profit {int(node.take_profit * 100)}%")
        return " ".join(parts) + ")"

    def _indent(self, text: str, spaces: int) -> str:
        indent = " " * spaces
        return "\n".join(indent + line for line in text.split("\n"))


class InfixSerializer:
    """Serialize AST back to Infix DSL format."""

    def serialize(self, node: Union[SymphonyNode, StrategyNode]) -> str:
        if isinstance(node, SymphonyNode):
            return self._symphony(node)
        return self._strategy(node)

    def _symphony(self, node: SymphonyNode) -> str:
        lines = [f'symphony "{node.name}" {{']
        lines.extend(self._metadata_lines(node.metadata))
        lines.append("")
        lines.append(self._indent(self._allocation(node.allocation), 2))
        lines.append("}")
        return "\n".join(lines)

    def _strategy(self, node: StrategyNode) -> str:
        lines = [f'strategy "{node.name}" {{']
        lines.extend(self._metadata_lines(node.metadata))

        for rule in node.rules:
            lines.append("")
            lines.append(self._indent(self._rule(rule), 2))

        lines.append("}")
        return "\n".join(lines)

    def _metadata_lines(self, node: MetadataNode) -> list:
        lines = []
        if node.rebalance:
            lines.append(f"  rebalance: {node.rebalance}")
        if node.benchmark:
            lines.append(f"  benchmark: {node.benchmark}")
        if node.timeframe:
            lines.append(f"  timeframe: {node.timeframe}")
        if node.symbols:
            symbols = ", ".join(node.symbols)
            lines.append(f"  symbols: [{symbols}]")
        if node.description:
            lines.append(f'  description: "{node.description}"')
        return lines

    def _allocation(self, node: AllocationNode) -> str:
        if isinstance(node, AssetNode):
            return self._asset(node)
        if isinstance(node, WeightNode):
            return self._weight(node)
        if isinstance(node, ConditionalNode):
            return self._conditional(node)
        if isinstance(node, FilterNode):
            return self._filter(node)
        if isinstance(node, UniverseNode):
            return node.name
        return str(node)

    def _asset(self, node: AssetNode) -> str:
        if node.weight is not None:
            return f"{node.symbol} @ {int(node.weight * 100)}%"
        return node.symbol

    def _weight(self, node: WeightNode) -> str:
        method = node.method

        if all(isinstance(c, AssetNode) for c in node.children):
            assets = ", ".join(self._asset(c) for c in node.children)
            return f"allocate {method} [{assets}]"

        if len(node.children) == 1 and isinstance(node.children[0], FilterNode):
            filter_str = self._filter(node.children[0])
            return f"allocate {method} ({filter_str})"

        children = ", ".join(self._allocation(c) for c in node.children)
        return f"allocate {method} [{children}]"

    def _conditional(self, node: ConditionalNode) -> str:
        cond = self._condition(node.condition)
        then_branch = self._allocation(node.then_branch)

        lines = [f"if {cond} {{"]
        lines.append(self._indent(then_branch, 2))
        lines.append("}")

        if node.else_branch:
            if isinstance(node.else_branch, ConditionalNode):
                else_str = self._conditional(node.else_branch)
                lines[-1] = "} else " + else_str.split("\n", 1)[0]
                lines.extend(else_str.split("\n")[1:])
            else:
                else_branch = self._allocation(node.else_branch)
                lines[-1] = "} else {"
                lines.append(self._indent(else_branch, 2))
                lines.append("}")

        return "\n".join(lines)

    def _filter(self, node: FilterNode) -> str:
        source = node.source.name if isinstance(node.source, UniverseNode) else str(node.source)
        return f"{node.type} {node.count} from {source} by {node.by}"

    def _condition(self, node: ConditionNode) -> str:
        if isinstance(node, ComparisonNode):
            left = self._expr(node.left)
            right = self._expr(node.right)
            return f"{left} {node.operator} {right}"
        if isinstance(node, CrossoverNode):
            fast = self._expr(node.fast)
            slow = self._expr(node.slow)
            return f"{fast} crosses {node.direction} {slow}"
        if isinstance(node, LogicalNode):
            if node.type == "not":
                return f"NOT {self._condition(node.conditions[0])}"
            op = f" {node.type.upper()} "
            return op.join(self._condition(c) for c in node.conditions)
        return str(node)

    def _expr(self, node) -> str:
        if isinstance(node, IndicatorNode):
            args = ", ".join(str(a) for a in node.args)
            base = f"{node.name}({args})" if args else f"{node.name}()"
            if node.accessor:
                base += f".{node.accessor}"
            return base
        if isinstance(node, ExprNode):
            if node.type == "arithmetic":
                return f"{self._expr(node.left)} {node.operator} {self._expr(node.right)}"
            if node.type == "negate":
                return f"-{self._expr(node.operand)}"
        if isinstance(node, (int, float)):
            return str(node)
        return str(node)

    def _rule(self, node: RuleNode) -> str:
        cond = self._condition(node.condition)
        lines = [f"{node.type} when {cond} {{"]

        for action in node.actions:
            lines.append(self._indent(self._action(action), 2))

        lines.append("}")
        return "\n".join(lines)

    def _action(self, node: ActionNode) -> str:
        if node.type == "buy" or node.type == "sell":
            if node.size_type == "percent_portfolio":
                return f"{node.type} {int(node.size_value * 100)}% of portfolio"
            if node.size_type == "fixed_shares":
                return f"{node.type} {int(node.size_value)} shares"
            if node.size_type == "fixed_dollars":
                return f"{node.type} ${node.size_value}"
        if node.type == "close":
            return "close position"
        if node.type == "set":
            value = node.value
            if isinstance(value, float) and abs(value) < 1:
                value = f"{int(value * 100)}%"
            return f"set {node.param} {value}"
        return node.type

    def _indent(self, text: str, spaces: int) -> str:
        indent = " " * spaces
        return "\n".join(indent + line for line in text.split("\n"))


class VisualBlockSerializer:
    """Serialize AST to/from visual builder JSON format."""

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
        """Convert visual block format back to AST."""
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

    def _node_to_blocks(self, node) -> list:
        if isinstance(node, list):
            return [self._node_to_block(n) for n in node]
        return [self._node_to_block(node)]

    def _node_to_block(self, node) -> dict:
        if isinstance(node, AssetNode):
            return {
                "id": self._generate_id(),
                "type": "asset",
                "symbol": node.symbol,
                "weight": node.weight
            }
        if isinstance(node, WeightNode):
            return {
                "id": self._generate_id(),
                "type": "weight",
                "method": node.method,
                "children": self._node_to_blocks(node.children)
            }
        if isinstance(node, ConditionalNode):
            result = {
                "id": self._generate_id(),
                "type": "conditional",
                "condition": self._condition_to_block(node.condition),
                "then": self._node_to_blocks(node.then_branch)
            }
            if node.else_branch:
                result["else"] = self._node_to_blocks(node.else_branch)
            return result
        if isinstance(node, RuleNode):
            return {
                "id": self._generate_id(),
                "type": "rule",
                "rule_type": node.type,
                "condition": self._condition_to_block(node.condition),
                "actions": [self._action_to_block(a) for a in node.actions]
            }
        return {"id": self._generate_id(), "type": "unknown", "data": str(node)}

    def _condition_to_block(self, node: ConditionNode) -> dict:
        if isinstance(node, ComparisonNode):
            return {
                "type": "comparison",
                "operator": node.operator,
                "left": self._expr_to_block(node.left),
                "right": self._expr_to_block(node.right)
            }
        if isinstance(node, LogicalNode):
            return {
                "type": "logical",
                "op": node.type,
                "conditions": [self._condition_to_block(c) for c in node.conditions]
            }
        if isinstance(node, CrossoverNode):
            return {
                "type": "crossover",
                "direction": node.direction,
                "fast": self._expr_to_block(node.fast),
                "slow": self._expr_to_block(node.slow)
            }
        return {"type": "unknown"}

    def _expr_to_block(self, node) -> dict:
        if isinstance(node, IndicatorNode):
            return {
                "type": "indicator",
                "name": node.name,
                "args": node.args,
                "accessor": node.accessor
            }
        if isinstance(node, (int, float)):
            return {"type": "literal", "value": node}
        if isinstance(node, str):
            return {"type": "symbol", "value": node}
        return {"type": "unknown", "value": str(node)}

    def _action_to_block(self, node: ActionNode) -> dict:
        return {
            "type": "action",
            "action_type": node.type,
            "size_type": node.size_type,
            "size_value": node.size_value,
            "stop_loss": node.stop_loss,
            "take_profit": node.take_profit
        }

    def _blocks_to_allocation(self, blocks: list) -> AllocationNode:
        # Implementation for reverse conversion
        pass

    def _blocks_to_rules(self, blocks: list) -> list:
        # Implementation for reverse conversion
        pass

    def _generate_id(self) -> str:
        import uuid
        return str(uuid.uuid4())[:8]
```

---

## Part 5: AI Generation Pipeline

````python
# libs/dsl/llamatrade_dsl/ai/generator.py

from typing import Optional, Literal
import json

from anthropic import Anthropic

DSL_FORMAT = Literal["sexpr", "infix"]

SYSTEM_PROMPT = """You are an expert trading strategy designer for LlamaTrade.
Convert natural language descriptions into trading strategies using the specified DSL format.

## S-Expression Format
- Use (defsymphony "name" {...} allocation) for portfolio allocations
- Use (defstrategy "name" {...} rules) for active trading
- Conditions: (and ...), (or ...), (> x y), (< x y), (crosses-above x y)
- Indicators: (rsi symbol period), (sma symbol period), (macd symbol fast slow signal)
- Weights: (weight-equal [...]), (weight-inverse-volatility [...])

## Infix Format
- Use `symphony "name" { ... }` for portfolios
- Use `strategy "name" { ... }` for active trading
- Conditions: AND, OR, >, <, crosses above/below
- Indicators: RSI(period), SMA(period), MACD(12, 26, 9)
- Example: `entry when RSI(14) < 30 AND Volume > SMA_Volume(20) { buy 5% of portfolio }`

Always output ONLY the DSL code, no explanations."""


INFIX_EXAMPLES = '''
Example 1 - Simple portfolio:
User: "Create a tech-focused portfolio with equal weights in AAPL, MSFT, GOOGL"
Output:
symphony "Tech Focus" {
  rebalance: monthly
  allocate equal_weight [AAPL, MSFT, GOOGL]
}

Example 2 - Conditional rotation:
User: "Buy bonds when RSI of SPY is overbought, otherwise stay in stocks"
Output:
symphony "Risk Rotation" {
  rebalance: daily

  if RSI(SPY, 14) > 70 {
    allocate equal_weight [TLT, IEF]
  } else {
    allocate equal_weight [SPY, QQQ]
  }
}

Example 3 - Mean reversion strategy:
User: "Buy when RSI drops below 30 with high volume, sell when RSI goes above 70"
Output:
strategy "RSI Mean Reversion" {
  timeframe: 1h
  symbols: [SPY]

  entry when RSI(14) < 30 AND Volume > SMA_Volume(20) * 1.5 {
    buy 5% of portfolio
    set stop_loss -2%
    set take_profit 4%
  }

  exit when RSI(14) > 70 {
    close position
  }
}
'''

SEXPR_EXAMPLES = '''
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
    """Generate strategies from natural language using Claude."""

    def __init__(self, api_key: Optional[str] = None):
        self.client = Anthropic(api_key=api_key)

    def generate(
        self,
        description: str,
        format: DSL_FORMAT = "infix",
        model: str = "claude-sonnet-4-20250514"
    ) -> str:
        """Generate DSL code from natural language description."""
        examples = INFIX_EXAMPLES if format == "infix" else SEXPR_EXAMPLES

        response = self.client.messages.create(
            model=model,
            max_tokens=2000,
            system=SYSTEM_PROMPT + "\n\n" + examples,
            messages=[
                {
                    "role": "user",
                    "content": f"Format: {format}\n\nDescription: {description}"
                }
            ]
        )

        return response.content[0].text.strip()

    def generate_with_validation(
        self,
        description: str,
        format: DSL_FORMAT = "infix"
    ) -> tuple[str, bool, Optional[str]]:
        """Generate and validate DSL code."""
        from ..infix.parser import InfixParser
        from ..sexpr.parser import SExprParser

        code = self.generate(description, format)

        parser = InfixParser() if format == "infix" else SExprParser()

        try:
            ast = parser.parse(code)
            return code, True, None
        except Exception as e:
            return code, False, str(e)

    def refine(
        self,
        code: str,
        feedback: str,
        format: DSL_FORMAT = "infix"
    ) -> str:
        """Refine existing DSL code based on feedback."""
        response = self.client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=2000,
            system=SYSTEM_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": f"Current code ({format} format):\n```\n{code}\n```\n\nFeedback: {feedback}\n\nPlease update the code."
                }
            ]
        )

        return response.content[0].text.strip()


class AIStrategyExplainer:
    """Explain strategies in natural language."""

    def __init__(self, api_key: Optional[str] = None):
        self.client = Anthropic(api_key=api_key)

    def explain(self, code: str, format: DSL_FORMAT = "infix") -> str:
        """Explain what a strategy does in plain English."""
        response = self.client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1000,
            messages=[
                {
                    "role": "user",
                    "content": f"Explain this trading strategy in simple terms:\n\n```{format}\n{code}\n```"
                }
            ]
        )

        return response.content[0].text
````

---

## Part 6: Execution Engine Integration

```python
# libs/dsl/llamatrade_dsl/execution/compiler.py

from typing import Dict, Any, List
from dataclasses import dataclass

from ..ast import (
    SymphonyNode, StrategyNode, ConditionalNode, WeightNode,
    FilterNode, AssetNode, UniverseNode, RuleNode, ConditionNode,
    ComparisonNode, LogicalNode, CrossoverNode, IndicatorNode
)


@dataclass
class CompiledSymphony:
    """Compiled symphony ready for execution."""
    name: str
    rebalance_frequency: str
    benchmark: Optional[str]
    evaluate: callable  # (market_data) -> Dict[str, float] (allocations)


@dataclass
class CompiledStrategy:
    """Compiled strategy ready for execution."""
    name: str
    timeframe: str
    symbols: List[str]
    on_bar: callable  # (symbol, bar, portfolio) -> List[Signal]


class StrategyCompiler:
    """Compile AST to executable functions."""

    def __init__(self, indicator_registry, universe_registry):
        self.indicators = indicator_registry
        self.universes = universe_registry

    def compile_symphony(self, node: SymphonyNode) -> CompiledSymphony:
        """Compile symphony AST to executable."""
        allocation_fn = self._compile_allocation(node.allocation)

        return CompiledSymphony(
            name=node.name,
            rebalance_frequency=node.metadata.rebalance or "monthly",
            benchmark=node.metadata.benchmark,
            evaluate=allocation_fn
        )

    def compile_strategy(self, node: StrategyNode) -> CompiledStrategy:
        """Compile strategy AST to executable."""
        entry_rules = [r for r in node.rules if r.type == "entry"]
        exit_rules = [r for r in node.rules if r.type == "exit"]

        compiled_entries = [self._compile_rule(r) for r in entry_rules]
        compiled_exits = [self._compile_rule(r) for r in exit_rules]

        def on_bar(symbol: str, bar: dict, portfolio: dict) -> list:
            signals = []
            context = {"symbol": symbol, "bar": bar, "portfolio": portfolio}

            # Check exit rules first
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
            def allocate(ctx):
                return {node.symbol: node.weight or 1.0}
            return allocate

        if isinstance(node, WeightNode):
            child_fns = [self._compile_allocation(c) for c in node.children]
            method = node.method

            def allocate(ctx):
                # Collect all assets from children
                assets = {}
                for fn in child_fns:
                    assets.update(fn(ctx))

                # Apply weighting method
                if method == "equal":
                    weight = 1.0 / len(assets)
                    return {s: weight for s in assets}
                elif method == "fixed":
                    return assets  # Use weights as specified
                elif method == "inverse_volatility":
                    return self._inverse_vol_weights(assets, ctx)
                elif method == "risk_parity":
                    return self._risk_parity_weights(assets, ctx)
                elif method == "momentum":
                    return self._momentum_weights(assets, ctx)
                return assets

            return allocate

        if isinstance(node, ConditionalNode):
            cond_fn = self._compile_condition(node.condition)
            then_fn = self._compile_allocation(node.then_branch)
            else_fn = self._compile_allocation(node.else_branch) if node.else_branch else lambda ctx: {}

            def allocate(ctx):
                if cond_fn(ctx):
                    return then_fn(ctx)
                return else_fn(ctx)

            return allocate

        if isinstance(node, FilterNode):
            source_fn = self._compile_allocation(node.source)

            def allocate(ctx):
                assets = source_fn(ctx)
                # Sort by metric and take top/bottom N
                sorted_assets = self._sort_by_metric(assets, node.by, ctx)
                if node.type == "top":
                    selected = sorted_assets[:node.count]
                else:
                    selected = sorted_assets[-node.count:]
                return {s: 1.0 for s in selected}

            return allocate

        if isinstance(node, UniverseNode):
            def allocate(ctx):
                symbols = self.universes.get(node.name, [])
                return {s: 1.0 for s in symbols}
            return allocate

        raise ValueError(f"Unknown allocation node type: {type(node)}")

    def _compile_condition(self, node: ConditionNode) -> callable:
        """Compile condition to boolean function."""

        if isinstance(node, ComparisonNode):
            left_fn = self._compile_expr(node.left)
            right_fn = self._compile_expr(node.right)
            op = node.operator

            def check(ctx):
                left = left_fn(ctx)
                right = right_fn(ctx)
                if op == ">":
                    return left > right
                if op == "<":
                    return left < right
                if op == ">=":
                    return left >= right
                if op == "<=":
                    return left <= right
                if op == "==" or op == "=":
                    return left == right
                if op == "!=":
                    return left != right
                return False

            return check

        if isinstance(node, LogicalNode):
            child_fns = [self._compile_condition(c) for c in node.conditions]

            if node.type == "and":
                return lambda ctx: all(fn(ctx) for fn in child_fns)
            if node.type == "or":
                return lambda ctx: any(fn(ctx) for fn in child_fns)
            if node.type == "not":
                return lambda ctx: not child_fns[0](ctx)

        if isinstance(node, CrossoverNode):
            fast_fn = self._compile_expr(node.fast)
            slow_fn = self._compile_expr(node.slow)
            direction = node.direction

            def check(ctx):
                # Need historical data for crossover detection
                fast_curr = fast_fn(ctx)
                slow_curr = slow_fn(ctx)
                fast_prev = fast_fn({**ctx, "offset": 1})
                slow_prev = slow_fn({**ctx, "offset": 1})

                if direction == "above":
                    return fast_prev <= slow_prev and fast_curr > slow_curr
                else:
                    return fast_prev >= slow_prev and fast_curr < slow_curr

            return check

        raise ValueError(f"Unknown condition type: {type(node)}")

    def _compile_expr(self, node) -> callable:
        """Compile expression to value function."""

        if isinstance(node, IndicatorNode):
            name = node.name.lower()
            args = node.args
            accessor = node.accessor

            def evaluate(ctx):
                symbol = ctx.get("symbol")
                indicator = self.indicators.calculate(name, symbol, *args)
                if accessor and isinstance(indicator, dict):
                    return indicator[accessor]
                return indicator

            return evaluate

        if isinstance(node, (int, float)):
            return lambda ctx: node

        if isinstance(node, str):
            if node.startswith("$"):
                var_name = node[1:]
                return lambda ctx: ctx.get(var_name)
            return lambda ctx: node

        raise ValueError(f"Unknown expression type: {type(node)}")

    def _compile_rule(self, node: RuleNode) -> tuple:
        """Compile rule to (condition_fn, actions_fn) tuple."""
        cond_fn = self._compile_condition(node.condition)
        actions = node.actions

        def get_actions(ctx):
            return [self._execute_action(a, ctx) for a in actions]

        return (cond_fn, get_actions)

    def _execute_action(self, action, ctx) -> dict:
        """Convert action node to signal dict."""
        return {
            "type": action.type,
            "symbol": ctx.get("symbol"),
            "size_type": action.size_type,
            "size_value": action.size_value,
            "stop_loss": action.stop_loss,
            "take_profit": action.take_profit
        }

    def _inverse_vol_weights(self, assets: dict, ctx) -> dict:
        """Calculate inverse volatility weights."""
        # Implementation using historical volatility
        pass

    def _risk_parity_weights(self, assets: dict, ctx) -> dict:
        """Calculate risk parity weights."""
        pass

    def _momentum_weights(self, assets: dict, ctx) -> dict:
        """Calculate momentum-based weights."""
        pass

    def _sort_by_metric(self, assets: dict, metric: str, ctx) -> list:
        """Sort assets by metric value."""
        pass
```

---

## Part 7: Visual Builder Integration

### 7.1 Frontend Components (React)

```typescript
// frontend/src/components/StrategyBuilder/types.ts

export interface BlockNode {
  id: string;
  type: BlockType;
  data: Record<string, any>;
  children?: BlockNode[];
  position?: { x: number; y: number };
}

export type BlockType =
  | "symphony"
  | "strategy"
  | "weight"
  | "asset"
  | "conditional"
  | "filter"
  | "rule"
  | "condition"
  | "indicator"
  | "action";

export interface IndicatorConfig {
  name: string;
  displayName: string;
  category: "trend" | "momentum" | "volatility" | "volume";
  params: ParamConfig[];
  outputs: string[];
}

export interface ParamConfig {
  name: string;
  type: "number" | "period" | "percent";
  default: number;
  min?: number;
  max?: number;
}
```

```typescript
// frontend/src/components/StrategyBuilder/BlockEditor.tsx

import React, { useState, useCallback } from 'react';
import { DndProvider, useDrag, useDrop } from 'react-dnd';
import { HTML5Backend } from 'react-dnd-html5-backend';
import { BlockNode, BlockType } from './types';
import { serializeToInfix, serializeToSExpr } from './serializers';

interface BlockEditorProps {
  initialBlocks?: BlockNode;
  onChange?: (blocks: BlockNode) => void;
  onCodeChange?: (code: string, format: 'infix' | 'sexpr') => void;
}

export const BlockEditor: React.FC<BlockEditorProps> = ({
  initialBlocks,
  onChange,
  onCodeChange
}) => {
  const [blocks, setBlocks] = useState<BlockNode>(initialBlocks || createEmptySymphony());
  const [selectedFormat, setSelectedFormat] = useState<'infix' | 'sexpr'>('infix');

  const handleBlockUpdate = useCallback((updatedBlocks: BlockNode) => {
    setBlocks(updatedBlocks);
    onChange?.(updatedBlocks);

    // Generate code from blocks
    const code = selectedFormat === 'infix'
      ? serializeToInfix(updatedBlocks)
      : serializeToSExpr(updatedBlocks);
    onCodeChange?.(code, selectedFormat);
  }, [onChange, onCodeChange, selectedFormat]);

  return (
    <DndProvider backend={HTML5Backend}>
      <div className="block-editor">
        <Toolbox />
        <Canvas blocks={blocks} onUpdate={handleBlockUpdate} />
        <CodePreview
          code={selectedFormat === 'infix' ? serializeToInfix(blocks) : serializeToSExpr(blocks)}
          format={selectedFormat}
          onFormatChange={setSelectedFormat}
        />
      </div>
    </DndProvider>
  );
};

const Toolbox: React.FC = () => {
  const blockTypes: { type: BlockType; label: string; icon: string }[] = [
    { type: 'asset', label: 'Asset', icon: '📊' },
    { type: 'weight', label: 'Weight', icon: '⚖️' },
    { type: 'conditional', label: 'If/Else', icon: '🔀' },
    { type: 'filter', label: 'Filter', icon: '🔍' },
    { type: 'rule', label: 'Rule', icon: '📋' },
    { type: 'indicator', label: 'Indicator', icon: '📈' },
    { type: 'action', label: 'Action', icon: '⚡' },
  ];

  return (
    <div className="toolbox">
      {blockTypes.map(({ type, label, icon }) => (
        <DraggableBlock key={type} type={type} label={label} icon={icon} />
      ))}
    </div>
  );
};

const DraggableBlock: React.FC<{ type: BlockType; label: string; icon: string }> = ({
  type, label, icon
}) => {
  const [{ isDragging }, drag] = useDrag({
    type: 'BLOCK',
    item: { type },
    collect: (monitor) => ({
      isDragging: monitor.isDragging(),
    }),
  });

  return (
    <div
      ref={drag}
      className={`toolbox-block ${isDragging ? 'dragging' : ''}`}
    >
      <span className="icon">{icon}</span>
      <span className="label">{label}</span>
    </div>
  );
};
```

```typescript
// frontend/src/components/StrategyBuilder/serializers.ts

import { BlockNode } from "./types";

export function serializeToInfix(blocks: BlockNode): string {
  if (blocks.type === "symphony") {
    return serializeSymphony(blocks);
  }
  return serializeStrategy(blocks);
}

function serializeSymphony(node: BlockNode): string {
  const lines: string[] = [`symphony "${node.data.name}" {`];

  if (node.data.rebalance) {
    lines.push(`  rebalance: ${node.data.rebalance}`);
  }
  if (node.data.benchmark) {
    lines.push(`  benchmark: ${node.data.benchmark}`);
  }

  lines.push("");

  if (node.children?.length) {
    lines.push(indent(serializeAllocation(node.children[0]), 2));
  }

  lines.push("}");
  return lines.join("\n");
}

function serializeAllocation(node: BlockNode): string {
  switch (node.type) {
    case "asset":
      return node.data.weight
        ? `${node.data.symbol} @ ${node.data.weight * 100}%`
        : node.data.symbol;

    case "weight":
      const assets = node.children?.map(serializeAllocation).join(", ") || "";
      return `allocate ${node.data.method} [${assets}]`;

    case "conditional":
      const cond = serializeCondition(node.data.condition);
      const thenBranch = node.children?.[0]
        ? serializeAllocation(node.children[0])
        : "";
      const elseBranch = node.children?.[1]
        ? serializeAllocation(node.children[1])
        : "";

      let result = `if ${cond} {\n${indent(thenBranch, 2)}\n}`;
      if (elseBranch) {
        result += ` else {\n${indent(elseBranch, 2)}\n}`;
      }
      return result;

    case "filter":
      return `${node.data.type} ${node.data.count} from ${node.data.universe} by ${node.data.metric}`;

    default:
      return "";
  }
}

function serializeCondition(cond: any): string {
  if (!cond) return "true";

  if (cond.type === "comparison") {
    const left = serializeExpr(cond.left);
    const right = serializeExpr(cond.right);
    return `${left} ${cond.operator} ${right}`;
  }

  if (cond.type === "logical") {
    const conditions = cond.conditions.map(serializeCondition);
    return conditions.join(` ${cond.op.toUpperCase()} `);
  }

  if (cond.type === "crossover") {
    const fast = serializeExpr(cond.fast);
    const slow = serializeExpr(cond.slow);
    return `${fast} crosses ${cond.direction} ${slow}`;
  }

  return String(cond);
}

function serializeExpr(expr: any): string {
  if (typeof expr === "number") return String(expr);
  if (typeof expr === "string") return expr;

  if (expr.type === "indicator") {
    const args = expr.args?.join(", ") || "";
    let result = `${expr.name}(${args})`;
    if (expr.accessor) result += `.${expr.accessor}`;
    return result;
  }

  return String(expr);
}

function indent(text: string, spaces: number): string {
  const pad = " ".repeat(spaces);
  return text
    .split("\n")
    .map((line) => pad + line)
    .join("\n");
}

// S-Expression serializer
export function serializeToSExpr(blocks: BlockNode): string {
  // Similar implementation for S-expression format
  // ...
}
```

### 7.2 API Endpoints

```python
# services/strategy/src/routers/dsl.py

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Literal, Optional, List

from llamatrade_dsl.sexpr.parser import SExprParser
from llamatrade_dsl.infix.parser import InfixParser
from llamatrade_dsl.serializers import SExprSerializer, InfixSerializer, VisualBlockSerializer
from llamatrade_dsl.ai.generator import AIStrategyGenerator

router = APIRouter(prefix="/dsl", tags=["dsl"])


class ParseRequest(BaseModel):
    code: str
    format: Literal["sexpr", "infix"]


class GenerateRequest(BaseModel):
    description: str
    format: Literal["sexpr", "infix"] = "infix"


class ConvertRequest(BaseModel):
    code: str
    from_format: Literal["sexpr", "infix", "blocks"]
    to_format: Literal["sexpr", "infix", "blocks", "json"]


class ValidateResponse(BaseModel):
    valid: bool
    errors: List[str]
    ast_json: Optional[dict]


@router.post("/parse", response_model=ValidateResponse)
async def parse_dsl(request: ParseRequest):
    """Parse DSL code and return AST."""
    parser = SExprParser() if request.format == "sexpr" else InfixParser()

    try:
        ast_nodes = parser.parse(request.code)
        return ValidateResponse(
            valid=True,
            errors=[],
            ast_json=[node.to_dict() for node in ast_nodes]
        )
    except Exception as e:
        return ValidateResponse(
            valid=False,
            errors=[str(e)],
            ast_json=None
        )


@router.post("/generate")
async def generate_from_natural_language(request: GenerateRequest):
    """Generate DSL code from natural language description."""
    generator = AIStrategyGenerator()
    code, valid, error = generator.generate_with_validation(
        request.description,
        request.format
    )

    return {
        "code": code,
        "format": request.format,
        "valid": valid,
        "error": error
    }


@router.post("/convert")
async def convert_format(request: ConvertRequest):
    """Convert between DSL formats."""
    # Parse input
    if request.from_format == "sexpr":
        parser = SExprParser()
        ast_nodes = parser.parse(request.code)
    elif request.from_format == "infix":
        parser = InfixParser()
        ast_nodes = parser.parse(request.code)
    elif request.from_format == "blocks":
        import json
        blocks = json.loads(request.code)
        serializer = VisualBlockSerializer()
        ast_nodes = [serializer.from_blocks(blocks)]
    else:
        raise HTTPException(400, f"Unknown format: {request.from_format}")

    # Serialize to output format
    results = []
    for node in ast_nodes:
        if request.to_format == "sexpr":
            serializer = SExprSerializer()
            results.append(serializer.serialize(node))
        elif request.to_format == "infix":
            serializer = InfixSerializer()
            results.append(serializer.serialize(node))
        elif request.to_format == "blocks":
            serializer = VisualBlockSerializer()
            results.append(serializer.to_blocks(node))
        elif request.to_format == "json":
            results.append(node.to_dict())

    return {
        "output": results[0] if len(results) == 1 else results,
        "format": request.to_format
    }


@router.post("/explain")
async def explain_strategy(request: ParseRequest):
    """Explain a strategy in natural language."""
    from llamatrade_dsl.ai.generator import AIStrategyExplainer

    explainer = AIStrategyExplainer()
    explanation = explainer.explain(request.code, request.format)

    return {"explanation": explanation}
```

---

## Part 8: File Structure

```
libs/
└── dsl/
    ├── pyproject.toml
    └── llamatrade_dsl/
        ├── __init__.py
        ├── ast.py                    # Unified AST definitions
        │
        ├── sexpr/
        │   ├── __init__.py
        │   ├── grammar.lark          # S-expression grammar
        │   └── parser.py             # S-expression parser
        │
        ├── infix/
        │   ├── __init__.py
        │   ├── grammar.lark          # Infix grammar
        │   └── parser.py             # Infix parser
        │
        ├── serializers.py            # AST → text/blocks serialization
        │
        ├── semantic/
        │   ├── __init__.py
        │   ├── validator.py          # AST validation
        │   ├── type_checker.py       # Type checking
        │   └── optimizer.py          # AST optimization
        │
        ├── execution/
        │   ├── __init__.py
        │   ├── compiler.py           # AST → executable
        │   └── runtime.py            # Execution context
        │
        ├── ai/
        │   ├── __init__.py
        │   ├── generator.py          # NL → DSL generation
        │   └── explainer.py          # DSL → NL explanation
        │
        └── tests/
            ├── test_sexpr_parser.py
            ├── test_infix_parser.py
            ├── test_serializers.py
            ├── test_compiler.py
            └── fixtures/
                ├── symphonies/
                └── strategies/

frontend/
└── src/
    └── components/
        └── StrategyBuilder/
            ├── index.tsx
            ├── BlockEditor.tsx
            ├── Canvas.tsx
            ├── Toolbox.tsx
            ├── blocks/
            │   ├── AssetBlock.tsx
            │   ├── WeightBlock.tsx
            │   ├── ConditionalBlock.tsx
            │   ├── IndicatorBlock.tsx
            │   └── ActionBlock.tsx
            ├── serializers.ts
            └── types.ts
```

---

## Summary

This implementation provides:

1. **Two DSL Syntaxes** - S-Expression (functional, composable) and Infix (readable, familiar)
2. **Unified AST** - Both parse to the same structure, enabling shared tooling
3. **Bidirectional Serialization** - Convert freely between formats
4. **Visual Builder** - Drag-and-drop that generates valid DSL code
5. **AI Generation** - Natural language → DSL with validation
6. **Execution Engine** - Compile AST to executable trading logic

The layered architecture means users can:

- Use visual blocks for simple strategies
- Write Infix for medium complexity
- Use S-expressions for maximum power
- Describe in natural language for AI generation
- Switch between formats at any time
