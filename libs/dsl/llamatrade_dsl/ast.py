"""AST node types for the allocation-based strategy DSL.

This module defines the data structures for representing allocation strategies
that match the strategy builder UI's block-based structure.

Block Types:
- Strategy: Root container with rebalance settings
- Group: Organizational grouping of allocations
- Weight: Allocation method (specified, equal, momentum, etc.)
- Asset: Single ticker symbol
- If: Conditional allocation
- Filter: Asset selection/filtering

Condition Types:
- Comparison: >, <, >=, <=, =, !=
- Crossover: crosses-above, crosses-below
- LogicalOp: and, or, not

Value Types:
- Price: Current or historical price
- Indicator: Technical indicator value
- Metric: Derived metric (drawdown, return)
- NumericLiteral: Constant number
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING
from typing import Literal as TypingLiteral

if TYPE_CHECKING:
    pass  # Block is defined later in this file


def _empty_block_list() -> list[Block]:
    """Factory for empty block list."""
    return []


# =============================================================================
# Source Location (for error reporting)
# =============================================================================


@dataclass(frozen=True, slots=True)
class SourceLocation:
    """Source code location for error reporting.

    Attributes:
        line: 1-indexed line number
        column: 1-indexed column number
        start: 0-indexed character offset from start of source
        end: 0-indexed character offset of end position (exclusive)
    """

    line: int
    column: int
    start: int
    end: int

    def __repr__(self) -> str:
        return f"line {self.line}, col {self.column}"


# =============================================================================
# Type Aliases
# =============================================================================

type RebalanceFrequency = TypingLiteral["daily", "weekly", "monthly", "quarterly", "annually"]

type WeightMethod = TypingLiteral[
    "specified",
    "equal",
    "momentum",
    "inverse-volatility",
    "min-variance",
    "market-cap",
    "risk-parity",
]

type FilterCriteria = TypingLiteral["momentum", "volatility", "volume"]

type SelectDirection = TypingLiteral["top", "bottom"]

type ComparisonOperator = TypingLiteral[">", "<", ">=", "<=", "=", "!="]

type LogicalOperator = TypingLiteral["and", "or", "not"]

type CrossoverDirection = TypingLiteral["above", "below"]

type PriceField = TypingLiteral["close", "open", "high", "low", "volume"]

# =============================================================================
# Value Types (used in conditions)
# =============================================================================


@dataclass(frozen=True, slots=True)
class NumericLiteral:
    """Constant numeric value."""

    value: float
    location: SourceLocation | None = None

    def __repr__(self) -> str:
        if self.value == int(self.value):
            return str(int(self.value))
        return str(self.value)


@dataclass(frozen=True, slots=True)
class Price:
    """Reference to an asset's price.

    Examples:
        (price SPY)           -> Price(symbol="SPY", field="close")
        (price AAPL :high)    -> Price(symbol="AAPL", field="high")
    """

    symbol: str
    field: PriceField = "close"
    location: SourceLocation | None = None

    def __repr__(self) -> str:
        if self.field == "close":
            return f"(price {self.symbol})"
        return f"(price {self.symbol} :{self.field})"


@dataclass(frozen=True, slots=True)
class Indicator:
    """Technical indicator value.

    Examples:
        (sma SPY 50)              -> Indicator(name="sma", symbol="SPY", params=(50,))
        (macd AAPL 12 26 9)       -> Indicator(name="macd", symbol="AAPL", params=(12, 26, 9))
        (macd AAPL 12 26 9 :signal) -> Indicator(..., output="signal")
        (bbands SPY 20 2 :upper)  -> Indicator(..., output="upper")
    """

    name: str
    symbol: str
    params: tuple[int | float, ...] = ()
    output: str | None = None
    location: SourceLocation | None = None

    def __repr__(self) -> str:
        parts = [self.name, self.symbol]
        parts.extend(str(p) for p in self.params)
        if self.output:
            parts.append(f":{self.output}")
        return f"({' '.join(parts)})"


@dataclass(frozen=True, slots=True)
class Metric:
    """Derived metric value.

    Examples:
        (drawdown SPY)     -> Metric(name="drawdown", symbol="SPY")
        (return SPY 30)    -> Metric(name="return", symbol="SPY", period=30)
    """

    name: TypingLiteral["drawdown", "return", "volatility"]
    symbol: str
    period: int | None = None
    location: SourceLocation | None = None

    def __repr__(self) -> str:
        if self.period:
            return f"({self.name} {self.symbol} {self.period})"
        return f"({self.name} {self.symbol})"


# Union type for all value expressions
type Value = NumericLiteral | Price | Indicator | Metric


# =============================================================================
# Condition Types (used in if blocks)
# =============================================================================


@dataclass(frozen=True, slots=True)
class Comparison:
    """Comparison between two values.

    Examples:
        (> (sma SPY 50) (sma SPY 200))
        (< (rsi QQQ 14) 30)
        (>= (price AAPL) 150)
    """

    operator: ComparisonOperator
    left: Value
    right: Value
    location: SourceLocation | None = None

    def __repr__(self) -> str:
        return f"({self.operator} {self.left!r} {self.right!r})"


@dataclass(frozen=True, slots=True)
class Crossover:
    """Crossover detection between two values.

    Examples:
        (crosses-above (sma SPY 50) (sma SPY 200))
        (crosses-below (ema QQQ 12) (ema QQQ 26))
    """

    direction: CrossoverDirection
    fast: Value
    slow: Value
    location: SourceLocation | None = None

    def __repr__(self) -> str:
        op = f"crosses-{self.direction}"
        return f"({op} {self.fast!r} {self.slow!r})"


@dataclass(frozen=True, slots=True)
class LogicalOp:
    """Logical combination of conditions.

    Examples:
        (and (> (sma SPY 50) (sma SPY 200)) (< (rsi SPY 14) 70))
        (or (> (rsi QQQ 14) 70) (< (rsi QQQ 14) 30))
        (not (> (price VIX) 30))
    """

    operator: LogicalOperator
    operands: tuple[Condition, ...]
    location: SourceLocation | None = None

    def __repr__(self) -> str:
        ops = " ".join(repr(op) for op in self.operands)
        return f"({self.operator} {ops})"


# Union type for all condition expressions
type Condition = Comparison | Crossover | LogicalOp


# =============================================================================
# Block Types (strategy structure)
# =============================================================================


@dataclass(frozen=True, slots=True)
class Asset:
    """Single tradeable asset.

    Examples:
        (asset VTI)              -> Asset(symbol="VTI")
        (asset AAPL :weight 25)  -> Asset(symbol="AAPL", weight=25.0)
    """

    symbol: str
    weight: float | None = None
    location: SourceLocation | None = None

    def __repr__(self) -> str:
        if self.weight is not None:
            return f"(asset {self.symbol} :weight {self.weight})"
        return f"(asset {self.symbol})"


@dataclass(slots=True)
class Weight:
    """Allocation weight block.

    Defines how child assets/groups should be weighted.

    Examples:
        (weight :method specified
          (asset VTI :weight 60)
          (asset BND :weight 40))

        (weight :method momentum :lookback 90 :top 3
          (asset XLK)
          (asset XLF)
          (asset XLE))
    """

    method: WeightMethod
    children: list[Block] = field(default_factory=_empty_block_list)
    lookback: int | None = None
    top: int | None = None
    location: SourceLocation | None = None

    def __repr__(self) -> str:
        parts = [f":method {self.method}"]
        if self.lookback:
            parts.append(f":lookback {self.lookback}")
        if self.top:
            parts.append(f":top {self.top}")
        children_str = " ".join(repr(c) for c in self.children)
        return f"(weight {' '.join(parts)} {children_str})"


@dataclass(slots=True)
class Group:
    """Organizational grouping of allocations.

    Groups don't affect allocation math - they're for organization.

    Examples:
        (group "US Equities"
          (weight :method equal
            (asset VTI)
            (asset VXF)))
    """

    name: str
    children: list[Block] = field(default_factory=_empty_block_list)
    location: SourceLocation | None = None

    def __repr__(self) -> str:
        children_str = " ".join(repr(c) for c in self.children)
        return f'(group "{self.name}" {children_str})'


@dataclass(slots=True)
class If:
    """Conditional allocation block.

    Examples:
        (if (> (sma SPY 50) (sma SPY 200))
          (weight :method equal (asset VTI) (asset VXUS))
          (else
            (weight :method equal (asset BND) (asset SHY))))
    """

    condition: Condition
    then_block: Block
    else_block: Block | None = None
    location: SourceLocation | None = None

    def __repr__(self) -> str:
        result = f"(if {self.condition!r} {self.then_block!r}"
        if self.else_block:
            result += f" (else {self.else_block!r})"
        result += ")"
        return result


@dataclass(slots=True)
class Filter:
    """Asset filter/selector block.

    Filters assets by criteria before applying weights.

    Examples:
        (filter :by momentum :select (top 3) :lookback 90
          (weight :method equal
            (asset XLK)
            (asset XLF)
            (asset XLE)
            (asset XLV)))
    """

    by: FilterCriteria
    select_direction: SelectDirection
    select_count: int
    children: list[Block] = field(default_factory=_empty_block_list)
    lookback: int | None = None
    location: SourceLocation | None = None

    def __repr__(self) -> str:
        parts = [f":by {self.by}", f":select ({self.select_direction} {self.select_count})"]
        if self.lookback:
            parts.append(f":lookback {self.lookback}")
        children_str = " ".join(repr(c) for c in self.children)
        return f"(filter {' '.join(parts)} {children_str})"


@dataclass(slots=True)
class Strategy:
    """Root strategy container.

    Examples:
        (strategy "My Portfolio"
          :rebalance monthly
          :benchmark SPY
          (weight :method equal
            (asset VTI)
            (asset BND)))
    """

    name: str
    children: list[Block] = field(default_factory=_empty_block_list)
    rebalance: RebalanceFrequency | None = None
    benchmark: str | None = None
    description: str | None = None
    location: SourceLocation | None = None

    def __repr__(self) -> str:
        parts = [f'"{self.name}"']
        if self.rebalance:
            parts.append(f":rebalance {self.rebalance}")
        if self.benchmark:
            parts.append(f":benchmark {self.benchmark}")
        children_str = " ".join(repr(c) for c in self.children)
        return f"(strategy {' '.join(parts)} {children_str})"


# Union type for all block types
type Block = Strategy | Group | Weight | Asset | If | Filter


# =============================================================================
# Constants
# =============================================================================

# Valid rebalance frequencies
REBALANCE_FREQUENCIES: frozenset[str] = frozenset(
    {"daily", "weekly", "monthly", "quarterly", "annually"}
)

# Valid weight methods
WEIGHT_METHODS: frozenset[str] = frozenset(
    {
        "specified",
        "equal",
        "momentum",
        "inverse-volatility",
        "min-variance",
        "market-cap",
        "risk-parity",
    }
)

# Valid filter criteria
FILTER_CRITERIA: frozenset[str] = frozenset({"momentum", "volatility", "volume"})

# Valid comparison operators
COMPARISON_OPS: frozenset[str] = frozenset({">", "<", ">=", "<=", "=", "!="})

# Valid logical operators
LOGICAL_OPS: frozenset[str] = frozenset({"and", "or", "not"})

# Valid crossover operators
CROSSOVER_OPS: frozenset[str] = frozenset({"crosses-above", "crosses-below"})

# Supported indicators for conditions
# This is the single source of truth - extractor.py imports from here
INDICATORS: frozenset[str] = frozenset(
    {
        "sma",
        "ema",
        "rsi",
        "macd",
        "atr",
        "adx",
        "bbands",
        "stoch",
        "cci",
        "obv",
        "vwap",
        # Additional indicators (sync with extractor.py INDICATOR_LOOKBACKS)
        "mfi",
        "williams-r",
        "keltner",
        "donchian",
        "stddev",
        "momentum",
    }
)

# Supported metrics
METRICS: frozenset[str] = frozenset({"drawdown", "return", "volatility"})
