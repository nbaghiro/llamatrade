"""AST node types for the S-expression DSL."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TypedDict


# TypedDicts for strategy configuration
class SizingConfig(TypedDict, total=False):
    """Position sizing configuration."""

    type: str  # "percent-equity", "fixed", "risk-based"
    value: float


class RiskConfig(TypedDict, total=False):
    """Risk management configuration."""

    stop_loss_pct: float
    take_profit_pct: float
    trailing_stop_pct: float
    max_position_pct: float


# Literal value type - recursive for lists
LiteralValue = int | float | str | bool | list["LiteralValue"]


@dataclass(frozen=True, slots=True)
class Literal:
    """Numeric, string, or boolean literal value."""

    value: LiteralValue

    def __repr__(self) -> str:
        if isinstance(self.value, str):
            return f'"{self.value}"'
        if isinstance(self.value, bool):
            return "true" if self.value else "false"
        if isinstance(self.value, list):
            return f"[{', '.join(repr(v) for v in self.value)}]"
        return str(self.value)


@dataclass(frozen=True, slots=True)
class Symbol:
    """
    Reference to a named value.

    Symbols are used for:
    - Price data: close, open, high, low, volume
    - Custom variables: $symbol, $price
    """

    name: str

    def __repr__(self) -> str:
        return self.name


@dataclass(frozen=True, slots=True)
class Keyword:
    """
    Keyword argument marker.

    Keywords start with colon in S-expressions:
    - :name, :symbols, :entry, :exit
    - :line, :signal (for indicator output selection)
    """

    name: str

    def __repr__(self) -> str:
        return f":{self.name}"


@dataclass(frozen=True, slots=True)
class FunctionCall:
    """
    Function or operator invocation.

    Represents all S-expression lists:
    - Indicators: (sma close 20), (rsi close 14)
    - Operators: (> a b), (and cond1 cond2)
    - Arithmetic: (+ a b), (* x y z)
    """

    name: str
    args: tuple[ASTNode, ...]

    def __repr__(self) -> str:
        if not self.args:
            return f"({self.name})"
        args_str = " ".join(repr(arg) for arg in self.args)
        return f"({self.name} {args_str})"


@dataclass(slots=True)
class Strategy:
    """
    Complete strategy definition.

    Parsed from:
    (strategy
      :name "..."
      :symbols ["AAPL" "MSFT"]
      :timeframe "1D"
      :entry (and ...)
      :exit (or ...)
      :risk {...})
    """

    name: str
    symbols: list[str]
    timeframe: str
    entry: ASTNode
    exit: ASTNode
    description: str | None = None
    strategy_type: str = "custom"
    sizing: SizingConfig = field(
        default_factory=lambda: SizingConfig(type="percent-equity", value=10)
    )
    risk: RiskConfig = field(default_factory=dict)

    def __repr__(self) -> str:
        return f"Strategy(name={self.name!r}, symbols={self.symbols}, timeframe={self.timeframe!r})"


# Type alias for any AST node
ASTNode = Literal | Symbol | Keyword | FunctionCall


# Valid price/volume references
PRICE_SYMBOLS = frozenset({"close", "open", "high", "low", "volume", "timestamp"})

# Valid timeframes
TIMEFRAMES = frozenset({"1m", "5m", "15m", "30m", "1H", "4H", "1D", "1W", "1M"})

# Strategy types
STRATEGY_TYPES = frozenset(
    {
        "trend_following",
        "mean_reversion",
        "momentum",
        "breakout",
        "custom",
    }
)
